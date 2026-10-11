#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcd-pick-one 决策引擎
=====================

把「候选餐品 + 用户口味档案」翻译成**唯一一个**推荐结果。

职责边界
--------
* 只做 **筛选 + 打分 + 排序**，不做任何写操作（不下单、不领券）
* 取数由麦当劳 MCP 负责（菜单 / 券 / 算价），决策由本脚本负责
* **本脚本不感知渠道差异**（菜单两套编码、档期规则、券可用性都属取数层）。
  唯一与渠道相关的只有「费用」，见下。

费用语义（重要，别搞错）
------------------------
`candidates[].price` 的语义被钉死为 **`calculate-price` 返回的实付总价**。

真机联调实测（2026-10-11，门店 1980359）：

* **到店自取** → `price` 只含商品价。返回里**没有**任何附加费字段。
* **麦乐送**   → `price` **已经含**配送费与打包费：
  `3240 = 商品 2450 + 配送 600 + 打包 190`

因此本脚本**默认不再叠加任何费用**（`--estimate-fee` 默认 0）。

只有当你的 `price` 其实是**未经核价的菜单价**时，才把输入里的 `price_basis`
写成 `"menu"`，并用 `--estimate-fee` 传一个附加费估算值。

> ⚠️ **最常见的错法**：外送场景既喂核价实付价、又传 `--estimate-fee 7.9`，
> 结果把配送费和打包费**算了两遍**（42.80 会变成 50.70）。
> 想避免这个坑，就用默认的 `price_basis="final"`。
>
> 💡 另外，打包费**按商品类型计**：只点饮品的那次核价，打包费字段直接缺席（=0）。
> 所以任何「写死一个固定费用」的做法在边界场景都是错的——费用只应来自核价。

决策顺序
--------
1. 硬筛选：剔除忌口 -> 必须满足「主食 + 配餐」结构
2. 打分：score = 口味满足度(1~5) / 实付价
3. 排序：分数高者优先；都不满足预算时，退化为「给最接近的 + 标注超标金额」

用法
----
    python pick_one.py --input demo.json
    python pick_one.py --input demo.real.json                      # 到店自取（默认）
    python pick_one.py --input demo.delivery.json --channel delivery
    python pick_one.py --input demo.json --price-basis menu --estimate-fee 7.9
    python pick_one.py --input demo.json --json

仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Tuple

DEFAULT_BUDGET = 25.0
DEFAULT_ESTIMATE_FEE = 0.0

# 渠道只用于**标注与告警**，不改变决策规则。
CHANNEL_TAKEOUT = "takeout"
CHANNEL_DELIVERY = "delivery"
CHANNELS = (CHANNEL_TAKEOUT, CHANNEL_DELIVERY)

MAIN_ROLES = {"main"}
# 配餐必须是「有实物的」：薯条 / 薯饼 / 鸡块 / 派 / 香肠……
# 饮料与甜品不计入配餐——否则一瓶 8.5 元的矿泉水就能顶一顿饭，「吃饱」检查形同虚设。
# 饮料是单独询问的可选附加项：计入预算，但不构成饱腹结构。
SIDE_ROLES = {"side"}

# price 的两种语义
PRICE_BASIS_FINAL = "final"  # price 已是 calculate-price 的实付总价（默认，最安全）
PRICE_BASIS_MENU = "menu"    # price 是菜单价，需叠加 --estimate-fee


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def norm(text: Any) -> str:
    return str(text or "").strip().lower()


def haystack_of(meal: Dict[str, Any]) -> str:
    """把菜名、标签、单品名拼成一个大字符串，用于忌口匹配。"""
    parts: List[str] = [norm(meal.get("name", ""))]
    parts.extend(norm(t) for t in meal.get("tags", []) or [])
    parts.extend(norm(i.get("name", "")) for i in meal.get("items", []) or [])
    return " ".join(p for p in parts if p)


def hits_ban(meal: Dict[str, Any], banned: List[str]) -> bool:
    hay = haystack_of(meal)
    return any(norm(b) and norm(b) in hay for b in banned or [])


