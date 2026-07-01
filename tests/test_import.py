from __future__ import annotations

import gzip
from pathlib import Path

import pandas as pd

from bnb_quant_v2.data.importers import GATE_CSV_COLUMNS, read_gate_csv
from bnb_quant_v2.data.quality import audit_klines


def test_gate_column_order(tmp_path: Path) -> None:
    csv = tmp_path / "BTC_USDT-202301.csv.gz"
    # Gate official: ts, vol, close, high, low, open
    row = "1672531200,2113502,16529.4,16541.7,16508.1,16536.6\n"
    with gzip.open(csv, "wt") as f:
        f.write(row)

    df = read_gate_csv(csv)
    assert df.iloc[0]["open"] == 16536.6
    assert df.iloc[0]["close"] == 16529.4
    assert df.iloc[0]["high"] == 16541.7
    assert df.iloc[0]["low"] == 16508.1


def test_audit_clean_series() -> None:
    times = pd.date_range("2024-01-01", periods=100, freq="1h", tz="UTC")
    close = pd.Series(range(100), dtype=float) + 100.0
    open_ = close.shift(1).fillna(100.0)
    df = pd.DataFrame(
        {
            "open_time": times,
            "open": open_,
            "high": pd.concat([open_, close], axis=1).max(axis=1),
            "low": pd.concat([open_, close], axis=1).min(axis=1),
            "close": close,
            "volume": 1.0,
            "closed": True,
        }
    )
    report = audit_klines(df)
    assert report.candle_artifact_pct < 10
    assert report.ohlc_violations == 0
