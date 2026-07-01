"""实时同步配置加载。

配置文件：``config/live_sync.yaml``

阶段 B 前保持 ``enabled: false``，避免 launchd 定时任务误发网络请求。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bnb_quant_v2.paths import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "live_sync.yaml"


@dataclass
class LiveSyncConfig:
    """实时增量同步参数。"""

    symbol: str = "BTCUSDT"
    intervals: list[str] = field(default_factory=lambda: ["5m", "1h"])
    source: str = "gate"  # gate | binance
    lookback_bars: dict[str, int] = field(default_factory=lambda: {"5m": 24, "1h": 3})
    store_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "klines")
    enabled: bool = False  # 阶段 B 前保持 False


def load_live_sync_config(path: Path | str | None = None) -> LiveSyncConfig:
    """从 YAML 加载；文件不存在时返回默认（enabled=False）。"""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return LiveSyncConfig()
    raw = yaml.safe_load(cfg_path.read_text()) or {}
    lookback = raw.get("lookback_bars") or {"5m": 24, "1h": 3}
    store = raw.get("store_dir", "data/klines")
    return LiveSyncConfig(
        symbol=str(raw.get("symbol", "BTCUSDT")),
        intervals=list(raw.get("intervals", ["5m", "1h"])),
        source=str(raw.get("source", "gate")),
        lookback_bars={str(k): int(v) for k, v in lookback.items()},
        store_dir=PROJECT_ROOT / store if not Path(store).is_absolute() else Path(store),
        enabled=bool(raw.get("enabled", False)),
    )
