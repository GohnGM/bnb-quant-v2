"""策略抽象层：Rule 协议、Strategy 协议、规则注册表。

规则注册表模式（Rule Registry Pattern）
--------------------------------------
- 每条规则是一个独立类，实现 ``Rule`` 协议
- 通过 ``@rule_registry.register_decorator()`` 装饰器注册
- 回测和实时评估都从 registry 查询规则，确保规则单一来源

Strategy 协议（统一预测框架）
---------------------------
- ``build_features()`` — 构建特征表
- ``evaluate()`` — 评估单条规则
- ``evaluate_all()`` — 评估所有规则
- 使 bar→next_bar 和 p1×f6 策略可互换、可比对

p1×f6 策略
----------
- ``P1F6Strategy`` — p1×f6 量化信号策略
- ``get_p1f6_strategy()`` — 获取 p1×f6 策略实例
"""
from bnb_quant_v2.strategy.base import (
    BaseRule,
    Rule,
    RuleMetadata,
    RuleRegistry,
    Strategy,
    StrategyRegistry,
    rule_registry,
    strategy_registry,
)
from bnb_quant_v2.strategy.p1f6_rules import (
    PRIMARY_HOUR_RULE,
    STRICT_HOUR_RULE,
    PRIMARY_HOUR_SHORT_RULE,
    STRICT_HOUR_SHORT_RULE,
)
from bnb_quant_v2.strategy.p1f6_strategy import P1F6Strategy, get_p1f6_strategy


__all__ = [
    "BaseRule",
    "Rule",
    "RuleMetadata",
    "RuleRegistry",
    "Strategy",
    "StrategyRegistry",
    "rule_registry",
    "strategy_registry",
    "P1F6Strategy",
    "get_p1f6_strategy",
    "PRIMARY_HOUR_RULE",
    "STRICT_HOUR_RULE",
    "PRIMARY_HOUR_SHORT_RULE",
    "STRICT_HOUR_SHORT_RULE",
]