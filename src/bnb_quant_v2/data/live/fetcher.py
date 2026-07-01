"""交易所 K 线拉取器抽象（阶段 B：Gate 已实现）。

返回 DataFrame 列：``open_time, open, high, low, close, volume, closed``
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from bnb_quant_v2.data.live.gate_rest import fetch_spot_candlesticks, load_gate_credentials


class LiveDataUnavailableError(RuntimeError):
    """实时拉取未启用或 Fetcher 尚未实现。"""


@dataclass
class FetchRequest:
    """单次拉取请求参数。"""

    symbol: str
    interval: str
    since: datetime | None  # 增量起点；None 表示拉最近 limit 根
    limit: int


class KlineFetcher(ABC):
    """交易所 K 线拉取器接口。"""

    name: str

    @abstractmethod
    def fetch_klines(self, req: FetchRequest) -> pd.DataFrame:
        """返回标准 K 线列（见模块 docstring）。"""


class StubFetcher(KlineFetcher):
    """占位：不发起网络请求，用于 live_sync.enabled=false。"""

    name = "stub"

    def fetch_klines(self, req: FetchRequest) -> pd.DataFrame:
        raise LiveDataUnavailableError(
            f"实时拉取未启用（source=stub）。"
            f" 计划: {req.symbol} {req.interval} limit={req.limit}。"
            f" 见 config/live_sync.yaml enabled=true 与 docs/RUN.md。"
        )


class GateFetcher(KlineFetcher):
    """Gate spot REST K 线（公开接口；API Key 可选，用于提高限额）。"""

    name = "gate"

    def __init__(self, api_key: str = "", api_secret: str = "") -> None:
        self.api_key = api_key
        self.api_secret = api_secret  # spot candlesticks 为公开接口，暂不需要签名

    def fetch_klines(self, req: FetchRequest) -> pd.DataFrame:
        now = datetime.now(timezone.utc)
        if req.since is not None:
            since = req.since
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            from_ts = int(since.timestamp())
            to_ts = int(now.timestamp())
            return fetch_spot_candlesticks(
                req.symbol,
                req.interval,
                from_ts=from_ts,
                to_ts=to_ts,
                api_key=self.api_key,
            )
        return fetch_spot_candlesticks(
            req.symbol,
            req.interval,
            limit=max(req.limit, 1),
            api_key=self.api_key,
        )


class BinanceFetcher(StubFetcher):
    """Binance REST K 线（待实现，阶段 F 备选）。"""

    name = "binance"


def get_fetcher(source: str, *, enabled: bool = False) -> KlineFetcher:
    """按配置选择 Fetcher；``enabled=False`` 时始终返回 ``StubFetcher``。"""
    from bnb_quant_v2.notify.config import load_env_file

    load_env_file()
    if not enabled:
        return StubFetcher()
    mapping: dict[str, type[KlineFetcher]] = {
        "gate": GateFetcher,
        "binance": BinanceFetcher,
        "stub": StubFetcher,
    }
    cls = mapping.get(source.lower(), StubFetcher)
    if cls is GateFetcher:
        key, secret = load_gate_credentials()
        return GateFetcher(api_key=key, api_secret=secret)
    return cls()


def empty_klines_frame() -> pd.DataFrame:
    """空 K 线表（列结构正确，用于测试）。"""
    return pd.DataFrame(
        columns=["open_time", "open", "high", "low", "close", "volume", "closed"]
    )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
