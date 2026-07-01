"""Parquet K 线持久化层。

约定
----
- 路径：``{root}/{symbol}_{interval}.parquet``（默认 root = ``data/klines``）
- 列：``open_time, open, high, low, close, volume, closed``
- ``open_time`` 统一为 UTC timezone-aware

注意
----
``load`` 在文件不存在时抛 ``FileNotFoundError``；实时流水线依赖此行为触发告警。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from bnb_quant_v2.paths import PROJECT_ROOT


class KlineStore:
    """读写单品种单周期的 K 线 parquet。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or PROJECT_ROOT / "data" / "klines").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, symbol: str, interval: str) -> Path:
        """返回 parquet 文件路径，不检查是否存在。"""
        return self.root / f"{symbol}_{interval}.parquet"

    def load(self, symbol: str, interval: str) -> pd.DataFrame:
        """加载并按 ``open_time`` 升序返回。文件缺失时抛 ``FileNotFoundError``。"""
        p = self.path(symbol, interval)
        if not p.exists():
            raise FileNotFoundError(p)
        df = pd.read_parquet(p)
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        return df.sort_values("open_time").reset_index(drop=True)

    def save_dataframe(self, symbol: str, interval: str, df: pd.DataFrame) -> Path:
        """覆盖写入 parquet（全量替换，非增量 merge）。"""
        out = self.path(symbol, interval)
        df = df.sort_values("open_time").reset_index(drop=True)
        df.to_parquet(out, index=False)
        return out

    def merge_append(self, symbol: str, interval: str, new_df: pd.DataFrame) -> tuple[Path, int]:
        """增量合并：按 ``open_time`` 去重，新数据覆盖同时间旧行。

        Returns:
            (parquet 路径, 本次合并后总行数)
        """
        if new_df.empty:
            p = self.path(symbol, interval)
            if p.exists():
                return p, len(self.load(symbol, interval))
            empty = new_df.copy()
            return self.save_dataframe(symbol, interval, empty), 0

        new_df = new_df.copy()
        new_df["open_time"] = pd.to_datetime(new_df["open_time"], utc=True)

        p = self.path(symbol, interval)
        if p.exists():
            existing = self.load(symbol, interval)
            merged = pd.concat([existing, new_df], ignore_index=True)
        else:
            merged = new_df

        merged = merged.drop_duplicates(subset=["open_time"], keep="last")
        merged = merged.sort_values("open_time").reset_index(drop=True)
        out = self.save_dataframe(symbol, interval, merged)
        return out, len(merged)
