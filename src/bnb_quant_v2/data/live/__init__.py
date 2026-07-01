"""实时 K 线增量同步（阶段 B）。

配置：``config/live_sync.yaml``（默认 ``enabled: false``）。

计划任务频率（UTC）::
    */5  — sync 5m
    :02  — sync 1h
    :30  — eval（见 runtime 模块）

当前 Gate/Binance Fetcher 为占位，真实拉取需实现 ``fetcher.py`` 并启用配置。
"""
from bnb_quant_v2.data.live.config import LiveSyncConfig, load_live_sync_config
from bnb_quant_v2.data.live.fetcher import LiveDataUnavailableError, get_fetcher
from bnb_quant_v2.data.live.scheduler import SyncPlan, build_sync_plan, cron_hints, run_live_sync

__all__ = [
    "LiveDataUnavailableError",
    "LiveSyncConfig",
    "SyncPlan",
    "build_sync_plan",
    "cron_hints",
    "get_fetcher",
    "load_live_sync_config",
    "run_live_sync",
]
