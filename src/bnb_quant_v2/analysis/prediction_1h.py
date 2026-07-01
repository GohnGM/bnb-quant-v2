"""单根 1H K 线特征与 bar-t → t+1 方向规则研究（阶段 2）。

与 p1×f6 框架分离：此处预测的是 **下一根** 1H（``next_bar_up``），
而 ``intra_5m.enrich_p1_f6`` 预测的是 **当前根** 1H（``hour_up``）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# 上一根 K 线实体涨跌幅阈值（对比用）
BODY_THRESHOLDS = (0.005, 0.01, 0.015, 0.02, 0.025)


def _classify_candle(df: pd.DataFrame) -> pd.Series:
    """第 t 根 K 线形态（按实体与影线占振幅比例）。"""
    br = df["body_range"]
    ls = df["lower_shadow_range"]
    us = df["upper_shadow_range"]
    yang = df["yang"]
    result = pd.Series("", index=df.index, dtype=object)
    result[br < 0.1] = "十字/纺锤"
    pending = result == ""
    result[pending & (ls > 0.4) & (us < 0.15) & yang] = "锤子(阳)"
    result[pending & (ls > 0.4) & (us < 0.15) & ~yang] = "锤子(阴)"
    pending = result == ""
    result[pending & (us > 0.4) & (ls < 0.15) & yang] = "射击之星(阳)"
    result[pending & (us > 0.4) & (ls < 0.15) & ~yang] = "射击之星(阴)"
    pending = result == ""
    result[pending & (br > 0.6) & yang] = "大阳线"
    result[pending & (br > 0.6) & ~yang] = "大阴线"
    pending = result == ""
    result[pending & yang] = "普通阳线"
    result[pending & ~yang] = "普通阴线"
    return result


@dataclass
class RuleResult:
    name: str
    signals: int
    correct: int
    wrong: int
    accuracy: float
    coverage_pct: float
    predict_up: int
    predict_down: int


@dataclass
class CompareReport:
    baseline_up_rate: float
    total_bars: int
    results: list[RuleResult]


def enrich_bar_features(df: pd.DataFrame) -> pd.DataFrame:
    """第 t 根 K 线特征（实体、影线、形态）。

    默认预测框架：第 t 根收盘后发信号，预测第 t+1 根开→收方向（next_bar_up）。
    """
    out = df.copy()
    out["body"] = out["close"] - out["open"]
    out["body_pct"] = out["body"] / out["open"]
    out["body_abs"] = out["body"].abs()
    out["upper_shadow"] = out["high"] - out[["open", "close"]].max(axis=1)
    out["lower_shadow"] = out[["open", "close"]].min(axis=1) - out["low"]
    out["range"] = out["high"] - out["low"]
    out["yang"] = out["close"] > out["open"]
    out["yin"] = ~out["yang"]
    out["body_range"] = out["body_abs"] / out["range"].replace(0, np.nan)
    out["lower_shadow_range"] = out["lower_shadow"] / out["range"].replace(0, np.nan)
    out["upper_shadow_range"] = out["upper_shadow"] / out["range"].replace(0, np.nan)
    out["lower_shadow_body"] = out["lower_shadow"] / out["body_abs"].replace(0, np.nan)
    out["upper_shadow_body"] = out["upper_shadow"] / out["body_abs"].replace(0, np.nan)
    out["candle_type"] = _classify_candle(out)
    out["bar_up"] = out["yang"]
    out["next_bar_up"] = out["close"].shift(-1) > out["open"].shift(-1)
    return out


def enrich_prev2_features(df: pd.DataFrame) -> pd.DataFrame:
    """前两根 → 预测当前根。

    - 前2 = 第 t-2 根，前1 = 第 t-1 根（均已收盘）
    - 当前 = 第 t 根（预测开→收方向）
    - 在第 t-1 收盘后即可发信号，预测第 t 根
    """
    out = enrich_bar_features(df)
    for lag, prefix in ((1, "p1"), (2, "p2")):
        out[f"{prefix}_yang"] = out["yang"].shift(lag)
        out[f"{prefix}_yin"] = out["yin"].shift(lag)
        out[f"{prefix}_body_pct"] = out["body_pct"].shift(lag)
        out[f"{prefix}_body_range"] = out["body_range"].shift(lag)
        out[f"{prefix}_lower_shadow_range"] = out["lower_shadow_range"].shift(lag)
        out[f"{prefix}_upper_shadow_range"] = out["upper_shadow_range"].shift(lag)
        out[f"{prefix}_lower_shadow_body"] = out["lower_shadow_body"].shift(lag)
        out[f"{prefix}_upper_shadow_body"] = out["upper_shadow_body"].shift(lag)
        out[f"{prefix}_candle_type"] = out["candle_type"].shift(lag)
    out["p2p1_pattern"] = (
        out["p2_yang"].map({True: "阳", False: "阴"})
        + out["p1_yang"].map({True: "阳", False: "阴"})
    )
    out["ret2_pct"] = out["p1_body_pct"] + out["p2_body_pct"]
    return out


def _direction_correct(pred: int, next_up: bool) -> bool:
    return (pred == 1 and next_up) or (pred == -1 and not next_up)


def _eval_rule(
    labeled: pd.DataFrame,
    name: str,
    pred: pd.Series,
    *,
    n_bars: int,
    target_col: str = "next_bar_up",
) -> RuleResult | None:
    mask = pred != 0
    if not mask.any():
        return None
    sub = labeled[mask]
    p = pred.reindex(sub.index)
    hits = sub.apply(
        lambda r, p=p, target_col=target_col: _direction_correct(
            int(p.loc[r.name]), bool(r[target_col])
        ),
        axis=1,
    )
    n = len(sub)
    return RuleResult(
        name=name,
        signals=n,
        correct=int(hits.sum()),
        wrong=int((~hits).sum()),
        accuracy=float(hits.mean()),
        coverage_pct=n / n_bars * 100,
        predict_up=int((p == 1).sum()),
        predict_down=int((p == -1).sum()),
    )


def build_bar_predictions(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """上一根（当根 t）→ 预测下一根（t+1）。"""
    z = pd.Series(0, index=df.index, dtype=int)
    rules: list[tuple[str, pd.Series]] = []

    p = z.copy()
    p.loc[df["yin"]] = 1
    rules.append(("上一根阴 → 预测下一根涨", p.copy()))

    p = z.copy()
    p.loc[df["yang"]] = 1
    rules.append(("上一根阳 → 预测下一根涨", p.copy()))

    p = z.copy()
    p.loc[df["yang"]] = -1
    rules.append(("上一根阳 → 预测下一根跌", p.copy()))

    p = z.copy()
    p.loc[df["yin"]] = -1
    rules.append(("上一根阴 → 预测下一根跌", p.copy()))

    for thr in BODY_THRESHOLDS:
        p = z.copy()
        p.loc[df["body_pct"] <= -thr] = 1
        rules.append((f"上一根跌>={thr*100:.1f}% → 预测下一根涨", p.copy()))

        p = z.copy()
        p.loc[df["body_pct"] >= thr] = -1
        rules.append((f"上一根涨>={thr*100:.1f}% → 预测下一根跌", p.copy()))

    for thr in BODY_THRESHOLDS:
        p = z.copy()
        p.loc[df["body_pct"] <= -thr] = 1
        p.loc[df["body_pct"] >= thr] = -1
        rules.append((f"上一根跌>={thr*100:.1f}%→涨 / 涨>={thr*100:.1f}%→跌", p.copy()))

    return rules


def build_prev2_predictions(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """前两根（t-2, t-1）→ 预测当前根（t）方向。"""
    z = pd.Series(0, index=df.index, dtype=int)
    rules: list[tuple[str, pd.Series]] = []

    for pat, direction in [("阴阴", 1), ("阳阳", -1), ("阳阴", 1), ("阴阳", -1)]:
        label = "涨" if direction == 1 else "跌"
        p = z.copy()
        p.loc[df["p2p1_pattern"] == pat] = direction
        rules.append((f"前2{pat[0]}+前1{pat[1]} → 预测当前{label}", p.copy()))

    for pat, direction in [("阴阴", -1), ("阳阳", 1), ("阳阴", -1), ("阴阳", 1)]:
        label = "涨" if direction == 1 else "跌"
        p = z.copy()
        p.loc[df["p2p1_pattern"] == pat] = direction
        rules.append((f"前2{pat[0]}+前1{pat[1]} (顺势) → 预测当前{label}", p.copy()))

    p = z.copy()
    p.loc[df["p1_yin"] & df["p2_yin"]] = 1
    rules.append(("前两根皆阴 → 预测当前涨", p.copy()))

    p = z.copy()
    p.loc[df["p1_yang"] & df["p2_yang"]] = -1
    rules.append(("前两根皆阳 → 预测当前跌", p.copy()))

    p = z.copy()
    p.loc[df["p1_yang"] & df["p2_yang"]] = 1
    rules.append(("前两根皆阳 → 预测当前涨", p.copy()))

    p = z.copy()
    p.loc[df["p1_yin"] & df["p2_yin"]] = -1
    rules.append(("前两根皆阴 → 预测当前跌", p.copy()))

    for thr in BODY_THRESHOLDS:
        p = z.copy()
        p.loc[df["ret2_pct"] <= -thr] = 1
        rules.append((f"前两根累计跌>={thr*100:.1f}% → 预测当前涨", p.copy()))

        p = z.copy()
        p.loc[df["ret2_pct"] >= thr] = -1
        rules.append((f"前两根累计涨>={thr*100:.1f}% → 预测当前跌", p.copy()))

        p = z.copy()
        p.loc[df["ret2_pct"] <= -thr] = 1
        p.loc[df["ret2_pct"] >= thr] = -1
        rules.append((f"前两根跌>={thr*100:.1f}%→涨 / 涨>={thr*100:.1f}%→跌", p.copy()))

    for thr in BODY_THRESHOLDS:
        p = z.copy()
        p.loc[(df["p1_body_pct"] <= -thr) & (df["p2_body_pct"] <= -thr)] = 1
        rules.append((f"前1跌>={thr*100:.1f}% & 前2跌>={thr*100:.1f}% → 预测当前涨", p.copy()))

        p = z.copy()
        p.loc[(df["p1_body_pct"] >= thr) & (df["p2_body_pct"] >= thr)] = -1
        rules.append((f"前1涨>={thr*100:.1f}% & 前2涨>={thr*100:.1f}% → 预测当前跌", p.copy()))

        p = z.copy()
        p.loc[df["p1_body_pct"] <= -thr] = 1
        rules.append((f"前1跌>={thr*100:.1f}% → 预测当前涨", p.copy()))

        p = z.copy()
        p.loc[df["p1_body_pct"] >= thr] = -1
        rules.append((f"前1涨>={thr*100:.1f}% → 预测当前跌", p.copy()))

        p = z.copy()
        p.loc[df["p2_body_pct"] <= -thr] = 1
        rules.append((f"前2跌>={thr*100:.1f}% → 预测当前涨", p.copy()))

        p = z.copy()
        p.loc[df["p2_body_pct"] >= thr] = -1
        rules.append((f"前2涨>={thr*100:.1f}% → 预测当前跌", p.copy()))

    for ctype, pred_dir, label in [
        ("大阴线", 1, "前1大阴线 → 预测当前涨"),
        ("大阳线", -1, "前1大阳线 → 预测当前跌"),
        ("射击之星(阴)", 1, "前1射击之星(阴) → 预测当前涨"),
        ("大阴线", 1, "前2大阴线 → 预测当前涨"),
        ("大阳线", -1, "前2大阳线 → 预测当前跌"),
    ]:
        prefix = "p1" if label.startswith("前1") else "p2"
        p = z.copy()
        p.loc[df[f"{prefix}_candle_type"] == ctype] = pred_dir
        rules.append((label, p))

    return rules


def build_prev2_shadow_body_predictions(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """前两根影线/实体组合 → 预测当前根方向。"""
    z = pd.Series(0, index=df.index, dtype=int)
    rules: list[tuple[str, pd.Series]] = []

    def add(mask: pd.Series, direction: int, name: str) -> None:
        p = z.copy()
        p.loc[mask] = direction
        rules.append((name, p))

    for p2_ct, p1_ct, direction, name in [
        ("大阴线", "大阴线", 1, "前2大阴+前1大阴 → 预测当前涨"),
        ("大阴线", "射击之星(阴)", 1, "前2大阴+前1射击之星(阴) → 预测当前涨"),
        ("射击之星(阴)", "大阴线", 1, "前2射击之星(阴)+前1大阴 → 预测当前涨"),
        ("射击之星(阴)", "射击之星(阴)", 1, "前2射击之星(阴)+前1射击之星(阴) → 预测当前涨"),
        ("大阳线", "大阳线", -1, "前2大阳+前1大阳 → 预测当前跌"),
        ("大阳线", "射击之星(阳)", -1, "前2大阳+前1射击之星(阳) → 预测当前跌"),
        ("射击之星(阳)", "大阳线", -1, "前2射击之星(阳)+前1大阳 → 预测当前跌"),
        ("阴阴", "大阴线", 1, "前2阴+前1大阴 → 预测当前涨"),
        ("阴阴", "射击之星(阴)", 1, "前2阴+前1射击之星(阴) → 预测当前涨"),
        ("阳阳", "大阳线", -1, "前2阳+前1大阳 → 预测当前跌"),
    ]:
        if p2_ct in ("阴阴", "阳阳"):
            pat = p2_ct
            mask = (df["p2p1_pattern"] == pat) & (df["p1_candle_type"] == p1_ct)
        else:
            mask = (df["p2_candle_type"] == p2_ct) & (df["p1_candle_type"] == p1_ct)
        add(mask, direction, name)

    for ctype, direction, name in [
        ("大阴线", 1, "前1大阴线 → 预测当前涨"),
        ("射击之星(阴)", 1, "前1射击之星(阴) → 预测当前涨"),
        ("大阳线", -1, "前1大阳线 → 预测当前跌"),
        ("射击之星(阳)", -1, "前1射击之星(阳) → 预测当前跌"),
        ("大阴线", 1, "前2大阴线 → 预测当前涨"),
        ("大阳线", -1, "前2大阳线 → 预测当前跌"),
    ]:
        prefix = "p1" if name.startswith("前1") else "p2"
        add(df[f"{prefix}_candle_type"] == ctype, direction, name)

    for thr in (0.3, 0.5):
        add(
            df["p1_yin"] & df["p2_yin"] & (df["p1_body_range"] >= thr) & (df["p2_body_range"] >= thr),
            1,
            f"前2阴+前1阴 & 实体/振幅均>={thr:.0%} → 预测当前涨",
        )
        add(
            df["p1_yang"] & df["p2_yang"] & (df["p1_body_range"] >= thr) & (df["p2_body_range"] >= thr),
            -1,
            f"前2阳+前1阳 & 实体/振幅均>={thr:.0%} → 预测当前跌",
        )
        add(df["p1_yin"] & (df["p1_body_range"] >= thr), 1, f"前1阴 & 实体/振幅>={thr:.0%} → 预测当前涨")
        add(df["p2_yin"] & (df["p2_body_range"] >= thr), 1, f"前2阴 & 实体/振幅>={thr:.0%} → 预测当前涨")
        add(df["p1_yang"] & (df["p1_body_range"] >= thr), -1, f"前1阳 & 实体/振幅>={thr:.0%} → 预测当前跌")
        add(df["p2_yang"] & (df["p2_body_range"] >= thr), -1, f"前2阳 & 实体/振幅>={thr:.0%} → 预测当前跌")

    for thr in (0.25, 0.4):
        add(
            df["p1_yin"] & df["p2_yin"] & (df["p1_lower_shadow_range"] < thr),
            1,
            f"前2阴+前1阴 & 前1短下影<{thr:.0%} → 预测当前涨",
        )
        add(
            df["p1_yin"] & df["p2_yin"] & (df["p1_lower_shadow_range"] >= thr),
            1,
            f"前2阴+前1阴 & 前1下影/振幅>={thr:.0%} → 预测当前涨",
        )
        add(
            df["p1_yang"] & df["p2_yang"] & (df["p1_upper_shadow_range"] >= thr),
            -1,
            f"前2阳+前1阳 & 前1上影/振幅>={thr:.0%} → 预测当前跌",
        )

    for thr in SHADOW_BODY_THRESHOLDS[:4]:
        add(
            df["p1_yin"] & df["p2_yin"] & (df["p1_lower_shadow_body"] >= thr),
            1,
            f"前2阴+前1阴 & 前1下影/实体>={thr:.1f} → 预测当前涨",
        )
        add(
            df["p1_yang"] & df["p2_yang"] & (df["p1_upper_shadow_body"] >= thr),
            -1,
            f"前2阳+前1阳 & 前1上影/实体>={thr:.1f} → 预测当前跌",
        )

    add(
        df["p1_yin"]
        & df["p2_yin"]
        & (df["p1_candle_type"].isin(["大阴线", "射击之星(阴)"])),
        1,
        "前2阴+前1阴 & 前1大阴或射击之星(阴) → 预测当前涨",
    )
    add(
        df["p1_yang"]
        & df["p2_yang"]
        & (df["p1_candle_type"].isin(["大阳线", "射击之星(阳)"])),
        -1,
        "前2阳+前1阳 & 前1大阳或射击之星(阳) → 预测当前跌",
    )
    add(
        df["p2_yin"]
        & df["p1_yin"]
        & (df["p2_candle_type"].isin(["大阴线", "射击之星(阴)"])),
        1,
        "前2阴+前1阴 & 前2大阴或射击之星(阴) → 预测当前涨",
    )

    return rules


SHADOW_BODY_THRESHOLDS = (0.3, 0.5, 0.7, 1.0, 1.5, 2.0)
RANGE_THRESHOLDS = (0.25, 0.4, 0.6)


def build_shadow_body_predictions(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """第 t 根影线/实体 → 预测第 t+1 根方向。"""
    z = pd.Series(0, index=df.index, dtype=int)
    rules: list[tuple[str, pd.Series]] = []

    for ctype, pred_dir, label in [
        ("大阴线", 1, "大阴线 → 预测下一根涨"),
        ("大阳线", -1, "大阳线 → 预测下一根跌"),
        ("射击之星(阴)", 1, "射击之星(阴) → 预测下一根涨"),
        ("射击之星(阳)", -1, "射击之星(阳) → 预测下一根跌"),
        ("锤子(阴)", 1, "锤子(阴) → 预测下一根涨"),
        ("锤子(阳)", 1, "锤子(阳) → 预测下一根涨"),
        ("十字/纺锤", 1, "十字/纺锤 → 预测下一根涨"),
    ]:
        p = z.copy()
        p.loc[df["candle_type"] == ctype] = pred_dir
        rules.append((label, p))

    for thr in (0.3, 0.5):
        p = z.copy()
        p.loc[df["yin"] & (df["body_range"] >= thr)] = 1
        rules.append((f"实体/振幅>={thr:.0%} & 阴 → 预测下一根涨", p.copy()))

        p = z.copy()
        p.loc[df["yang"] & (df["body_range"] >= thr)] = -1
        rules.append((f"实体/振幅>={thr:.0%} & 阳 → 预测下一根跌", p.copy()))

    for thr in SHADOW_BODY_THRESHOLDS:
        p = z.copy()
        p.loc[df["yin"] & (df["lower_shadow_body"] >= thr)] = 1
        rules.append((f"下影/实体>={thr:.1f} & 阴 → 预测下一根涨", p.copy()))

        p = z.copy()
        p.loc[df["yang"] & (df["upper_shadow_body"] >= thr)] = -1
        rules.append((f"上影/实体>={thr:.1f} & 阳 → 预测下一根跌", p.copy()))

    for thr in RANGE_THRESHOLDS:
        p = z.copy()
        p.loc[df["yin"] & (df["lower_shadow_range"] >= thr)] = 1
        rules.append((f"下影/振幅>={thr:.0%} & 阴 → 预测下一根涨", p.copy()))

        p = z.copy()
        p.loc[df["yang"] & (df["upper_shadow_range"] >= thr)] = -1
        rules.append((f"上影/振幅>={thr:.0%} & 阳 → 预测下一根跌", p.copy()))

    return rules


@dataclass
class CandleTypeStat:
    candle_type: str
    count: int
    next_up_rate: float


@dataclass
class BucketStat:
    label: str
    count: int
    next_up_rate: float


@dataclass
class ShadowBodyReport:
    baseline_up_rate: float
    total_bars: int
    candle_types: list[CandleTypeStat]
    lower_shadow_buckets: list[BucketStat]
    body_range_buckets: list[BucketStat]
    results: list[RuleResult]


@dataclass
class PairCandleStat:
    p2_type: str
    p1_type: str
    count: int
    bar_up_rate: float


@dataclass
class Prev2ShadowBodyReport:
    baseline_up_rate: float
    total_bars: int
    pair_candle_types: list[PairCandleStat]
    p1_lower_shadow_buckets: list[BucketStat]
    p1_body_range_buckets: list[BucketStat]
    results: list[RuleResult]


def compare_prev2_shadow_body_rules(
    df_1h: pd.DataFrame, *, verbose: bool = True
) -> Prev2ShadowBodyReport:
    """前两根影线/实体组合 → 当前根方向。"""
    df = enrich_prev2_features(df_1h)
    labeled = df.dropna(subset=["bar_up", "p1_yang", "p2_yang", "p1_body_range"]).copy()
    n_bars = len(labeled)
    baseline = float(labeled["bar_up"].mean())

    pair_candle_types: list[PairCandleStat] = []
    labeled["_pair"] = labeled["p2_candle_type"] + "+" + labeled["p1_candle_type"]
    for pair, grp in labeled.groupby("_pair", sort=False):
        parts = str(pair).split("+", 1)
        pair_candle_types.append(
            PairCandleStat(
                p2_type=parts[0],
                p1_type=parts[1] if len(parts) > 1 else "",
                count=len(grp),
                bar_up_rate=float(grp["bar_up"].mean()),
            )
        )
    pair_candle_types = [p for p in pair_candle_types if p.count >= 30]
    pair_candle_types.sort(key=lambda x: x.bar_up_rate, reverse=True)

    p1_lower_shadow_buckets = _bucket_rate(
        labeled,
        labeled["p1_lower_shadow_range"],
        "bar_up",
        [
            (0.0, 0.1, "前1短下影 0-10%"),
            (0.1, 0.25, "前1下影 10-25%"),
            (0.25, 0.4, "前1下影 25-40%"),
            (0.4, 0.6, "前1下影 40-60%"),
            (0.6, 1.01, "前1长下影 60%+"),
        ],
        extra_mask=labeled["p1_yin"] & labeled["p2_yin"],
    )
    p1_body_range_buckets = _bucket_rate(
        labeled,
        labeled["p1_body_range"],
        "bar_up",
        [
            (0.0, 0.1, "前1小实体 <10%"),
            (0.1, 0.3, "前1实体 10-30%"),
            (0.3, 0.5, "前1实体 30-50%"),
            (0.5, 0.7, "前1实体 50-70%"),
            (0.7, 1.01, "前1大实体 70%+"),
        ],
        extra_mask=labeled["p1_yin"] & labeled["p2_yin"],
    )

    results: list[RuleResult] = []
    for name, pred in build_prev2_shadow_body_predictions(labeled):
        row = _eval_rule(labeled, name, pred, n_bars=n_bars, target_col="bar_up")
        if row and row.signals >= 20:
            results.append(row)
    results.sort(key=lambda r: r.accuracy, reverse=True)

    report = Prev2ShadowBodyReport(
        baseline_up_rate=baseline,
        total_bars=n_bars,
        pair_candle_types=pair_candle_types,
        p1_lower_shadow_buckets=p1_lower_shadow_buckets,
        p1_body_range_buckets=p1_body_range_buckets,
        results=results,
    )
    if verbose:
        _print_prev2_shadow_body(report)
    return report


def compare_shadow_body_rules(df_1h: pd.DataFrame, *, verbose: bool = True) -> ShadowBodyReport:
    """第 t 根影线/实体特征 → 第 t+1 根方向。"""
    df = enrich_bar_features(df_1h)
    labeled = df.dropna(subset=["next_bar_up"]).copy()
    n_bars = len(labeled)
    baseline = float(labeled["next_bar_up"].mean())

    candle_types: list[CandleTypeStat] = []
    for ctype, grp in labeled.groupby("candle_type", sort=False):
        candle_types.append(
            CandleTypeStat(
                candle_type=str(ctype),
                count=len(grp),
                next_up_rate=float(grp["next_bar_up"].mean()),
            )
        )
    candle_types.sort(key=lambda x: x.next_up_rate, reverse=True)

    lower_shadow_buckets = _bucket_next_up(
        labeled,
        labeled["lower_shadow_range"],
        [
            (0.0, 0.1, "短下影 0-10%"),
            (0.1, 0.25, "下影 10-25%"),
            (0.25, 0.4, "下影 25-40%"),
            (0.4, 0.6, "下影 40-60%"),
            (0.6, 1.01, "长下影 60%+"),
        ],
    )
    body_range_buckets = _bucket_next_up(
        labeled,
        labeled["body_range"],
        [
            (0.0, 0.1, "小实体 <10%"),
            (0.1, 0.3, "实体 10-30%"),
            (0.3, 0.5, "实体 30-50%"),
            (0.5, 0.7, "实体 50-70%"),
            (0.7, 1.01, "大实体 70%+"),
        ],
    )

    results: list[RuleResult] = []
    for name, pred in build_shadow_body_predictions(labeled):
        row = _eval_rule(labeled, name, pred, n_bars=n_bars)
        if row and row.signals >= 20:
            results.append(row)
    results.sort(key=lambda r: r.accuracy, reverse=True)

    report = ShadowBodyReport(
        baseline_up_rate=baseline,
        total_bars=n_bars,
        candle_types=candle_types,
        lower_shadow_buckets=lower_shadow_buckets,
        body_range_buckets=body_range_buckets,
        results=results,
    )
    if verbose:
        _print_shadow_body(report)
    return report


def _bucket_next_up(
    labeled: pd.DataFrame,
    values: pd.Series,
    edges: list[tuple[float, float, str]],
) -> list[BucketStat]:
    return _bucket_rate(labeled, values, "next_bar_up", edges)


def _bucket_rate(
    labeled: pd.DataFrame,
    values: pd.Series,
    target_col: str,
    edges: list[tuple[float, float, str]],
    *,
    extra_mask: pd.Series | None = None,
) -> list[BucketStat]:
    out: list[BucketStat] = []
    for lo, hi, label in edges:
        mask = (values >= lo) & (values < hi)
        if extra_mask is not None:
            mask = mask & extra_mask
        if not mask.any():
            continue
        out.append(
            BucketStat(
                label=label,
                count=int(mask.sum()),
                next_up_rate=float(labeled.loc[mask, target_col].mean()),
            )
        )
    return out


def compare_prev2_rules(df_1h: pd.DataFrame, *, verbose: bool = True) -> CompareReport:
    """对比：前两根 K 线 → 当前 K 线方向。"""
    df = enrich_prev2_features(df_1h)
    labeled = df.dropna(subset=["bar_up", "p1_yang", "p2_yang"]).copy()
    n_bars = len(labeled)
    baseline = float(labeled["bar_up"].mean())

    results: list[RuleResult] = []
    for name, pred in build_prev2_predictions(labeled):
        row = _eval_rule(labeled, name, pred, n_bars=n_bars, target_col="bar_up")
        if row:
            results.append(row)

    results.sort(key=lambda r: r.accuracy, reverse=True)
    report = CompareReport(baseline_up_rate=baseline, total_bars=n_bars, results=results)

    if verbose:
        _print_prev2_compare(report)

    return report


def compare_prev1_rules(df_1h: pd.DataFrame, *, verbose: bool = True) -> CompareReport:
    """对比：上一根 K 线 → 下一根 K 线方向。"""
    df = enrich_bar_features(df_1h)
    labeled = df.dropna(subset=["next_bar_up"]).copy()
    n_bars = len(labeled)
    baseline = float(labeled["next_bar_up"].mean())

    results: list[RuleResult] = []
    for name, pred in build_bar_predictions(labeled):
        row = _eval_rule(labeled, name, pred, n_bars=n_bars)
        if row:
            results.append(row)

    results.sort(key=lambda r: r.accuracy, reverse=True)
    report = CompareReport(baseline_up_rate=baseline, total_bars=n_bars, results=results)

    if verbose:
        _print_compare(report)

    return report


def analyze_1h_prediction(
    df_1h: pd.DataFrame,
    *,
    rule_name: str | None = None,
    prev_bars: int = 1,
    verbose: bool = True,
) -> RuleResult | CompareReport:
    if prev_bars == 2:
        report = compare_prev2_rules(df_1h, verbose=False)
        print_fn = _print_prev2_compare
    elif prev_bars == 1:
        report = compare_prev1_rules(df_1h, verbose=False)
        print_fn = _print_compare
    else:
        raise ValueError(f"仅支持 prev_bars=1 或 2，收到 {prev_bars}")
    if rule_name is None:
        if verbose:
            print_fn(report)
        return report
    for r in report.results:
        if r.name == rule_name:
            if verbose:
                _print_single(r, report.baseline_up_rate, report.total_bars, prev_bars=prev_bars)
            return r
    raise ValueError(f"未知规则: {rule_name!r}")


def _print_compare(report: CompareReport) -> None:
    blind = max(report.baseline_up_rate, 1 - report.baseline_up_rate)
    print("================== 上一根 K 线 → 下一根 K 线 ==================")
    print("说明: 上一根 = 当根刚收盘的第 t 根；下一根 = 第 t+1 根开→收方向")
    print(f"样本: {report.total_bars} 根  |  基准下一根收涨 {report.baseline_up_rate*100:.2f}%")
    print(f"盲猜上限 {blind*100:.2f}%\n")
    print(f"{'规则':<46} {'信号':>6} {'覆盖率':>7} {'对':>5} {'错':>5} {'准确率':>8}")
    print("-" * 84)
    for r in report.results:
        print(
            f"{r.name:<46} {r.signals:>6} {r.coverage_pct:>6.1f}% "
            f"{r.correct:>5} {r.wrong:>5} {r.accuracy*100:>7.2f}%"
        )
    print("=" * 84)


def _print_prev2_compare(report: CompareReport) -> None:
    blind = max(report.baseline_up_rate, 1 - report.baseline_up_rate)
    print("================== 前两根 K 线 → 当前 K 线 ==================")
    print("说明: 前2=第 t-2 根，前1=第 t-1 根；当前=第 t 根开→收方向")
    print("信号时点: 第 t-1 根收盘后，预测第 t 根")
    print(f"样本: {report.total_bars} 根  |  基准当前收涨 {report.baseline_up_rate*100:.2f}%")
    print(f"盲猜上限 {blind*100:.2f}%\n")
    print(f"{'规则':<46} {'信号':>6} {'覆盖率':>7} {'对':>5} {'错':>5} {'准确率':>8}")
    print("-" * 84)
    for r in report.results:
        print(
            f"{r.name:<46} {r.signals:>6} {r.coverage_pct:>6.1f}% "
            f"{r.correct:>5} {r.wrong:>5} {r.accuracy*100:>7.2f}%"
        )
    print("=" * 84)


def _print_shadow_body(report: ShadowBodyReport) -> None:
    blind = max(report.baseline_up_rate, 1 - report.baseline_up_rate)
    print("================== 第 t 根影线/实体 → 第 t+1 根方向 ==================")
    print("说明: 特征均来自第 t 根（上一根刚收盘）；目标为第 t+1 根开→收方向")
    print(f"样本: {report.total_bars} 根  |  基准下一根收涨 {report.baseline_up_rate*100:.2f}%")
    print(f"盲猜上限 {blind*100:.2f}%\n")

    print("--- 第 t 根形态 → 下一根收涨率（描述性，非预测规则）---")
    print(f"{'形态':<14} {'数量':>6} {'下一根涨':>8}")
    for ct in report.candle_types:
        print(f"{ct.candle_type:<14} {ct.count:>6} {ct.next_up_rate*100:>7.2f}%")

    print("\n--- 下影占振幅分桶 → 下一根收涨率 ---")
    for b in report.lower_shadow_buckets:
        print(f"  {b.label:<16} n={b.count:>5}  下一根涨 {b.next_up_rate*100:.1f}%")

    print("\n--- 实体占振幅分桶 → 下一根收涨率 ---")
    for b in report.body_range_buckets:
        print(f"  {b.label:<16} n={b.count:>5}  下一根涨 {b.next_up_rate*100:.1f}%")

    print("\n--- 影线/实体预测规则（按准确率）---")
    print(f"{'规则':<46} {'信号':>6} {'覆盖率':>7} {'对':>5} {'错':>5} {'准确率':>8}")
    print("-" * 84)
    for r in report.results:
        print(
            f"{r.name:<46} {r.signals:>6} {r.coverage_pct:>6.1f}% "
            f"{r.correct:>5} {r.wrong:>5} {r.accuracy*100:>7.2f}%"
        )
    print("=" * 84)


def _print_prev2_shadow_body(report: Prev2ShadowBodyReport) -> None:
    blind = max(report.baseline_up_rate, 1 - report.baseline_up_rate)
    print("================== 前两根影线/实体 → 当前 K 线 ==================")
    print("说明: 前2=第 t-2 根，前1=第 t-1 根；当前=第 t 根开→收方向")
    print(f"样本: {report.total_bars} 根  |  基准当前收涨 {report.baseline_up_rate*100:.2f}%")
    print(f"盲猜上限 {blind*100:.2f}%\n")

    print("--- 前2形态+前1形态 → 当前收涨率（n≥30，描述性）---")
    print(f"{'前2':<14} {'前1':<14} {'数量':>6} {'当前涨':>8}")
    for p in report.pair_candle_types[:15]:
        print(f"{p.p2_type:<14} {p.p1_type:<14} {p.count:>6} {p.bar_up_rate*100:>7.2f}%")
    if len(report.pair_candle_types) > 15:
        print(f"  ... 共 {len(report.pair_candle_types)} 种组合")
    print("\n--- 末15种（当前涨率最低）---")
    for p in report.pair_candle_types[-8:]:
        print(f"{p.p2_type:<14} {p.p1_type:<14} {p.count:>6} {p.bar_up_rate*100:>7.2f}%")

    print("\n--- 前2阴+前1阴时：前1下影占振幅 → 当前收涨率 ---")
    for b in report.p1_lower_shadow_buckets:
        print(f"  {b.label:<20} n={b.count:>5}  当前涨 {b.next_up_rate*100:.1f}%")

    print("\n--- 前2阴+前1阴时：前1实体占振幅 → 当前收涨率 ---")
    for b in report.p1_body_range_buckets:
        print(f"  {b.label:<20} n={b.count:>5}  当前涨 {b.next_up_rate*100:.1f}%")

    print("\n--- 前两根影线/实体组合预测规则（按准确率）---")
    print(f"{'规则':<52} {'信号':>6} {'覆盖率':>7} {'对':>5} {'错':>5} {'准确率':>8}")
    print("-" * 90)
    for r in report.results:
        print(
            f"{r.name:<52} {r.signals:>6} {r.coverage_pct:>6.1f}% "
            f"{r.correct:>5} {r.wrong:>5} {r.accuracy*100:>7.2f}%"
        )
    print("=" * 90)


def _print_single(r: RuleResult, baseline: float, n_bars: int, *, prev_bars: int = 1) -> None:
    blind = max(baseline, 1 - baseline)
    if prev_bars == 2:
        title = "前两根 → 当前"
    else:
        title = "上一根 → 下一根"
    print(f"================== {title} ==================")
    print(f"规则: {r.name}")
    print(f"信号: {r.signals}  (覆盖率 {r.coverage_pct:.1f}%)  涨{r.predict_up} / 跌{r.predict_down}")
    print(f"方向正确: {r.correct}  错误: {r.wrong}")
    print(f"准确率: {r.accuracy*100:.2f}%  (vs 盲猜 +{(r.accuracy-blind)*100:.2f}pp)")
    print("=" * 54)
