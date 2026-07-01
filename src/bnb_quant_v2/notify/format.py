"""Telegram 消息模板（双时区 UTC / 北京时间）。

消息类型
--------
- ``format_signal_message`` — p1×f6 触发信号（做多/做空 · 主规则/严格规则）
- ``format_alert_message``  — 运维告警（数据不足、sync 失败）
- ``format_heartbeat_message`` — 日心跳（过去 24h 统计）

依赖 ``analysis.evaluator.LiveSignal`` 仅用于类型标注，避免 runtime ↔ notify 循环导入。
"""
from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pandas as pd

from bnb_quant_v2.analysis.intra_5m import F6_BARS

if TYPE_CHECKING:
    from bnb_quant_v2.analysis.evaluator import LiveSignal

BEIJING = "Asia/Shanghai"

_TIER_LABELS = {
    "primary": "主规则·做多",
    "strict": "严格规则·做多",
    "primary_short": "主规则·做空",
    "strict_short": "严格规则·做空",
}
_BACKTEST_HINTS = {
    "primary": "回测约 84%",
    "strict": "回测约 91% · 覆盖较低",
    "primary_short": "回测约 83%",
    "strict_short": "回测约 92% · 覆盖较低",
}


def _as_utc(ts: pd.Timestamp | str) -> pd.Timestamp:
    out = pd.Timestamp(ts)
    if out.tzinfo is None:
        return out.tz_localize("UTC")
    return out.tz_convert("UTC")


def format_dual_time(ts: pd.Timestamp | str) -> tuple[str, str]:
    """返回 (UTC 字符串, 北京时间字符串)，格式 ``YYYY-MM-DD HH:MM``。"""
    utc = _as_utc(ts)
    bj = utc.tz_convert(BEIJING)
    return utc.strftime("%Y-%m-%d %H:%M"), bj.strftime("%Y-%m-%d %H:%M")


def format_time_block(label: str, ts: pd.Timestamp | str) -> str:
    """带标签的双时区时间块，用于信号消息正文。"""
    utc_s, bj_s = format_dual_time(ts)
    return f"{label}\n  UTC: {utc_s}\n  北京: {bj_s}"


def _format_usdt(price: float) -> str:
    if price != price:
        return "n/a"
    return f"{price:,.2f} USDT"


def format_signal_message(sig: LiveSignal, *, tier: str) -> str:
    """格式化规则触发信号（``tier``: primary / strict / primary_short / strict_short）。"""
    tier_label = _TIER_LABELS.get(tier, "规则")
    emoji = "🟢" if sig.direction == 1 else "🔴" if sig.direction == -1 else "⚪"
    backtest_hint = _BACKTEST_HINTS.get(tier, "回测仅供参考")
    entry_s = _format_usdt(sig.entry_price)
    hour_open_s = _format_usdt(sig.hour_open_price)

    strength = sig.f6_close_strength
    strength_s = f"{strength:.0%}" if strength == strength else "n/a"
    ret_s = f"{sig.f6_ret_sum * 100:.2f}%" if sig.f6_ret_sum == sig.f6_ret_sum else "n/a"
    if sig.direction == -1:
        f6_cnt_label = f"f6阴: {F6_BARS - sig.f6_yang_cnt}"
    else:
        f6_cnt_label = f"f6阳: {sig.f6_yang_cnt}"

    price_lines = [f"  入场价 (:30): {entry_s}"]
    if hour_open_s != "n/a":
        price_lines.insert(0, f"  1H 开盘价: {hour_open_s}")

    lines = [
        f"{emoji} BTCUSDT p1×f6 · {tier_label}",
        f"入场 {entry_s}",
        "",
        f"规则: {sig.rule}",
        f"预测: {sig.prediction}（{'做多' if sig.direction == 1 else '做空' if sig.direction == -1 else '观望'}）",
        "────────────────",
        "价格",
        *price_lines,
        "────────────────",
        format_time_block("1H 开盘", sig.hour_open_time),
        format_time_block("入场 (:30)", sig.entry_at),
        format_time_block("出场 (1H 收盘)", sig.exit_at),
        "────────────────",
        f"p1: {sig.p1_candle_type} | {f6_cnt_label} | f6涨: {ret_s} | f6收盘强度: {strength_s}",
        f"⚠️ 非投资建议 · {backtest_hint}",
    ]
    return "\n".join(lines)


def format_alert_message(title: str, detail: str, *, as_of: pd.Timestamp | None = None) -> str:
    """运维告警模板（数据不足、sync 失败等）。"""
    ts = _as_utc(as_of if as_of is not None else pd.Timestamp.utcnow())
    utc_s, bj_s = format_dual_time(ts)
    return (
        f"⚠️ bnb-quant-v2 告警\n"
        f"{title}\n"
        f"{detail}\n"
        f"UTC: {utc_s}\n"
        f"北京: {bj_s}"
    )


def format_heartbeat_message(
    *,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
    sync_5m_ok: int,
    sync_5m_total: int,
    sync_1h_ok: int,
    sync_1h_total: int,
    eval_count: int,
    primary_triggers: int,
    strict_triggers: int,
    primary_short_triggers: int = 0,
    strict_short_triggers: int = 0,
    latest_5m: pd.Timestamp | None,
    status: str,
) -> str:
    """每日心跳：汇总过去 24h sync / eval / 触发次数。"""
    start_utc, start_bj = format_dual_time(period_start)
    end_utc, end_bj = format_dual_time(period_end)
    latest_block = "n/a"
    if latest_5m is not None:
        lu, lb = format_dual_time(latest_5m)
        latest_block = f"5m {lu} UTC ({lb} 北京)"

    return (
        f"💓 bnb-quant-v2 日心跳\n\n"
        f"统计区间: 过去 24h\n"
        f"  UTC: {start_utc} – {end_utc}\n"
        f"  北京: {start_bj} – {end_bj}\n"
        f"────────────────\n"
        f"5m sync: {sync_5m_ok}/{sync_5m_total} 成功\n"
        f"1h sync: {sync_1h_ok}/{sync_1h_total} 成功\n"
        f":30 评估: {eval_count} 次\n"
        f"信号: 做多主 {primary_triggers} · 做多严 {strict_triggers} · "
        f"做空主 {primary_short_triggers} · 做空严 {strict_short_triggers}\n"
        f"最新 K 线: {latest_block}\n"
        f"状态: {status}"
    )


def heartbeat_period_end(as_of: pd.Timestamp | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """心跳统计窗口：结束于最近一个 04:00 UTC，向前 24 小时。

    对应北京时间 12:00 日心跳。
    """
    end = _as_utc(as_of if as_of is not None else pd.Timestamp.utcnow())
    end = end.floor("D") + timedelta(hours=4)
    if _as_utc(as_of if as_of is not None else pd.Timestamp.utcnow()) < end:
        end = end - timedelta(days=1)
    start = end - timedelta(hours=24)
    return start, end
