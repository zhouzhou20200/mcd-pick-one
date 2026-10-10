#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcd-pick-one 顺手提示排序器
==========================

把「门店档期 / 活动 / 券」三路数据，收敛成**最多 1 条**提示——或者**保持沉默**。

为什么需要它
------------
推荐助手最常见的失败不是"说得太少"，而是**说得太多**：
答案给完再堆一句"另外你还有 8 张券可以领、这个月有联名周边、积分商城 88 分可以换……"，
用户就又回到了「要做决定」的状态——而这正是本项目要消除的东西。

所以提示不是"有信息就说"，而是必须**同时**通过三道门槛：

    ① 现在就能做      —— 需要等待或额外条件的，不提示
    ② 错过不可逆      —— 过了这个点就没了；"明天也能做"的不提示
    ③ 只留 1 条       —— 多条合格时取**最紧急**的 1 条，其余全部丢弃

**默认是沉默。** 没有合格项时输出空，这是设计的一部分。

用法
----
    python rank_tips.py --input demo.tips.json
    python rank_tips.py --input demo.tips.json --now "2026-10-10 15:30"
    python rank_tips.py --input demo.tips.json --all      # 打印全部候选（调试用）
    python rank_tips.py --input demo.tips.json --json

仅依赖 Python 标准库。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# ── 阈值 ────────────────────────────────────────────────────────────────
# 档期剩余 <= 该分钟数时，视为"即将切换"，构成不可逆事件
SLOT_ALERT_MINUTES = 30
# 券剩余 <= 该小时数时，视为"即将过期"
COUPON_ALERT_HOURS = 48

# 三类**可能**通过门槛的信息；其余一律不进入候选
KIND_SLOT = "slot"        # ⏰ 档期即将切换
KIND_CAMPAIGN = "campaign"  # 🎰 仅今日有效的活动
KIND_COUPON = "coupon"    # 🎫 手里已有且即将过期的券


# ── 时间解析 ────────────────────────────────────────────────────────────
def parse_now(text: Optional[str]) -> datetime:
    if not text:
        return datetime.now()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    raise ValueError("无法解析时间：%s（支持 YYYY-MM-DD[ HH:MM[:SS]]）" % text)


def parse_on_date(now: datetime, hhmm: Optional[str]) -> Optional[datetime]:
    """把 "HH:MM" 解析成 now 当天的具体时刻。"""
    if not hhmm:
        return None
    try:
        hour, minute = (int(x) for x in str(hhmm).strip().split(":")[:2])
    except (ValueError, TypeError):
        return None
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def parse_datetime(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text).strip(), fmt)
        except ValueError:
            continue
    return None


def end_of_day(now: datetime) -> datetime:
    return now.replace(hour=23, minute=59, second=59, microsecond=0)


# ── 三道门槛 ────────────────────────────────────────────────────────────
def gate_actionable(item: Dict[str, Any]) -> bool:
    """门槛①：现在就能做（不需要等待、不需要额外条件）。"""
    return bool(item.get("actionable", False))


