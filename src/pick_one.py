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

决策顺序
--------
1. 硬筛选：剔除忌口 -> 必须满足「主食 + 配餐」结构
2. 打分：score = 口味满足度(1~5) / 实付价
3. 排序：分数高者优先；都不满足预算时，退化为「给最接近的 + 标注超标金额」

用法
----
    python pick_one.py --input demo.json
    python pick_one.py --input demo.json --budget 25 --delivery-fee 9
    python pick_one.py --input demo.json --json

仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

DEFAULT_BUDGET = 25.0
MAIN_ROLES = {"main"}
SIDE_ROLES = {"side", "drink", "dessert"}


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


def decide(payload: Dict[str, Any], budget: float, delivery_fee: float) -> Dict[str, Any]:
    profile = payload.get("profile") or {}
    banned = profile.get("banned") or []
    candidates = payload.get("candidates") or []

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
        price = round(float(meal.get("price", 0.0)) + float(delivery_fee), 2)
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

    in_budget = [s for s in scored if s["actual_price"] <= budget]
    if in_budget:
        return {
            "status": "ok",
            "pick": in_budget[0],
            "alternatives": in_budget[1:3],
            "dropped": dropped,
            "budget": budget,
            "delivery_fee": delivery_fee,
        }
    if scored:
        closest = min(scored, key=lambda x: x["actual_price"])
        return {
            "status": "over_budget",
            "pick": closest,
            "alternatives": [],
            "dropped": dropped,
            "budget": budget,
            "delivery_fee": delivery_fee,
        }
    return {
        "status": "empty",
        "pick": None,
        "alternatives": [],
        "dropped": dropped,
        "budget": budget,
        "delivery_fee": delivery_fee,
    }


def render(result: Dict[str, Any]) -> str:
    budget = result.get("budget", DEFAULT_BUDGET)
    fee = result.get("delivery_fee", 0.0)
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
        lines.append("要不要就按这个来？还是放宽预算？")
        return "\n".join(lines)

    lines.append("【今天就吃这个】")
    lines.append("  %s" % pick["name"])
    lines.append("  构成：%s" % " + ".join(pick["items"]))
    if fee:
        lines.append("  实付：%.2f 元（含配送费 %.2f，预算 %.2f）" % (pick["actual_price"], fee, budget))
    else:
        lines.append("  实付：%.2f 元（预算 %.2f，自取无配送费）" % (pick["actual_price"], budget))
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
    parser.add_argument("--delivery-fee", type=float, default=0.0, help="外送费（元）；自取填 0")
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

    budget = float((payload.get("profile") or {}).get("budget", args.budget))
    if args.budget != DEFAULT_BUDGET:
        budget = args.budget

    result = decide(payload, budget, args.delivery_fee)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
