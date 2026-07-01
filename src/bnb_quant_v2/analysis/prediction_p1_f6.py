"""p1（前一根 1H+5m）× f6（当前小时前 6 根 5m）→ 当前整根 1H 方向分析。

与 prediction_intra.py（第 t 根整小时 5m → 第 t+1 根）分离，避免混用。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bnb_quant_v2.analysis.intra_5m import F6_BARS

TARGET_COL = "hour_up"


@dataclass
class P1F6CrossRow:
    label: str
    count: int
    hour_up_rate: float
    hour_down_rate: float
    vs_baseline_pp: float


@dataclass
class P1F6DescriptiveReport:
    baseline_up_rate: float
    total_bars: int
    f6_yang_buckets: list[P1F6CrossRow]
    cross_rows: list[P1F6CrossRow]


def _labeled(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=[TARGET_COL]).copy()


def _row(mask: pd.Series, labeled: pd.DataFrame, label: str, baseline: float) -> P1F6CrossRow | None:
    if mask.sum() < 30:
        return None
    up = float(labeled.loc[mask, TARGET_COL].mean())
    return P1F6CrossRow(
        label=label,
        count=int(mask.sum()),
        hour_up_rate=up,
        hour_down_rate=1.0 - up,
        vs_baseline_pp=(up - baseline) * 100,
    )


def build_p1_f6_cross_definitions(labeled: pd.DataFrame) -> list[tuple[pd.Series, str]]:
    """p1 × f6 交叉条件列表。"""
    return [
        (labeled["p1_yin"], "p1: 1H阴"),
        (labeled["p1_yang"], "p1: 1H阳"),
        (labeled["f6_all_yin"], "f6: 前6根皆阴"),
        (labeled["f6_all_yang"], "f6: 前6根皆阳"),
        (labeled["f6_yang_cnt"] <= 2, "f6: 前6根阳线<=2"),
        (labeled["f6_yang_cnt"] >= 4, "f6: 前6根阳线>=4"),
        (labeled["p1_yin"] & labeled["f6_all_yin"], "p1阴 & f6皆阴"),
        (labeled["p1_yin"] & ~labeled["f6_all_yin"], "p1阴 & f6非皆阴"),
        (labeled["p1_yin"] & (labeled["f6_yang_cnt"] <= 2), "p1阴 & f6阳线<=2"),
        (labeled["p1_yang"] & labeled["f6_all_yang"], "p1阳 & f6皆阳"),
        (labeled["p1_yang"] & ~labeled["f6_all_yang"], "p1阳 & f6非皆阳"),
        (labeled["p1_yang"] & (labeled["f6_yang_cnt"] >= 4), "p1阳 & f6阳线>=4"),
        (labeled["p1_candle_type"] == "大阴线", "p1: 大阴线"),
        (labeled["p1_candle_type"] == "大阳线", "p1: 大阳线"),
        (
            (labeled["p1_candle_type"] == "大阴线") & (labeled["f6_yang_cnt"] <= 2),
            "p1大阴 & f6阳线<=2",
        ),
        (
            (labeled["p1_candle_type"] == "大阴线") & (labeled["f6_yang_cnt"] >= 4),
            "p1大阴 & f6阳线>=4",
        ),
        (
            (labeled["p1_candle_type"] == "大阴线") & (labeled["f6_ret_sum"] > 0),
            "p1大阴 & f6前30分累计涨",
        ),
        (
            (labeled["p1_m5_pattern_last3"] == "阴阴阴") & labeled["f6_all_yin"],
            "p1尾盘阴阴阴 & f6皆阴",
        ),
        (
            (labeled["p1_m5_pattern_last3"] == "阴阴阴") & ~labeled["f6_all_yin"],
            "p1尾盘阴阴阴 & f6非皆阴",
        ),
        (labeled["p1_yin"] & labeled["f6_last2_yang"], "p1阴 & f6最后2根皆阳"),
        (labeled["p1_yang"] & (~labeled["f6_last2_yang"]), "p1阳 & f6最后2根非皆阳"),
        (labeled["f6_close_strength"] >= 0.67, "f6收盘强度>=67%"),
        (labeled["f6_close_strength"] <= 0.33, "f6收盘强度<=33%"),
        (labeled["f6_range_hl"] >= 0.004, "f6振幅>=0.4%"),
        (
            (labeled["p1_candle_type"] == "大阴线")
            & (labeled["f6_yang_cnt"] >= 4)
            & (labeled["f6_close_strength"] >= 0.67),
            "p1大阴 & f6阳>=4 & f6收盘强",
        ),
        (
            (labeled["p1_candle_type"] == "大阴线")
            & (labeled["f6_yang_cnt"] >= 4)
            & (labeled["f6_ret_sum"] > 0.002),
            "p1大阴 & f6阳>=4 & f6涨>0.2%",
        ),
        (
            (labeled["p1_candle_type"] == "大阴线") & labeled["f6_yang_cnt"].isin([5, 6]),
            "p1大阴 & f6阳5-6",
        ),
    ]


def compare_p1_f6_descriptive(
    df: pd.DataFrame,
    *,
    verbose: bool = True,
) -> P1F6DescriptiveReport:
    """p1+f6 → 当前整根 1H 收涨率描述统计。"""
    labeled = _labeled(df)
    baseline = float(labeled[TARGET_COL].mean()) if len(labeled) else 0.0

    f6_yang_buckets: list[P1F6CrossRow] = []
    for cnt in range(F6_BARS + 1):
        mask = labeled["f6_yang_cnt"] == cnt
        row = _row(mask, labeled, f"f6阳线{cnt}根", baseline)
        if row:
            f6_yang_buckets.append(row)

    cross_rows: list[P1F6CrossRow] = []
    for mask, label in build_p1_f6_cross_definitions(labeled):
        row = _row(mask, labeled, label, baseline)
        if row:
            cross_rows.append(row)
    cross_rows.sort(key=lambda r: r.hour_up_rate, reverse=True)

    report = P1F6DescriptiveReport(
        baseline_up_rate=baseline,
        total_bars=len(labeled),
        f6_yang_buckets=f6_yang_buckets,
        cross_rows=cross_rows,
    )
    if verbose:
        print_p1_f6_descriptive(report)
    return report


def export_p1_f6_cross_csv(report: P1F6DescriptiveReport, path: Path | str) -> Path:
    rows: list[dict] = []
    for section, items in [
        ("f6_yang_cnt", report.f6_yang_buckets),
        ("p1_x_f6", report.cross_rows),
    ]:
        for item in items:
            rows.append(
                {
                    "section": section,
                    "label": item.label,
                    "count": item.count,
                    "hour_up_rate": item.hour_up_rate,
                    "hour_down_rate": item.hour_down_rate,
                    "vs_baseline_pp": item.vs_baseline_pp,
                }
            )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def print_p1_f6_descriptive(report: P1F6DescriptiveReport) -> None:
    print("================== p1 + f6 → 当前整根 1H 方向（描述性）==================")
    print("p1 = 前一根 1H + 其 12 根 5m  |  f6 = 当前 1H 前 6 根 5m")
    print("信号时点: :30  |  目标: 当前 1H 收阳 (hour_up)")
    print(f"样本: {report.total_bars}  |  基准当前 1H 收涨 {report.baseline_up_rate*100:.2f}%\n")

    print("--- f6 阳线根数 → 当前 1H 涨跌 ---")
    print(f"{'条件':<22} {'样本':>6} {'1H涨':>8} {'1H跌':>8} {'vs基准':>8}")
    for r in report.f6_yang_buckets:
        print(
            f"{r.label:<22} {r.count:>6} {r.hour_up_rate*100:>7.1f}% "
            f"{r.hour_down_rate*100:>7.1f}% {r.vs_baseline_pp:>+7.1f}pp"
        )

    print("\n--- p1 × f6 交叉（按当前 1H 收涨率）---")
    print(f"{'组合':<32} {'样本':>6} {'1H涨':>8} {'1H跌':>8} {'vs基准':>8}")
    for r in report.cross_rows:
        print(
            f"{r.label:<32} {r.count:>6} {r.hour_up_rate*100:>7.1f}% "
            f"{r.hour_down_rate*100:>7.1f}% {r.vs_baseline_pp:>+7.1f}pp"
        )
    print("=" * 72)
