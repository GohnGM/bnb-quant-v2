"""5m 与 1H 对齐、微观结构特征工程（p1 / f6 框架）。

核心概念
--------
- 每小时应有 **12 根 5m**（``EXPECTED_M5_PER_HOUR``）
- **f6**：当前 1H 前 6 根 5m（:00–:25），信号在 **:30** 评估
- **p1**：上一根 1H 及其完整 12 根 5m 特征（``p1_*`` 前缀列）
- **L6**：当前 1H 后 6 根 5m（:30–:55），用于 half2 实验

主要入口
--------
- ``enrich_p1_f6`` — 回测特征表（``complete_only`` 剔除不完整小时）
- ``build_live_p1_f6_row`` 的离线等价逻辑在 ``evaluator`` 中逐小时构建
- ``validate_hour_alignment`` — 验收 5m 聚合 OHLC 与 1H 一致（>99%）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_M5_PER_HOUR = 12
F6_BARS = 6  # 当前 1H 前 6 根 5m（信号在第 30 分钟）
L6_BARS = 6  # 当前 1H 后 6 根 5m（预测目标区间 :30→:60）
F6_CLOSE_STRENGTH_MIN = 0.67  # 前 30 分收盘在振幅上部
F6_RET_STRONG = 0.002  # 前 30 分累计涨幅 >0.2%
F6_RANGE_HL_MIN = 0.004  # 前 30 分振幅 >0.4%
OHLC_RTOL = 1e-9
OHLC_ATOL = 1e-6

# enrich_p1_f6：从第 t-1 行取值并加 p1_ 前缀的列（第 t-1 根 1H + 其 12 根 5m 特征）
P1_SHIFT_COLS = (
    "yin",
    "yang",
    "body_pct",
    "candle_type",
    "m5_yang_cnt",
    "m5_yin_cnt",
    "m5_ret_sum",
    "m5_first_half_ret",
    "m5_second_half_ret",
    "m5_pattern_last3",
    "m5_last2_yang",
    "m5_close_strength",
    "m5_recovery",
)


@dataclass
class AlignmentReport:
    total_1h_bars: int
    with_5m_data: int
    complete_hours: int  # m5_count == 12
    ohlc_all_match: int
    open_match: int
    high_match: int
    low_match: int
    close_match: int
    volume_match: int
    failures: list[dict] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        return self.with_5m_data / self.total_1h_bars * 100 if self.total_1h_bars else 0.0

    @property
    def complete_pct(self) -> float:
        return self.complete_hours / self.total_1h_bars * 100 if self.total_1h_bars else 0.0

    @property
    def ohlc_match_pct(self) -> float:
        return self.ohlc_all_match / self.total_1h_bars * 100 if self.total_1h_bars else 0.0

    @property
    def passed(self) -> bool:
        return self.ohlc_match_pct >= 99.0 and self.complete_pct >= 99.0


def aggregate_5m_to_1h(df_5m: pd.DataFrame) -> pd.DataFrame:
    """将 5m K 线按小时桶聚合为与 1H 对齐的 OHLCV。"""
    m5 = df_5m.sort_values("open_time").reset_index(drop=True).copy()
    m5["hour_bucket"] = m5["open_time"].dt.floor("1h")

    agg = (
        m5.groupby("hour_bucket", sort=True)
        .agg(
            m5_count=("open_time", "count"),
            m5_open=("open", "first"),
            m5_close=("close", "last"),
            m5_high=("high", "max"),
            m5_low=("low", "min"),
            m5_volume=("volume", "sum"),
            m5_first_time=("open_time", "first"),
            m5_last_time=("open_time", "last"),
        )
        .reset_index()
        .rename(columns={"hour_bucket": "open_time"})
    )
    return agg


def align_5m_to_1h(
    df_1h: pd.DataFrame,
    df_5m: pd.DataFrame,
    *,
    complete_only: bool = True,
) -> pd.DataFrame:
    """1H 左连接 5m 小时聚合，每行 1H 附带对应小时内 5m 统计。

    complete_only=True 时剔除 m5_count != 12 的不完整小时（默认开启）。
    """
    h1 = df_1h.sort_values("open_time").reset_index(drop=True).copy()
    agg = aggregate_5m_to_1h(df_5m)
    merged = h1.merge(agg, on="open_time", how="left", suffixes=("", "_m5agg"))
    merged["m5_complete"] = merged["m5_count"] == EXPECTED_M5_PER_HOUR
    if complete_only:
        merged = filter_complete_hours(merged)
    return merged


def filter_complete_hours(
    aligned: pd.DataFrame,
    *,
    expected_m5_count: int = EXPECTED_M5_PER_HOUR,
) -> pd.DataFrame:
    """仅保留小时内恰好 expected_m5_count 根 5m 的 1H 行。"""
    mask = aligned["m5_count"] == expected_m5_count
    return aligned.loc[mask].reset_index(drop=True)


def list_incomplete_hours(
    aligned: pd.DataFrame,
    *,
    expected_m5_count: int = EXPECTED_M5_PER_HOUR,
) -> pd.DataFrame:
    """返回 m5 根数不足的不完整 1H 行。"""
    has_m5 = aligned["m5_count"].notna()
    incomplete = has_m5 & (aligned["m5_count"] != expected_m5_count)
    cols = ["open_time", "m5_count", "m5_first_time", "m5_last_time"]
    present = [c for c in cols if c in aligned.columns]
    return aligned.loc[incomplete, present].reset_index(drop=True)


def _price_match(a: pd.Series, b: pd.Series) -> pd.Series:
    return np.isclose(a, b, rtol=OHLC_RTOL, atol=OHLC_ATOL, equal_nan=True)


def validate_hour_alignment(
    aligned: pd.DataFrame,
    *,
    expected_m5_count: int = EXPECTED_M5_PER_HOUR,
    max_failures: int = 20,
) -> AlignmentReport:
    """校验 5m 聚合 OHLC 与 1H 是否一致。"""
    df = aligned.copy()
    has_m5 = df["m5_count"].notna()
    sub = df.loc[has_m5].copy()

    open_ok = _price_match(sub["open"], sub["m5_open"])
    high_ok = _price_match(sub["high"], sub["m5_high"])
    low_ok = _price_match(sub["low"], sub["m5_low"])
    close_ok = _price_match(sub["close"], sub["m5_close"])
    vol_ok = _price_match(sub["volume"], sub["m5_volume"])
    ohlc_ok = open_ok & high_ok & low_ok & close_ok
    complete = sub["m5_count"] == expected_m5_count

    failures: list[dict] = []
    bad = sub.loc[~(ohlc_ok & complete)].copy()
    for _, row in bad.head(max_failures).iterrows():
        failures.append(
            {
                "open_time": str(row["open_time"]),
                "m5_count": int(row["m5_count"]),
                "open": (float(row["open"]), float(row["m5_open"])),
                "high": (float(row["high"]), float(row["m5_high"])),
                "low": (float(row["low"]), float(row["m5_low"])),
                "close": (float(row["close"]), float(row["m5_close"])),
                "volume": (float(row["volume"]), float(row["m5_volume"])),
                "m5_range": f"{row['m5_first_time']} ~ {row['m5_last_time']}",
            }
        )

    return AlignmentReport(
        total_1h_bars=len(df),
        with_5m_data=int(has_m5.sum()),
        complete_hours=int(complete.sum()),
        ohlc_all_match=int(ohlc_ok.sum()),
        open_match=int(open_ok.sum()),
        high_match=int(high_ok.sum()),
        low_match=int(low_ok.sum()),
        close_match=int(close_ok.sum()),
        volume_match=int(vol_ok.sum()),
        failures=failures,
    )


def print_alignment_report(report: AlignmentReport) -> None:
    print("================== 5m ↔ 1H 对齐校验 ==================")
    print(f"1H 总数:        {report.total_1h_bars}")
    print(f"有 5m 聚合:     {report.with_5m_data}  ({report.coverage_pct:.2f}%)")
    print(f"完整 12 根 5m:  {report.complete_hours}  ({report.complete_pct:.2f}%)")
    print(f"OHLC 全匹配:    {report.ohlc_all_match}  ({report.ohlc_match_pct:.2f}%)")
    print(f"  open 匹配:    {report.open_match}")
    print(f"  high 匹配:    {report.high_match}")
    print(f"  low  匹配:    {report.low_match}")
    print(f"  close匹配:    {report.close_match}")
    print(f"  volume匹配:   {report.volume_match}")
    status = "通过" if report.passed else "未通过"
    print(f"\n验收 (>99% 完整 & OHLC): {status}")

    if report.failures:
        print(f"\n--- 失败样例（最多 {len(report.failures)} 条）---")
        for f in report.failures:
            print(
                f"  {f['open_time']}  m5_count={f['m5_count']}  "
                f"close 1h={f['close'][0]:.2f} m5={f['close'][1]:.2f}  "
                f"range {f['m5_range']}"
            )
    print("=" * 54)


def _bar_yang_label(yang: bool) -> str:
    return "阳" if yang else "阴"


def compute_intra_features(group_5m: pd.DataFrame) -> pd.Series:
    """单个小时桶内 5m K 线的微观结构特征。"""
    g = group_5m.sort_values("open_time").reset_index(drop=True)
    body_pct = (g["close"] - g["open"]) / g["open"]
    yang = g["close"] > g["open"]
    n = len(g)
    half = n // 2

    high_idx = int(g["high"].to_numpy().argmax())
    low_idx = int(g["low"].to_numpy().argmin())
    bar_high = float(g["high"].max())
    bar_low = float(g["low"].min())
    bar_close = float(g["close"].iloc[-1])
    bar_open = float(g["open"].iloc[0])
    bar_range = bar_high - bar_low

    if bar_range > 0:
        close_strength = (bar_close - bar_low) / bar_range
    else:
        close_strength = np.nan

    if bar_low > 0:
        recovery = (bar_close - bar_low) / bar_low
    else:
        recovery = np.nan

    vol = g["volume"]
    vol_total = float(vol.sum())
    vol_first_half_ratio = float(vol.iloc[:half].sum() / vol_total) if vol_total > 0 and half > 0 else np.nan

    last3 = yang.iloc[-3:] if n >= 3 else yang
    pattern_last3 = "".join(_bar_yang_label(bool(v)) for v in last3)

    return pd.Series(
        {
            "m5_count": n,
            "m5_yang_cnt": int(yang.sum()),
            "m5_yin_cnt": int((~yang).sum()),
            "m5_ret_sum": float(body_pct.sum()),
            "m5_first_half_ret": float(body_pct.iloc[:half].sum()) if half > 0 else 0.0,
            "m5_second_half_ret": float(body_pct.iloc[half:].sum()) if half < n else 0.0,
            "m5_last1_yang": bool(yang.iloc[-1]),
            "m5_last2_yang": bool(yang.iloc[-2:].all()) if n >= 2 else bool(yang.iloc[-1]),
            "m5_last3_yang_cnt": int(yang.iloc[-3:].sum()) if n >= 3 else int(yang.sum()),
            "m5_high_idx": high_idx,
            "m5_low_idx": low_idx,
            "m5_close_strength": close_strength,
            "m5_recovery": recovery,
            "m5_vol_first_half_ratio": vol_first_half_ratio,
            "m5_pattern_last3": pattern_last3,
            "m5_open": bar_open,
            "m5_close": bar_close,
            "m5_high": bar_high,
            "m5_low": bar_low,
            "m5_volume": vol_total,
            "m5_first_time": g["open_time"].iloc[0],
            "m5_last_time": g["open_time"].iloc[-1],
        }
    )


def compute_all_intra_features(df_5m: pd.DataFrame) -> pd.DataFrame:
    """全部 5m 按小时聚合为微观结构特征表（索引列 open_time）。"""
    m5 = df_5m.sort_values("open_time").reset_index(drop=True).copy()
    m5["hour_bucket"] = m5["open_time"].dt.floor("1h")
    features = (
        m5.groupby("hour_bucket", sort=True)
        .apply(compute_intra_features, include_groups=False)
        .reset_index()
        .rename(columns={"hour_bucket": "open_time"})
    )
    features["m5_complete"] = features["m5_count"] == EXPECTED_M5_PER_HOUR
    return features


def enrich_1h_with_intra(
    df_1h: pd.DataFrame,
    df_5m: pd.DataFrame,
    *,
    complete_only: bool = True,
) -> pd.DataFrame:
    """【阶段 3/4】第 t 根 1H + 其 12 根 5m → 预测第 t+1 根（next_bar_up）。

    信号时点：第 t 根 1H 收盘。
    """
    from bnb_quant_v2.analysis.prediction_1h import enrich_bar_features

    intra = compute_all_intra_features(df_5m)
    h1 = enrich_bar_features(df_1h.sort_values("open_time").reset_index(drop=True))
    merged = h1.merge(intra, on="open_time", how="inner")
    if complete_only:
        merged = filter_complete_hours(merged)
    return merged.reset_index(drop=True)


# ---------------------------------------------------------------------------
# p1 + f6 框架（与阶段 3/4 分离）
# p1 = 第 t-1 根 1H 及其 12 根 5m 特征
# f6 = 第 t 根 1H 的前 6 根 5m 特征（信号在第 30 分钟）
# 目标 = hour_up（第 t 根 1H 整根收阳，默认预测目标）
# half2_* 保留供后30分钟实验，非默认
# ---------------------------------------------------------------------------


def compute_first6_features(group_5m: pd.DataFrame) -> pd.Series:
    """当前 1H 内前 6 根 5m 的特征（f6_*）。"""
    g = group_5m.sort_values("open_time").reset_index(drop=True).iloc[:F6_BARS]
    body_pct = (g["close"] - g["open"]) / g["open"]
    yang = g["close"] > g["open"]
    n = len(g)
    pattern = "".join(_bar_yang_label(bool(v)) for v in yang)

    bar_open = float(g["open"].iloc[0]) if n else np.nan
    bar_close = float(g["close"].iloc[-1]) if n else np.nan
    bar_high = float(g["high"].max()) if n else np.nan
    bar_low = float(g["low"].min()) if n else np.nan
    bar_range = bar_high - bar_low if n else np.nan

    if bar_range and bar_range > 0:
        close_strength = (bar_close - bar_low) / bar_range
    else:
        close_strength = np.nan

    if bar_open and bar_open > 0:
        range_hl = bar_range / bar_open
    else:
        range_hl = np.nan

    vol = g["volume"]
    vol_total = float(vol.sum()) if n else 0.0
    if vol_total > 0 and n >= 2:
        vol_last2_ratio = float(vol.iloc[-2:].sum() / vol_total)
        half = n // 2
        vol_first3_ratio = float(vol.iloc[:half].sum() / vol_total) if half > 0 else np.nan
    else:
        vol_last2_ratio = np.nan
        vol_first3_ratio = np.nan

    return pd.Series(
        {
            "f6_count": n,
            "f6_yang_cnt": int(yang.sum()),
            "f6_yin_cnt": int((~yang).sum()),
            "f6_ret_sum": float(body_pct.sum()),
            "f6_all_yang": bool(yang.all()) if n else False,
            "f6_all_yin": bool((~yang).all()) if n else False,
            "f6_last1_yang": bool(yang.iloc[-1]) if n else False,
            "f6_last2_yang": bool(yang.iloc[-2:].all()) if n >= 2 else bool(yang.iloc[-1]) if n else False,
            "f6_pattern": pattern,
            "f6_open": bar_open,
            "f6_close": bar_close,
            "f6_high": bar_high,
            "f6_low": bar_low,
            "f6_range_hl": float(range_hl) if pd.notna(range_hl) else np.nan,
            "f6_close_strength": float(close_strength) if pd.notna(close_strength) else np.nan,
            "f6_volume": vol_total,
            "f6_vol_last2_ratio": vol_last2_ratio,
            "f6_vol_first3_ratio": vol_first3_ratio,
        }
    )


def compute_all_first6_features(df_5m: pd.DataFrame) -> pd.DataFrame:
    """每小时一行 f6_*（仅完整 12 根 5m 的小时）。"""
    m5 = df_5m.sort_values("open_time").reset_index(drop=True).copy()
    m5["hour_bucket"] = m5["open_time"].dt.floor("1h")
    rows: list[pd.Series] = []
    for hour_bucket, grp in m5.groupby("hour_bucket", sort=True):
        if len(grp) < EXPECTED_M5_PER_HOUR:
            continue
        feat = compute_first6_features(grp)
        feat["open_time"] = hour_bucket
        rows.append(feat)
    if not rows:
        return pd.DataFrame(columns=["open_time"])
    out = pd.DataFrame(rows).reset_index(drop=True)
    out["f6_complete"] = out["f6_count"] == F6_BARS
    return out


def compute_half2_features(group_5m: pd.DataFrame) -> pd.Series:
    """当前 1H 后 6 根 5m（:30→:60）标签与回测价格。

    entry_price = 前 6 根最后一根 close（:30 信号价）
    exit_price  = 第 12 根 close（:60 小时收盘）
    half2_up    = exit_price > entry_price
    """
    g = group_5m.sort_values("open_time").reset_index(drop=True)
    if len(g) < EXPECTED_M5_PER_HOUR:
        return pd.Series(
            {
                "half2_count": len(g.iloc[F6_BARS:]) if len(g) > F6_BARS else 0,
                "half2_up": np.nan,
                "half2_ret": np.nan,
                "half2_yang_cnt": np.nan,
                "half2_ret_sum": np.nan,
                "entry_price": np.nan,
                "exit_price": np.nan,
                "l6_open": np.nan,
                "l6_close": np.nan,
            }
        )

    f6 = g.iloc[:F6_BARS]
    l6 = g.iloc[F6_BARS : F6_BARS + L6_BARS]
    entry = float(f6["close"].iloc[-1])
    exit_ = float(g["close"].iloc[-1])
    half2_ret = (exit_ - entry) / entry if entry else np.nan
    body_pct = (l6["close"] - l6["open"]) / l6["open"]
    yang = l6["close"] > l6["open"]

    return pd.Series(
        {
            "half2_count": len(l6),
            "half2_up": bool(exit_ > entry),
            "half2_ret": float(half2_ret),
            "half2_yang_cnt": int(yang.sum()),
            "half2_ret_sum": float(body_pct.sum()),
            "entry_price": entry,
            "exit_price": exit_,
            "l6_open": float(l6["open"].iloc[0]),
            "l6_close": exit_,
        }
    )


def compute_all_half2_features(df_5m: pd.DataFrame) -> pd.DataFrame:
    """每小时一行 half2_*（仅完整 12 根 5m 的小时）。"""
    m5 = df_5m.sort_values("open_time").reset_index(drop=True).copy()
    m5["hour_bucket"] = m5["open_time"].dt.floor("1h")
    rows: list[pd.Series] = []
    for hour_bucket, grp in m5.groupby("hour_bucket", sort=True):
        if len(grp) < EXPECTED_M5_PER_HOUR:
            continue
        feat = compute_half2_features(grp)
        feat["open_time"] = hour_bucket
        rows.append(feat)
    if not rows:
        return pd.DataFrame(columns=["open_time"])
    out = pd.DataFrame(rows).reset_index(drop=True)
    out["half2_complete"] = out["half2_count"] == L6_BARS
    return out


def enrich_p1_f6(
    df_1h: pd.DataFrame,
    df_5m: pd.DataFrame,
    *,
    complete_only: bool = True,
) -> pd.DataFrame:
    """【p1+f6】前一根 1H+5m + 当前小时前 6 根 5m → 预测当前整根 1H（hour_up）。

    时间线（第 t 根为当前行）:
    - p1_* : 第 t-1 根 1H 及其 12 根 5m（shift 自上一行）
    - f6_* : 第 t 根 1H 的前 6 根 5m（:00~:25）
    - gap_hour : 当前 1H 开盘相对前一根 1H 收盘的跳空
    - hour_up : 第 t 根 1H 整根收阳（默认预测目标）
    - half2_* : 后 30 分钟标签（实验用）

    信号时点: open_time + 30min（f6 末根 close）
    """
    base = enrich_1h_with_intra(df_1h, df_5m, complete_only=False)
    f6 = compute_all_first6_features(df_5m)
    half2 = compute_all_half2_features(df_5m)
    out = base.merge(f6, on="open_time", how="inner").merge(
        half2,
        on="open_time",
        how="inner",
        suffixes=("", "_half2dup"),
    )

    for col in P1_SHIFT_COLS:
        if col in out.columns:
            out[f"p1_{col}"] = out[col].shift(1)

    prev_close = out["close"].shift(1)
    out["gap_hour"] = (out["open"] - prev_close) / prev_close
    out["hour_up"] = out["yang"]
    out["signal_at"] = out["open_time"] + pd.Timedelta(minutes=5 * F6_BARS)
    out["exit_at"] = out["open_time"] + pd.Timedelta(hours=1)

    out = out.dropna(subset=["p1_yin", "f6_count", "half2_up"])
    if complete_only:
        out = out.loc[out["m5_count"] == EXPECTED_M5_PER_HOUR].copy()
        out = out.loc[out["f6_count"] == F6_BARS].copy()
        out = out.loc[out["half2_count"] == L6_BARS].copy()
    return out.reset_index(drop=True)


def save_p1_f6_features(df: pd.DataFrame, path: Path | str) -> Path:
    """保存 p1+f6 特征表（与 enrich_1h_with_intra 产物分开存放）。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out


