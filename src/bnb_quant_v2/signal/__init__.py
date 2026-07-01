"""兼容层 — 已迁移，请改用新模块路径。

迁移对照
--------
- ``signal.evaluator`` → ``analysis.evaluator``
- ``signal.pipeline``  → ``runtime.pipeline``
- ``signal.dedup``     → ``runtime.dedup``
- ``signal.run_stats`` → ``runtime.run_stats``
"""

from bnb_quant_v2.analysis.evaluator import (
    EvalResult,
    LiveSignal,
    evaluate_live_at,
    resolve_eval_hour,
)
from bnb_quant_v2.runtime.dedup import SignalDedup

__all__ = [
    "EvalResult",
    "LiveSignal",
    "SignalDedup",
    "evaluate_live_at",
    "resolve_eval_hour",
]
