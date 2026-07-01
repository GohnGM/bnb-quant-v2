"""模块二：分析策略 — 特征工程、回测、规则评估、实时信号判定。

子模块
------
- ``intra_5m``       — 5m↔1H 对齐，p1/f6 特征
- ``backtest_p1_f6`` — 方向准确率回测，规则常量（``PRIMARY_HOUR_RULE`` 等）
- ``evaluator``      — 实时 :30 评估（与回测共用 ``build_p1_f6_hour_predictions``）
- ``prediction_*``   — 探索性统计（非生产推送路径）

脚本入口
--------
- ``scripts/analysis/backtest_p1_f6.py`` — 主回测 CLI
- ``scripts/analysis/analyze_*.py``      — 研究分析
"""

from bnb_quant_v2.analysis.evaluator import (
    EvalResult,
    LiveSignal,
    evaluate_from_store,
    evaluate_live_at,
    resolve_eval_hour,
    rule_tier,
)
from bnb_quant_v2.analysis.prediction_1h import analyze_1h_prediction, compare_prev1_rules

__all__ = [
    "EvalResult",
    "LiveSignal",
    "analyze_1h_prediction",
    "compare_prev1_rules",
    "evaluate_from_store",
    "evaluate_live_at",
    "resolve_eval_hour",
    "rule_tier",
]
