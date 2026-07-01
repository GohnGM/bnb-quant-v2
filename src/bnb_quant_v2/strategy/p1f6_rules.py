"""p1×f6 策略的规则实现。

每条规则是一个独立类，通过 ``@rule_registry.register_decorator`` 注册。
回测和实时评估都从 registry 查询规则，确保规则单一来源。
"""
from __future__ import annotations

import pandas as pd

from bnb_quant_v2.analysis.intra_5m import (
    F6_CLOSE_STRENGTH_MIN,
    F6_RANGE_HL_MIN,
    F6_RET_STRONG,
)
from bnb_quant_v2.strategy.base import BaseRule, rule_registry


PRIMARY_HOUR_RULE = "p1大阴 & f6阳>=4 & f6收盘强>=67% → 1H涨"
STRICT_HOUR_RULE = "p1大阴 & f6阳>=4 & f6涨>0.2% & f6收盘强 → 1H涨"
PRIMARY_HOUR_SHORT_RULE = "p1大阳 & f6阴>=4 & f6收盘弱<=33% → 1H跌"
STRICT_HOUR_SHORT_RULE = "p1大阳 & f6阴>=4 & f6跌>0.2% & f6收盘弱 → 1H跌"


register = rule_registry.register_decorator


@register(
    name="p1大阴 & f6阳>=4 & f6收盘强>=67% → 1H涨",
    tier="primary",
    risk="medium",
    description="主规则做多，约 84% / ~30 笔·月",
)
class PrimaryHourRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if (
            row["p1_candle_type"] == "大阴线"
            and row["f6_yang_cnt"] >= 4
            and row["f6_close_strength"] >= F6_CLOSE_STRENGTH_MIN
        ):
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[
            (df["p1_candle_type"] == "大阴线")
            & (df["f6_yang_cnt"] >= 4)
            & (df["f6_close_strength"] >= F6_CLOSE_STRENGTH_MIN)
        ] = 1
        return z


@register(
    name="p1大阴 & f6阳>=4 → 1H涨",
    tier="other",
    risk="medium",
    description="宽松版主规则",
)
class LooseHourRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_candle_type"] == "大阴线" and row["f6_yang_cnt"] >= 4:
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[(df["p1_candle_type"] == "大阴线") & (df["f6_yang_cnt"] >= 4)] = 1
        return z


@register(
    name="f6阳>=4→1H涨 / f6阳<=2→1H跌",
    tier="other",
    risk="low",
    description="仅基于 f6 阳线数量的规则",
)
class F6YangCountRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["f6_yang_cnt"] >= 4:
            return 1
        if row["f6_yang_cnt"] <= 2:
            return -1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[df["f6_yang_cnt"] >= 4] = 1
        z.loc[df["f6_yang_cnt"] <= 2] = -1
        return z


@register(
    name="f6皆阳→1H涨 / f6皆阴→1H跌",
    tier="other",
    risk="low",
    description="极端情况规则",
)
class F6AllRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["f6_all_yang"]:
            return 1
        if row["f6_all_yin"]:
            return -1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[df["f6_all_yang"]] = 1
        z.loc[df["f6_all_yin"]] = -1
        return z


@register(
    name="p1阴&f6阳>=4涨 / p1阳&f6阳<=2跌",
    tier="other",
    risk="medium",
    description="p1方向 + f6阳线数量",
)
class P1F6ComboRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_yin"] and row["f6_yang_cnt"] >= 4:
            return 1
        if row["p1_yang"] and row["f6_yang_cnt"] <= 2:
            return -1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[df["p1_yin"] & (df["f6_yang_cnt"] >= 4)] = 1
        z.loc[df["p1_yang"] & (df["f6_yang_cnt"] <= 2)] = -1
        return z


@register(
    name="p1大阴 & f6前30分累计涨 → 1H涨",
    tier="other",
    risk="medium",
    description="基于 f6 累计涨幅",
)
class P1BigYinF6RetRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_candle_type"] == "大阴线" and row["f6_ret_sum"] > 0:
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[(df["p1_candle_type"] == "大阴线") & (df["f6_ret_sum"] > 0)] = 1
        return z


