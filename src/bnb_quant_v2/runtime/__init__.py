"""模块四：保持运行 — 确保规则触发时能可靠推送 Telegram。

组件
----
- ``pipeline``   — 编排 sync → eval → dedup → notify
- ``dedup``      — 按 (hour, rule) 防重复推送
- ``run_stats``  — JSON 事件日志（健康检查、心跳数据源）

端到端时序（UTC，以 10:00–11:00 这根 1H 为例）::

    10:00–10:25  sync 5m 写入当前小时前 5 根
    10:30        eval 评估主/严格规则 → Telegram
    11:02        sync 1h 拉取已收盘 K 线
    04:00        日心跳

launchd 入口：``scripts/launchd_task.sh`` → ``scripts/runtime/eval_p1_f6_signal.py``
"""

from bnb_quant_v2.runtime.dedup import SignalDedup
from bnb_quant_v2.runtime.pipeline import (
    NotifyStepResult,
    PipelineResult,
    SyncStepResult,
    run_eval_pipeline,
    run_notify_step,
    run_pre_eval_sync,
)
from bnb_quant_v2.runtime.run_stats import (
    DEFAULT_STATS_PATH,
    append_run_event,
    events_in_window,
)

__all__ = [
    "DEFAULT_STATS_PATH",
    "NotifyStepResult",
    "PipelineResult",
    "SignalDedup",
    "SyncStepResult",
    "append_run_event",
    "events_in_window",
    "run_eval_pipeline",
    "run_notify_step",
    "run_pre_eval_sync",
]