def gate_irreversible(item: Dict[str, Any]) -> bool:
    """门槛②：错过不可逆（存在一个"过了就没了"的截止时刻）。"""
    deadline = item.get("deadline")
    if not isinstance(deadline, datetime):
        return False
    item["minutes_left"] = int((deadline - item["_now"]).total_seconds() // 60)
    return item["minutes_left"] >= 0


# ── 候选生成 ────────────────────────────────────────────────────────────
def collect_candidates(payload: Dict[str, Any], now: datetime) -> tuple:
    """只收三类信息。其余（可领券 / 长期活动 / 新品 / 积分）**根本不生成候选**。

    返回 (候选列表, 被排除在候选之外的信息及原因)。
    """
    raw: List[Dict[str, Any]] = []
    excluded: List[Dict[str, str]] = []

    # ① 档期即将切换 —— 数据来源：query-nearby-stores 的 reservationTimeOptions
    store = payload.get("store") or {}
    store_name = store.get("name") or "本店"
    for slot in store.get("slots") or []:
        start = parse_on_date(now, slot.get("start"))
        end = parse_on_date(now, slot.get("end"))
        if not start or not end:
            continue
        if not (start <= now < end):
            continue  # 当前不在这段档期内
        left = int((end - now).total_seconds() // 60)
        if 0 <= left <= SLOT_ALERT_MINUTES:
            slot_label = ("的%s档" % slot.get("name")) if slot.get("name") else "档"
            raw.append(
                {
                    "kind": KIND_SLOT,
                    "deadline": end,
                    "actionable": True,
                    "text": "%s%s%s %s 结束（还有 %d 分钟），现在下单还来得及。"
                    % ("⏰ ", store_name, slot_label, end.strftime("%H:%M"), left),
                }
            )

    # ② 仅今日有效的活动 —— 数据来源：campaign-calendar
    for camp in payload.get("campaigns") or []:
        title = camp.get("title")
        if not camp.get("today_only"):
            excluded.append({"text": "🎰 「%s」" % title, "reason": "非仅今日活动：错过可逆，不进提示"})
            continue
        if str(camp.get("date", "")) != now.strftime("%Y-%m-%d"):
            excluded.append(
                {"text": "🎰 「%s」" % title, "reason": "仅限 %s，非今日" % camp.get("date")}
            )
            continue
        raw.append(
            {
                "kind": KIND_CAMPAIGN,
                "deadline": end_of_day(now),
                "actionable": True,
                "text": "%s「%s」今天最后一天。" % ("🎰 ", title),
            }
        )

    # ③ 手里已有且即将过期的券 —— 数据来源：query-my-coupons 的 tradeDateTime
    for coupon in payload.get("coupons") or []:
        title = coupon.get("title")
        expire = parse_datetime(coupon.get("expire"))
        if expire is None:
            continue
        left_hours = (expire - now).total_seconds() / 3600
        if 0 < left_hours <= COUPON_ALERT_HOURS:
            raw.append(
                {
                    "kind": KIND_COUPON,
                    "deadline": expire,
                    "actionable": True,
                    "text": "%s你有一张「%s」，%s 过期。"
                    % ("🎫 ", title, expire.strftime("%m-%d %H:%M")),
                }
            )
        else:
            excluded.append(
                {
                    "text": "🎫 「%s」" % title,
                    "reason": "剩余 %.0f 小时，未进入 %d 小时预警窗口"
                    % (left_hours, COUPON_ALERT_HOURS),
                }
            )

    for item in raw:
        item["_now"] = now
    return raw, excluded


def rank(payload: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """过三道门槛 -> 按"不可逆时刻"升序 -> 只留 1 条。"""
    candidates, excluded = collect_candidates(payload, now)

    passed: List[Dict[str, Any]] = []
    rejected: List[Dict[str, str]] = []
    for item in candidates:
        if not gate_actionable(item):
            rejected.append({"text": item["text"], "reason": "门槛①未过：当前做不了"})
            continue
        if not gate_irreversible(item):
            rejected.append({"text": item["text"], "reason": "门槛②未过：不存在未来截止时刻"})
            continue
        passed.append(item)

    # 门槛③：越早不可逆的越优先
    passed.sort(key=lambda x: (x["deadline"], x["kind"]))
    top = passed[0] if passed else None

    return {
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "candidate_count": len(candidates),
        "passed_count": len(passed),
        "excluded": excluded,
        "dropped_by_gate3": [p["text"] for p in passed[1:]],
        "rejected": rejected,
        "tip": top["text"] if top else None,
        "all_passed": [p["text"] for p in passed],
    }


def render(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("【顺手提示】")
    if result["tip"]:
        lines.append("  " + result["tip"])
    else:
        lines.append("  （无）三道门槛均未通过 —— 本次保持沉默。")
    if result["dropped_by_gate3"]:
        lines.append("  被门槛③丢弃（同类过多，只留最紧急的 1 条）：")
        for text in result["dropped_by_gate3"]:
            lines.append("    · " + text)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="mcd-pick-one 顺手提示排序器：最多 1 条，默认沉默")
    parser.add_argument("--input", required=True, help="输入 JSON，需含 store / campaigns / coupons")
    parser.add_argument("--now", default=None, help='覆盖当前时间，格式 "YYYY-MM-DD HH:MM"')
    parser.add_argument("--all", action="store_true", help="打印全部候选与判定理由（调试用）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出原始结果")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except FileNotFoundError:
        print("找不到输入文件：%s" % args.input, file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print("输入不是合法 JSON：%s" % exc, file=sys.stderr)
        return 2

    try:
        now = parse_now(args.now)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    result = rank(payload, now)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.all:
        print("当前时间：%s" % result["now"])
        print("候选总数：%d ｜ 通过门槛：%d" % (result["candidate_count"], result["passed_count"]))
        print()
        print("【进入候选】")
        for text in result["all_passed"]:
            print("  ✔ 通过  " + text)
        for item in result["rejected"]:
            print("  ✗ 拒绝  %s  ← %s" % (item["text"], item["reason"]))
        if result["dropped_by_gate3"]:
            print("  ✗ 丢弃（门槛③：只留最紧急的 1 条）")
            for text in result["dropped_by_gate3"]:
                print("      " + text)
        if result["excluded"]:
            print()
            print("【未进入候选（连被比较的资格都没有）】")
            for item in result["excluded"]:
                print("  – %s  ← %s" % (item["text"], item["reason"]))
        print()
        print(render(result))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