@register(
    name="p1阴 & f6最后2根皆阳 → 1H涨",
    tier="other",
    risk="medium",
    description="p1阴 + f6尾盘强度",
)
class P1YinF6Last2Rule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_yin"] and row["f6_last2_yang"]:
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[df["p1_yin"] & df["f6_last2_yang"]] = 1
        return z


@register(
    name="p1尾盘阴阴阴 & f6非皆阴 → 1H涨",
    tier="other",
    risk="medium",
    description="p1尾盘模式",
)
class P1PatternLast3Rule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_m5_pattern_last3"] == "阴阴阴" and not row["f6_all_yin"]:
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[(df["p1_m5_pattern_last3"] == "阴阴阴") & ~df["f6_all_yin"]] = 1
        return z


@register(
    name="p1大阴 & f6阳>=4 & f6涨>0.2% → 1H涨",
    tier="other",
    risk="medium",
    description="加严规则：增加涨幅阈值",
)
class StrictF6RetRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if (
            row["p1_candle_type"] == "大阴线"
            and row["f6_yang_cnt"] >= 4
            and row["f6_ret_sum"] > F6_RET_STRONG
        ):
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[
            (df["p1_candle_type"] == "大阴线")
            & (df["f6_yang_cnt"] >= 4)
            & (df["f6_ret_sum"] > F6_RET_STRONG)
        ] = 1
        return z


@register(
    name="p1大阴 & f6阳5-6 → 1H涨",
    tier="other",
    risk="medium",
    description="f6阳线数量更严格",
)
class StrictF6CountRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_candle_type"] == "大阴线" and row["f6_yang_cnt"] in (5, 6):
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[(df["p1_candle_type"] == "大阴线") & df["f6_yang_cnt"].isin([5, 6])] = 1
        return z


@register(
    name="p1大阴 & f6阳5-6 & f6收盘强>=67% → 1H涨",
    tier="other",
    risk="high",
    description="加严规则：阳线数量 + 收盘强度",
)
class StrictF6CountStrengthRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if (
            row["p1_candle_type"] == "大阴线"
            and row["f6_yang_cnt"] in (5, 6)
            and row["f6_close_strength"] >= F6_CLOSE_STRENGTH_MIN
        ):
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[
            (df["p1_candle_type"] == "大阴线")
            & df["f6_yang_cnt"].isin([5, 6])
            & (df["f6_close_strength"] >= F6_CLOSE_STRENGTH_MIN)
        ] = 1
        return z


@register(
    name="p1大阴 & f6阳>=4 & f6振幅>=0.4% → 1H涨",
    tier="other",
    risk="medium",
    description="加严规则：增加振幅阈值",
)
class StrictF6RangeRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if (
            row["p1_candle_type"] == "大阴线"
            and row["f6_yang_cnt"] >= 4
            and row["f6_range_hl"] >= F6_RANGE_HL_MIN
        ):
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[
            (df["p1_candle_type"] == "大阴线")
            & (df["f6_yang_cnt"] >= 4)
            & (df["f6_range_hl"] >= F6_RANGE_HL_MIN)
        ] = 1
        return z


@register(
    name="p1大阴 & f6阳>=4 & f6涨>0.2% & f6收盘强 → 1H涨",
    tier="strict",
    risk="high",
    description="严格规则做多，约 91.5% / ~2.4% 覆盖",
)
class StrictHourRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if (
            row["p1_candle_type"] == "大阴线"
            and row["f6_yang_cnt"] >= 4
            and row["f6_ret_sum"] > F6_RET_STRONG
            and row["f6_close_strength"] >= F6_CLOSE_STRENGTH_MIN
        ):
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[
            (df["p1_candle_type"] == "大阴线")
            & (df["f6_yang_cnt"] >= 4)
            & (df["f6_ret_sum"] > F6_RET_STRONG)
            & (df["f6_close_strength"] >= F6_CLOSE_STRENGTH_MIN)
        ] = 1
        return z


