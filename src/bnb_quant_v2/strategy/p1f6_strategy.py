"""p1×f6 策略实现，遵循 Strategy 协议。

统一两套预测框架的接口，使 bar→next_bar 和 p1×f6 策略可互换、可比对。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

import pandas as pd

from bnb_quant_v2.analysis.intra_5m import enrich_p1_f6
from bnb_quant_v2.strategy.base import Strategy, strategy_registry
from bnb_quant_v2.strategy.p1f6_rules import rule_registry


if TYPE_CHECKING:
    from bnb_quant_v2.analysis.evaluator import LiveSignal
    from bnb_quant_v2.strategy.base import Rule


class P1F6Strategy(Strategy):
    """p1×f6 策略：基于上一根 1H 和当前 1H 前 6 根 5m 预测方向。"""

    name = "p1f6"
    description = "p1×f6 量化信号策略：上一根 1H + 当前前6根5m → 当前1H方向"

    def build_features(self, df_1h: pd.DataFrame, df_5m: pd.DataFrame) -> pd.DataFrame:
        """构建 p1×f6 特征表。"""
        return enrich_p1_f6(df_1h, df_5m)

    def evaluate(self, df: pd.DataFrame, rule_name: str) -> pd.Series:
        """评估单条规则。"""
        rule = rule_registry.get(rule_name)
        if rule is None:
            raise ValueError(f"未知规则: {rule_name}")
        return rule.evaluate_batch(df)

    def evaluate_all(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """评估所有启用的规则。"""
        return rule_registry.evaluate_all(df)

    def evaluate_rules(self, df: pd.DataFrame, rule_names: List[str]) -> Dict[str, pd.Series]:
        """评估指定规则列表。"""
        result: Dict[str, pd.Series] = {}
        for name in rule_names:
            rule = rule_registry.get(name)
            if rule is not None and rule.metadata.enabled:
                result[name] = rule.evaluate_batch(df)
        return result

    def evaluate_live_push_rules(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """评估实时推送规则（primary/strict/primary_short/strict_short）。"""
        rules = rule_registry.get_live_push_rules()
        return {rule.metadata.name: rule.evaluate_batch(df) for rule in rules}

    def live_signal_from_row(self, row: pd.Series, rule_name: str) -> "LiveSignal":
        """从特征行构建实时信号。"""
        from bnb_quant_v2.analysis.evaluator import LiveSignal

        rule = rule_registry.get(rule_name)
        if rule is None:
            raise ValueError(f"未知规则: {rule_name}")
        direction = rule.evaluate(row)
        return LiveSignal(
            hour_open_time=row["open_time"],
            rule=rule_name,
            direction=direction,
            prediction="涨" if direction == 1 else "跌" if direction == -1 else "观望",
            f6_yang_cnt=int(row.get("f6_yang_cnt", 0)),
            f6_close_strength=float(row.get("f6_close_strength", 0)),
            f6_ret_sum=float(row.get("f6_ret_sum", 0)),
            p1_candle_type=str(row.get("p1_candle_type", "")),
            p1_yang=bool(row.get("p1_yang", False)),
            p1_yin=bool(row.get("p1_yin", False)),
            entry_price=float(row.get("entry_price", 0)),
            entry_at=row.get("signal_at"),
            exit_at=row.get("exit_at"),
        )


strategy_registry.register(P1F6Strategy())


def get_p1f6_strategy() -> P1F6Strategy:
    """获取 p1×f6 策略实例。"""
    strategy = strategy_registry.get("p1f6")
    if strategy is None:
        raise RuntimeError("p1f6 策略未注册")
    return strategy