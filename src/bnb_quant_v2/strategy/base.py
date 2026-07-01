"""策略抽象层：Rule 协议、Strategy 协议、RuleRegistry。

规则注册表模式（Rule Registry Pattern）
--------------------------------------
- 每条规则是一个独立类，实现 ``Rule`` 协议
- 通过 ``@rule_registry.register()`` 装饰器注册
- 回测和实时评估都从 registry 查询规则

Strategy 协议（统一预测框架）
---------------------------
- ``build_features()`` — 构建特征表
- ``evaluate()`` — 评估单条规则
- ``evaluate_all()`` — 评估所有规则
- 使 bar→next_bar 和 p1×f6 策略可互换、可比对
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, List, Optional, Protocol, Type, TypeVar

import pandas as pd

if TYPE_CHECKING:
    from bnb_quant_v2.analysis.evaluator import LiveSignal


T = TypeVar("T")


@dataclass
class RuleMetadata:
    """规则元数据。"""

    name: str
    tier: str = "other"
    risk: str = "medium"
    description: str = ""
    enabled: bool = True
    version: str = "1.0"


class Rule(Protocol):
    """规则协议：单条交易规则的抽象接口。"""

    metadata: RuleMetadata

    def evaluate(self, row: pd.Series) -> int:
        """评估单条规则，返回 +1（涨）/ -1（跌）/ 0（无信号）。"""
        ...

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        """批量评估规则，返回每一行的预测值。"""
        ...


class BaseRule(ABC):
    """规则基类，提供通用功能。"""

    metadata: RuleMetadata

    @abstractmethod
    def evaluate(self, row: pd.Series) -> int:
        ...

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        """默认批量评估实现：逐行调用 evaluate。"""
        return df.apply(self.evaluate, axis=1)


class RuleRegistry:
    """规则注册表：管理所有规则的注册和查询。"""

    def __init__(self) -> None:
        self._rules: Dict[str, Rule] = {}
        self._rules_by_tier: Dict[str, List[Rule]] = {}

    def register(self, rule: Rule) -> None:
        """注册规则。"""
        name = rule.metadata.name
        self._rules[name] = rule
        tier = rule.metadata.tier
        if tier not in self._rules_by_tier:
            self._rules_by_tier[tier] = []
        self._rules_by_tier[tier].append(rule)

    def register_decorator(
        self,
        *,
        name: str,
        tier: str = "other",
        risk: str = "medium",
        description: str = "",
        enabled: bool = True,
        version: str = "1.0",
    ) -> Callable[[Type[BaseRule]], Type[BaseRule]]:
        """装饰器：注册规则类。"""

        def decorator(cls: Type[BaseRule]) -> Type[BaseRule]:
            cls.metadata = RuleMetadata(
                name=name,
                tier=tier,
                risk=risk,
                description=description,
                enabled=enabled,
                version=version,
            )
            self.register(cls())
            return cls

        return decorator

    def get(self, name: str) -> Optional[Rule]:
        """按名称获取规则。"""
        return self._rules.get(name)

    def get_enabled(self) -> Iterable[Rule]:
        """获取所有启用的规则。"""
        return (r for r in self._rules.values() if r.metadata.enabled)

    def get_by_tier(self, tier: str) -> Iterable[Rule]:
        """按层级获取规则。"""
        return self._rules_by_tier.get(tier, [])

    def get_live_push_rules(self) -> List[Rule]:
        """获取实时推送规则（primary/strict/primary_short/strict_short）。"""
        tiers = ["primary", "strict", "primary_short", "strict_short"]
        result: List[Rule] = []
        for tier in tiers:
            result.extend(self.get_by_tier(tier))
        return result

    def names(self) -> List[str]:
        """获取所有规则名称。"""
        return list(self._rules.keys())

    def enabled_names(self) -> List[str]:
        """获取所有启用规则的名称。"""
        return [r.metadata.name for r in self.get_enabled()]

    def evaluate_all(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """评估所有启用的规则，返回规则名→预测系列的映射。"""
        return {rule.metadata.name: rule.evaluate_batch(df) for rule in self.get_enabled()}


rule_registry = RuleRegistry()


class Strategy(Protocol):
    """策略协议：统一的策略接口。"""

    name: str
    description: str = ""

    def build_features(self, df_1h: pd.DataFrame, df_5m: pd.DataFrame) -> pd.DataFrame:
        """构建策略特征表。"""
        ...

    def evaluate(self, df: pd.DataFrame, rule_name: str) -> pd.Series:
        """评估单条规则。"""
        ...

    def evaluate_all(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """评估所有规则。"""
        ...

    def live_signal_from_row(self, row: pd.Series, rule_name: str) -> "LiveSignal":
        """从特征行构建实时信号。"""
        ...


class StrategyRegistry:
    """策略注册表：管理所有策略的注册和查询。"""

    def __init__(self) -> None:
        self._strategies: Dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        """注册策略。"""
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> Optional[Strategy]:
        """按名称获取策略。"""
        return self._strategies.get(name)

    def names(self) -> List[str]:
        """获取所有策略名称。"""
        return list(self._strategies.keys())


strategy_registry = StrategyRegistry()