def structure_ok(meal: Dict[str, Any]) -> bool:
    """结构达标 = 至少一份主食 + 至少一份配餐。"""
    roles = [norm(i.get("role", "")) for i in meal.get("items", []) or []]
    return any(r in MAIN_ROLES for r in roles) and any(r in SIDE_ROLES for r in roles)


def satisfaction(meal: Dict[str, Any], profile: Dict[str, Any]) -> float:
    """满足度 = 各餐品口味分的平均；标过的用档案分，没标过的用默认分。"""
    taste_map = {norm(k): float(v) for k, v in (profile.get("taste") or {}).items()}
    default = float(profile.get("default_taste", 3.0))
    scores: List[float] = []
    for item in meal.get("items", []) or []:
        key = norm(item.get("name", ""))
        raw = taste_map.get(key)
        if raw is None:
            raw = float(item.get("taste", default))
        scores.append(raw)
    return round(sum(scores) / len(scores), 3) if scores else 0.0


def resolve_fee(payload: Dict[str, Any], estimate_fee: float) -> Tuple[str, float]:
    """决定要不要叠加附加费。

    只有 `price_basis == "menu"`（price 是菜单价）时才叠加；
    否则一律返回 0，**从机制上杜绝「配送费算两遍」**。
    """
    basis = norm(payload.get("price_basis") or PRICE_BASIS_FINAL)
    if basis == PRICE_BASIS_MENU:
        return basis, round(float(estimate_fee), 2)
    return basis, 0.0


def collect_warnings(channel: str, basis: str, fee: float, payload: Dict[str, Any]) -> List[str]:
    """收集「数据可能不自洽」的告警。不改变结论，只提醒。"""
    warns: List[str] = []

    if channel == CHANNEL_DELIVERY and basis == PRICE_BASIS_MENU and fee <= 0:
        warns.append(
            "外送 + price_basis=menu 但 estimate-fee=0：配送费与打包费未计入，实付价会偏低。"
            "实测外送附加费为 配送 6.00 + 打包 1.90 = 7.90 元。"
        )

    src = payload.get("_source") or {}
    raw_order_type = src.get("order_type")
    if raw_order_type is not None:
        try:
            expected = 2 if channel == CHANNEL_DELIVERY else 1
            if int(raw_order_type) != expected:
                warns.append(
                    "渠道与快照来源不一致：--channel=%s 但 _source.order_type=%s。"
                    % (channel, raw_order_type)
                )
        except (TypeError, ValueError):
            pass

    return warns


def decide(
    payload: Dict[str, Any], budget: float, estimate_fee: float, channel: str
) -> Dict[str, Any]:
    profile = payload.get("profile") or {}
    banned = profile.get("banned") or []
    candidates = payload.get("candidates") or []

    basis, fee = resolve_fee(payload, estimate_fee)

    kept: List[Dict[str, Any]] = []
    dropped = {"banned": [], "structure": []}

    for meal in candidates:
        if hits_ban(meal, banned):
            dropped["banned"].append(meal.get("name"))
            continue
        if not structure_ok(meal):
            dropped["structure"].append(meal.get("name"))
            continue
        kept.append(meal)

    scored: List[Dict[str, Any]] = []
    for meal in kept:
        price = round(float(meal.get("price", 0.0)) + fee, 2)
        sat = satisfaction(meal, profile)
        scored.append(
            {
                "name": meal.get("name"),
                "items": [i.get("name") for i in meal.get("items", []) or []],
                "satisfaction": sat,
                "actual_price": price,
                "over_budget": round(max(0.0, price - budget), 2),
                "score": round(sat / price, 4) if price > 0 else 0.0,
            }
        )

    scored.sort(key=lambda x: (-x["score"], x["actual_price"]))

    common = {
        "dropped": dropped,
        "budget": budget,
        "channel": channel,
        "price_basis": basis,
        "estimate_fee": fee,
        "warnings": collect_warnings(channel, basis, fee, payload),
    }

    in_budget = [s for s in scored if s["actual_price"] <= budget]
    if in_budget:
        return dict(common, status="ok", pick=in_budget[0], alternatives=in_budget[1:3])
    if scored:
        closest = min(scored, key=lambda x: x["actual_price"])
        return dict(common, status="over_budget", pick=closest, alternatives=[])
    return dict(common, status="empty", pick=None, alternatives=[])


