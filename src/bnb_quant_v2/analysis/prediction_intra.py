"""5m 微观特征 → 下一根 1H 方向的描述性统计（阶段 3/4 研究用）。

数据来自 ``enrich_1h_with_intra``（第 t 根 1H + 12 根 5m → 预测 t+1）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

TARGET_COL = "next_bar_up"


@dataclass
class BucketStat:
    label: str
    count: int
    next_up_rate: float


@dataclass
class CrossStat:
    label: str
    count: int
    next_up_rate: float


@dataclass
class IntraDescriptiveReport:
    baseline_up_rate: float
    total_bars: int
    yang_cnt_buckets: list[BucketStat]
    last2_yang_buckets: list[BucketStat]
    second_half_ret_buckets: list[BucketStat]
    high_idx_buckets: list[BucketStat]
    low_idx_buckets: list[BucketStat]
    pattern_last3: list[BucketStat]
    close_strength_buckets: list[BucketStat]
    cross_stats: list[CrossStat]


def _labeled(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=[TARGET_COL]).copy()


def _rate(mask: pd.Series, labeled: pd.DataFrame, label: str) -> CrossStat | None:
    if not mask.any():
        return None
    return CrossStat(
        label=label,
        count=int(mask.sum()),
        next_up_rate=float(labeled.loc[mask, TARGET_COL].mean()),
    )


def _bucket_values(
    labeled: pd.DataFrame,
    values: pd.Series,
    edges: list[tuple[float, float, str]],
) -> list[BucketStat]:
    out: list[BucketStat] = []
    for lo, hi, label in edges:
        mask = (values >= lo) & (values < hi)
        if not mask.any():
            continue
        out.append(
            BucketStat(
                label=label,
                count=int(mask.sum()),
                next_up_rate=float(labeled.loc[mask, TARGET_COL].mean()),
            )
        )
    return out


def compare_intra_descriptive(
    df: pd.DataFrame,
    *,
    verbose: bool = True,
    min_pattern_n: int = 100,
) -> IntraDescriptiveReport:
    """按小时内 5m 特征分桶，统计下一根 1H 收涨率。"""
    labeled = _labeled(df)
    n_bars = len(labeled)
    baseline = float(labeled[TARGET_COL].mean()) if n_bars else 0.0

    yang_cnt_buckets: list[BucketStat] = []
    for cnt, grp in labeled.groupby("m5_yang_cnt", sort=True):
        yang_cnt_buckets.append(
            BucketStat(
                label=f"阳线 {int(cnt)} 根",
                count=len(grp),
                next_up_rate=float(grp[TARGET_COL].mean()),
            )
        )

    last2_yang_buckets = [
        BucketStat(
            label="最后2根5m皆阳",
            count=int(labeled["m5_last2_yang"].sum()),
            next_up_rate=float(labeled.loc[labeled["m5_last2_yang"], TARGET_COL].mean()),
        ),
        BucketStat(
            label="最后2根5m非皆阳",
            count=int((~labeled["m5_last2_yang"]).sum()),
            next_up_rate=float(labeled.loc[~labeled["m5_last2_yang"], TARGET_COL].mean()),
        ),
    ]

    second_half_ret_buckets = _bucket_values(
        labeled,
        labeled["m5_second_half_ret"],
        [
            (-1e9, -0.001, "后半段跌"),
            (-0.001, 0.001, "后半段平"),
            (0.001, 1e9, "后半段涨"),
        ],
    )

    high_idx_buckets = _bucket_values(
        labeled,
        labeled["m5_high_idx"],
        [
            (0, 6, "最高价在前半(0-5)"),
            (6, 12, "最高价在后半(6-11)"),
        ],
    )
    low_idx_buckets = _bucket_values(
        labeled,
        labeled["m5_low_idx"],
        [
            (0, 6, "最低价在前半(0-5)"),
            (6, 12, "最低价在后半(6-11)"),
        ],
    )

    close_strength_buckets = _bucket_values(
        labeled,
        labeled["m5_close_strength"],
        [
            (0.0, 0.33, "收盘偏弱 0-33%"),
            (0.33, 0.67, "收盘中部 33-67%"),
            (0.67, 1.01, "收盘偏强 67-100%"),
        ],
    )

    pattern_last3: list[BucketStat] = []
    for pat, grp in labeled.groupby("m5_pattern_last3", sort=False):
        if len(grp) < min_pattern_n:
            continue
        pattern_last3.append(
            BucketStat(
                label=str(pat),
                count=len(grp),
                next_up_rate=float(grp[TARGET_COL].mean()),
            )
        )
    pattern_last3.sort(key=lambda x: x.next_up_rate, reverse=True)

    cross_stats: list[CrossStat] = []
    crosses: list[tuple[pd.Series, str]] = [
        (labeled["yin"] & labeled["m5_last2_yang"], "1H阴 & 最后2根5m皆阳"),
        (labeled["yin"] & (~labeled["m5_last2_yang"]), "1H阴 & 最后2根5m非皆阳"),
        (labeled["yang"] & labeled["m5_last2_yang"], "1H阳 & 最后2根5m皆阳"),
        (labeled["yang"] & (~labeled["m5_last2_yang"]), "1H阳 & 最后2根5m非皆阳"),
        (labeled["yin"] & (labeled["m5_pattern_last3"] == "阴阴阴"), "1H阴 & 尾盘5m阴阴阴"),
        (labeled["yang"] & (labeled["m5_pattern_last3"] == "阳阳阳"), "1H阳 & 尾盘5m阳阳阳"),
        (labeled["candle_type"] == "大阴线", "1H大阴线"),
        (
            (labeled["candle_type"] == "大阴线") & (labeled["m5_second_half_ret"] > 0),
            "1H大阴线 & 后半段5m反弹",
        ),
        (
            (labeled["candle_type"] == "大阴线") & (labeled["m5_second_half_ret"] <= 0),
            "1H大阴线 & 后半段5m未反弹",
        ),
        (
            (labeled["m5_first_half_ret"] < 0) & (labeled["m5_second_half_ret"] > 0),
            "前半跌 & 后半涨(V形)",
        ),
        (
            (labeled["m5_first_half_ret"] > 0) & (labeled["m5_second_half_ret"] < 0),
            "前半涨 & 后半跌(倒V)",
        ),
        (labeled["m5_low_idx"] >= 6, "最低价出现在后半(6-11)"),
        (labeled["m5_low_idx"] < 6, "最低价出现在前半(0-5)"),
        (labeled["m5_last1_yang"] & labeled["yin"], "1H阴 & 最后1根5m阳"),
        (labeled["m5_last1_yang"] & labeled["yang"], "1H阳 & 最后1根5m阳"),
        ((~labeled["m5_last1_yang"]) & labeled["yang"], "1H阳 & 最后1根5m阴"),
    ]
    for mask, label in crosses:
        row = _rate(mask, labeled, label)
        if row and row.count >= 30:
            cross_stats.append(row)
    cross_stats.sort(key=lambda x: x.next_up_rate, reverse=True)

    report = IntraDescriptiveReport(
        baseline_up_rate=baseline,
        total_bars=n_bars,
        yang_cnt_buckets=yang_cnt_buckets,
        last2_yang_buckets=last2_yang_buckets,
        second_half_ret_buckets=second_half_ret_buckets,
        high_idx_buckets=high_idx_buckets,
        low_idx_buckets=low_idx_buckets,
        pattern_last3=pattern_last3,
        close_strength_buckets=close_strength_buckets,
        cross_stats=cross_stats,
    )
    if verbose:
        print_intra_descriptive(report)
    return report


def export_intra_descriptive_csv(report: IntraDescriptiveReport, path: Path | str) -> Path:
    """导出分桶与交叉统计为 CSV。"""
    rows: list[dict] = []
    sections = [
        ("m5_yang_cnt", report.yang_cnt_buckets),
        ("m5_last2_yang", report.last2_yang_buckets),
        ("m5_second_half_ret", report.second_half_ret_buckets),
        ("m5_high_idx", report.high_idx_buckets),
        ("m5_low_idx", report.low_idx_buckets),
        ("m5_close_strength", report.close_strength_buckets),
        ("m5_pattern_last3", report.pattern_last3),
        ("cross", report.cross_stats),
    ]
    for section, items in sections:
        for item in items:
            rows.append(
                {
                    "section": section,
                    "label": item.label,
                    "count": item.count,
                    "next_up_rate": item.next_up_rate,
                }
            )
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def print_intra_descriptive(report: IntraDescriptiveReport) -> None:
    blind = max(report.baseline_up_rate, 1 - report.baseline_up_rate)
    print("================== 小时内 5m → 下一根 1H 方向（描述性）==================")
    print("说明: 特征来自第 t 根 1H 内 12 根 5m；目标为第 t+1 根 1H 开→收收涨")
    print(f"样本: {report.total_bars} 根  |  基准下一根收涨 {report.baseline_up_rate*100:.2f}%")
    print(f"盲猜上限 {blind*100:.2f}%\n")

    def _print_buckets(title: str, buckets: list[BucketStat]) -> None:
        print(f"--- {title} ---")
        for b in buckets:
            print(f"  {b.label:<28} n={b.count:>6}  下一根涨 {b.next_up_rate*100:.1f}%")
        print()

    _print_buckets("小时内阳线根数 m5_yang_cnt", report.yang_cnt_buckets)
    _print_buckets("最后 2 根 5m 阴阳", report.last2_yang_buckets)
    _print_buckets("后半段 5m 涨跌 m5_second_half_ret", report.second_half_ret_buckets)
    _print_buckets("最高价出现位置 m5_high_idx", report.high_idx_buckets)
    _print_buckets("最低价出现位置 m5_low_idx", report.low_idx_buckets)
    _print_buckets("收盘强度 m5_close_strength", report.close_strength_buckets)

    print("--- 尾盘 3 根 5m 形态 m5_pattern_last3（按收涨率）---")
    for b in report.pattern_last3:
        print(f"  {b.label:<8} n={b.count:>6}  下一根涨 {b.next_up_rate*100:.1f}%")
    print()

    print("--- 1H × 5m 交叉（按收涨率）---")
    for c in report.cross_stats:
        print(f"  {c.label:<36} n={c.count:>6}  下一根涨 {c.next_up_rate*100:.1f}%")
    print("=" * 72)