@register(
    name="p1大阳 & f6阴>=4 & f6收盘弱<=33% → 1H跌",
    tier="primary_short",
    risk="medium",
    description="主规则做空，约 83% / ~31 笔·月",
)
class PrimaryHourShortRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if (
            row["p1_candle_type"] == "大阳线"
            and row["f6_yin_cnt"] >= 4
            and row["f6_close_strength"] <= (1 - F6_CLOSE_STRENGTH_MIN)
        ):
            return -1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[
            (df["p1_candle_type"] == "大阳线")
            & (df["f6_yin_cnt"] >= 4)
            & (df["f6_close_strength"] <= (1 - F6_CLOSE_STRENGTH_MIN))
        ] = -1
        return z


@register(
    name="p1大阳 & f6阴>=4 & f6跌>0.2% & f6收盘弱 → 1H跌",
    tier="strict_short",
    risk="high",
    description="严格规则做空，约 92% / ~16 笔·月",
)
class StrictHourShortRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if (
            row["p1_candle_type"] == "大阳线"
            and row["f6_yin_cnt"] >= 4
            and row["f6_ret_sum"] < -F6_RET_STRONG
            and row["f6_close_strength"] <= (1 - F6_CLOSE_STRENGTH_MIN)
        ):
            return -1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[
            (df["p1_candle_type"] == "大阳线")
            & (df["f6_yin_cnt"] >= 4)
            & (df["f6_ret_sum"] < -F6_RET_STRONG)
            & (df["f6_close_strength"] <= (1 - F6_CLOSE_STRENGTH_MIN))
        ] = -1
        return z


# --- half2 规则（预测后 30 分钟涨跌）---

@register(
    name="p1大阴 & f6阳>=4 → 后半涨",
    tier="half2",
    risk="medium",
    description="half2 主规则：p1大阴 + f6阳>=4 → 后半涨",
)
class Half2PrimaryRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_candle_type"] == "大阴线" and row["f6_yang_cnt"] >= 4:
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[(df["p1_candle_type"] == "大阴线") & (df["f6_yang_cnt"] >= 4)] = 1
        return z


@register(
    name="f6皆阳→后半涨 / f6皆阴→后半跌",
    tier="half2",
    risk="low",
    description="half2 极端情况规则",
)
class Half2AllRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["f6_all_yang"]:
            return 1
        if row["f6_all_yin"]:
            return -1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[df["f6_all_yang"]] = 1
        z.loc[df["f6_all_yin"]] = -1
        return z


@register(
    name="p1阴&f6阳>=4涨 / p1阳&f6阳<=2跌",
    tier="half2",
    risk="medium",
    description="half2 p1方向 + f6阳线数量",
)
class Half2P1F6ComboRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_yin"] and row["f6_yang_cnt"] >= 4:
            return 1
        if row["p1_yang"] and row["f6_yang_cnt"] <= 2:
            return -1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[df["p1_yin"] & (df["f6_yang_cnt"] >= 4)] = 1
        z.loc[df["p1_yang"] & (df["f6_yang_cnt"] <= 2)] = -1
        return z


@register(
    name="p1大阴 & f6前30分累计涨 → 后半涨",
    tier="half2",
    risk="medium",
    description="half2 基于 f6 累计涨幅",
)
class Half2P1BigYinF6RetRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_candle_type"] == "大阴线" and row["f6_ret_sum"] > 0:
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[(df["p1_candle_type"] == "大阴线") & (df["f6_ret_sum"] > 0)] = 1
        return z


@register(
    name="p1阴 & f6最后2根皆阳 → 后半涨",
    tier="half2",
    risk="medium",
    description="half2 p1阴 + f6尾盘强度",
)
class Half2P1YinF6Last2Rule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_yin"] and row["f6_last2_yang"]:
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[df["p1_yin"] & df["f6_last2_yang"]] = 1
        return z


@register(
    name="p1尾盘阴阴阴 & f6非皆阴 → 后半涨",
    tier="half2",
    risk="medium",
    description="half2 p1尾盘模式",
)
class Half2P1PatternLast3Rule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["p1_m5_pattern_last3"] == "阴阴阴" and not row["f6_all_yin"]:
            return 1
        return 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        z = pd.Series(0, index=df.index, dtype=int)
        z.loc[(df["p1_m5_pattern_last3"] == "阴阴阴") & ~df["f6_all_yin"]] = 1
        return z