def render(result: Dict[str, Any]) -> str:
    budget = result.get("budget", DEFAULT_BUDGET)
    fee = result.get("estimate_fee", 0.0)
    channel = result.get("channel", CHANNEL_TAKEOUT)
    is_delivery = channel == CHANNEL_DELIVERY
    how = "外送" if is_delivery else "自取"
    lines: List[str] = []

    if result["status"] == "empty":
        lines.append("【今天没有合适的】")
        lines.append("所有候选都被忌口或「主食+配餐」结构条件筛掉了。")
        if result["dropped"]["banned"]:
            lines.append("  · 忌口筛掉：" + "、".join(result["dropped"]["banned"]))
        if result["dropped"]["structure"]:
            lines.append("  · 结构不达标：" + "、".join(result["dropped"]["structure"]))
        return "\n".join(lines)

    pick = result["pick"]

    if result["status"] == "over_budget":
        lines.append("【今天没有完全符合的】")
        lines.append(
            "最接近的是 %s，实付 %.2f 元，超了 %.2f 元。"
            % (pick["name"], pick["actual_price"], pick["over_budget"])
        )
        if is_delivery:
            lines.append("（外送附加费固定 %.2f 元：配送 + 打包，使得预算比自取更难满足）" % fee if fee else
                         "（原因：外送附加费为配送 + 打包，使实付价高于同内容的自取价）")
        lines.append("要不要就按这个来？还是放宽预算？")
        return "\n".join(lines)

    lines.append("【今天就吃这个】")
    lines.append("  %s" % pick["name"])
    composed = " + ".join(pick["items"])
    # 菜名本身就是单品罗列时（如「A + B」），不再重复打印「构成」一行
    if composed and composed != pick["name"]:
        lines.append("  构成：%s" % composed)
    if fee:
        lines.append("  实付：%.2f 元（含估算附加费 %.2f，预算 %.2f）" % (pick["actual_price"], fee, budget))
    else:
        lines.append("  实付：%.2f 元（%s，预算 %.2f）" % (pick["actual_price"], how, budget))
    lines.append("  满足度：%.1f / 5　性价比得分：%.4f" % (pick["satisfaction"], pick["score"]))

    alts = result.get("alternatives") or []
    if alts:
        lines.append("  备选（追问才展示）：")
        for alt in alts:
            lines.append(
                "    - %s（实付 %.2f 元，得分 %.4f）" % (alt["name"], alt["actual_price"], alt["score"])
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="mcd-pick-one 决策引擎：只输出一个答案")
    parser.add_argument("--input", required=True, help="输入 JSON，需含 profile 与 candidates")
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET, help="一餐预算上限（元），默认 25")
    parser.add_argument(
        "--channel",
        choices=CHANNELS,
        default=CHANNEL_TAKEOUT,
        help="取餐渠道：takeout 到店自取（默认）/ delivery 麦乐送。仅影响标注与告警，不改变决策规则",
    )
    parser.add_argument(
        "--estimate-fee",
        type=float,
        default=DEFAULT_ESTIMATE_FEE,
        help="附加费估算值（元）。**仅当** price_basis=menu（price 是菜单价）时才生效，默认 0",
    )
    parser.add_argument(
        "--price-basis",
        choices=(PRICE_BASIS_FINAL, PRICE_BASIS_MENU),
        default=None,
        help="声明输入里 price 的语义：final=已是核价实付总价（默认，最安全）/ menu=菜单价，需叠加 --estimate-fee",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出原始结果")
    return parser


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = load_json(args.input)
    except FileNotFoundError:
        print("找不到输入文件：%s" % args.input, file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print("输入不是合法 JSON：%s" % exc, file=sys.stderr)
        return 2

    if args.price_basis:
        payload["price_basis"] = args.price_basis

    budget = float((payload.get("profile") or {}).get("budget", args.budget))
    if args.budget != DEFAULT_BUDGET:
        budget = args.budget

    result = decide(payload, budget, args.estimate_fee, args.channel)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result))
        for warn in result.get("warnings") or []:
            print("  ⚠️  %s" % warn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