def save_intra_features(df: pd.DataFrame, path: Path | str) -> Path:
    """保存 1H+intra 特征表。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out


def print_intra_feature_summary(df: pd.DataFrame) -> None:
    """打印阶段 3 特征表概览（t → t+1，勿与 p1+f6 混用）。"""
    labeled = df.dropna(subset=["next_bar_up"])
    baseline = float(labeled["next_bar_up"].mean()) if len(labeled) else 0.0
    print("================== 1H + 小时内 5m 特征 ==================")
    print(f"样本: {len(df)} 根  |  基准下一根收涨 {baseline*100:.2f}%")
    print(f"时间: {df['open_time'].min()} ~ {df['open_time'].max()}")
    print(f"m5_count 分布: {dict(df['m5_count'].value_counts().sort_index())}")
    print("\n--- 特征描述统计 ---")
    cols = [
        "m5_yang_cnt",
        "m5_ret_sum",
        "m5_first_half_ret",
        "m5_second_half_ret",
        "m5_close_strength",
        "m5_recovery",
        "m5_vol_first_half_ratio",
    ]
    for col in cols:
        if col in df.columns:
            print(f"  {col:26s} mean={df[col].mean():>8.4f}  median={df[col].median():>8.4f}")
    print("\n--- 尾盘形态（最后3根5m）Top 8 → 下一根收涨率 ---")
    if "m5_pattern_last3" in df.columns and "next_bar_up" in df.columns:
        pat = (
            labeled.groupby("m5_pattern_last3")["next_bar_up"]
            .agg(["count", "mean"])
            .rename(columns={"count": "n", "mean": "up_rate"})
        )
        pat = pat[pat["n"] >= 100].sort_values("up_rate", ascending=False).head(8)
        for idx, row in pat.iterrows():
            print(f"  {idx:<8} n={int(row.n):>5}  下一根涨 {row.up_rate*100:.1f}%")
    print("=" * 54)
