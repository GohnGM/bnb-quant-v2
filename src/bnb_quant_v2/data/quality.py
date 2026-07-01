"""K 线数据质量审计。

用于导入后自检：时间连续性、OHLC 合法性、开收价衔接、阴阳线与下一根涨跌的统计一致性。
``candle_artifact_pct`` 过高通常意味着 open/close 列被交换或数据源异常。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class QualityReport:
    """单次 ``audit_klines`` 结果摘要。"""

    rows: int
    time_start: str
    time_end: str
    duplicate_times: int
    gap_not_1bar: int
    ohlc_violations: int
    open_eq_prev_close_pct: float
    close_t1_eq_open_t_pct: float
    fwd_up_given_yang_pct: float
    fwd_up_given_yin_pct: float
    candle_artifact_pct: float  # P(fwd_c2c_up)==P(yin) 暗示 open/close 列对调

    @property
    def has_critical_issues(self) -> bool:
        """重复时间戳、OHLC 违规或 artifact 过高视为严重问题。"""
        return (
            self.ohlc_violations > 0
            or self.candle_artifact_pct > 80
            or self.duplicate_times > 0
        )

    def summary(self) -> str:
        return (
            f"n={self.rows} {self.time_start}~{self.time_end} | "
            f"dup={self.duplicate_times} gaps={self.gap_not_1bar} ohlc_bad={self.ohlc_violations} | "
            f"open==prev_close={self.open_eq_prev_close_pct:.1f}% "
            f"close[t+1]==open[t]={self.close_t1_eq_open_t_pct:.1f}% | "
            f"fwd_up|yang={self.fwd_up_given_yang_pct:.1f}% "
            f"fwd_up|yin={self.fwd_up_given_yin_pct:.1f}% "
            f"artifact={self.candle_artifact_pct:.1f}%"
        )


def audit_klines(
    df: pd.DataFrame,
    *,
    bar_hours: float | None = 1.0,
    bar_minutes: float | None = None,
) -> QualityReport:
    """对 K 线 DataFrame 做质量统计。

    Args:
        df: 含 ``open_time, open, high, low, close`` 的 K 线表。
        bar_hours: 1H 等按小时计周期时使用。
        bar_minutes: 5m 等按分钟计周期时优先于 ``bar_hours``。
    """
    s = df.sort_values("open_time").reset_index(drop=True).copy()
    if bar_minutes is not None:
        delta = pd.Timedelta(minutes=bar_minutes)
    elif bar_hours:
        delta = pd.Timedelta(hours=bar_hours)
    else:
        delta = None

    dup = int(s["open_time"].duplicated().sum())
    gaps = s["open_time"].diff().dropna()
    gap_bad = int((gaps != delta).sum()) if delta is not None else 0

    viol = (
        (s["high"] < s[["open", "close"]].max(axis=1))
        | (s["low"] > s[["open", "close"]].min(axis=1))
    )
    ohlc_bad = int(viol.sum())

    s["prev_close"] = s["close"].shift(1)
    s["next_close"] = s["close"].shift(-1)
    s["yang"] = s["close"] > s["open"]
    sub = s.dropna(subset=["prev_close", "next_close"])

    open_eq = float((sub["open"] == sub["prev_close"]).mean() * 100)
    c1_eq_o = float((sub["next_close"] == sub["open"]).mean() * 100)
    fwd_yang = float(sub.loc[sub["yang"], "next_close"].gt(sub.loc[sub["yang"], "close"]).mean() * 100)
    fwd_yin = float(sub.loc[~sub["yang"], "next_close"].gt(sub.loc[~sub["yang"], "close"]).mean() * 100)
    artifact = float(((sub["next_close"] > sub["close"]) == (~sub["yang"])).mean() * 100)

    t0 = str(s["open_time"].iloc[0])
    t1 = str(s["open_time"].iloc[-1])
    return QualityReport(
        rows=len(s),
        time_start=t0,
        time_end=t1,
        duplicate_times=dup,
        gap_not_1bar=gap_bad,
        ohlc_violations=ohlc_bad,
        open_eq_prev_close_pct=open_eq,
        close_t1_eq_open_t_pct=c1_eq_o,
        fwd_up_given_yang_pct=fwd_yang,
        fwd_up_given_yin_pct=fwd_yin,
        candle_artifact_pct=artifact,
    )
