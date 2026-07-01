"""Gate REST 解析与 KlineStore 增量合并测试。"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.data.live.fetcher import FetchRequest, GateFetcher, get_fetcher
from bnb_quant_v2.data.live.gate_rest import parse_gate_candlesticks


def test_parse_gate_candlesticks() -> None:
    rows = [
        ["1609459200", "100.5", "29000.1", "29100.0", "28900.0", "28950.0"],
        ["1609459500", "80.2", "29150.0", "29200.0", "29000.0", "29000.1"],
    ]
    df = parse_gate_candlesticks(rows)
    assert list(df.columns) == ["open_time", "open", "high", "low", "close", "volume", "closed"]
    assert len(df) == 2
    assert df["open"].iloc[0] == 28950.0
    assert df["close"].iloc[0] == 29000.1


def test_merge_append_dedup(tmp_path) -> None:
    store = KlineStore(tmp_path)
    t0 = pd.Timestamp("2024-01-01 00:00:00", tz="UTC")
    base = pd.DataFrame(
        {
            "open_time": [t0, t0 + pd.Timedelta(minutes=5)],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [1.0, 1.0],
            "closed": [True, True],
        }
    )
    store.save_dataframe("BTCUSDT", "5m", base)

    updated = base.copy()
    updated.loc[1, "close"] = 999.0
    new_row = pd.DataFrame(
        {
            "open_time": [t0 + pd.Timedelta(minutes=10)],
            "open": [102.0],
            "high": [103.0],
            "low": [101.0],
            "close": [102.5],
            "volume": [1.0],
            "closed": [True],
        }
    )
    patch_df = pd.concat([updated.iloc[[1]], new_row], ignore_index=True)
    _, total = store.merge_append("BTCUSDT", "5m", patch_df)
    assert total == 3
    loaded = store.load("BTCUSDT", "5m")
    assert loaded["close"].iloc[1] == 999.0
    assert loaded["open_time"].iloc[-1] == t0 + pd.Timedelta(minutes=10)


def test_gate_fetcher_uses_limit_when_no_since() -> None:
    sample = parse_gate_candlesticks(
        [["1609459200", "1", "100", "101", "99", "100"]]
    )
    fetcher = GateFetcher()
    with patch(
        "bnb_quant_v2.data.live.fetcher.fetch_spot_candlesticks",
        return_value=sample,
    ) as mock_fetch:
        out = fetcher.fetch_klines(
            FetchRequest(symbol="BTCUSDT", interval="5m", since=None, limit=10)
        )
        assert len(out) == 1
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args.kwargs["limit"] == 10


def test_gate_fetcher_uses_from_to_when_since() -> None:
    sample = parse_gate_candlesticks([])
    fetcher = GateFetcher()
    since = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with patch(
        "bnb_quant_v2.data.live.fetcher.fetch_spot_candlesticks",
        return_value=sample,
    ) as mock_fetch:
        fetcher.fetch_klines(
            FetchRequest(symbol="BTCUSDT", interval="5m", since=since, limit=24)
        )
        assert "from_ts" in mock_fetch.call_args.kwargs
        assert "to_ts" in mock_fetch.call_args.kwargs


def test_get_fetcher_enabled_gate() -> None:
    assert get_fetcher("gate", enabled=True).name == "gate"
