"""模块一：获取数据 — K 线存储、Gate CSV 导入、质量审计、实时同步框架。

子包
----
``live/``
    阶段 B 实时增量同步（``config/live_sync.yaml``）。Gate/Binance Fetcher 当前为占位，
    ``enabled=false`` 时不会发起网络请求。

数据流
------
Gate CSV / REST → ``normalize_kline_dataframe`` → ``KlineStore.save_dataframe``
→ ``data/klines/{symbol}_{interval}.parquet``

下游消费者
----------
- ``analysis``：回测与实时评估读 parquet
- ``runtime``：流水线在 eval 前可选调用 ``run_live_sync``

脚本入口
--------
- ``scripts/data/import_gate.py`` — 离线 CSV 批量导入
- ``scripts/data/sync_live_klines.py`` — 增量同步 CLI
- ``scripts/data/validate_intra_alignment.py`` — 5m↔1H 对齐校验
"""

from bnb_quant_v2.data.importers import import_gate_directory
from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.data.quality import audit_klines

__all__ = ["KlineStore", "import_gate_directory", "audit_klines"]
