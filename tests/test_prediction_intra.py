from __future__ import annotations

import pandas as pd

from bnb_quant_v2.analysis.intra_5m import enrich_1h_with_intra
from bnb_quant_v2.analysis.prediction_intra import compare_intra_descriptive


def _sample_features(n: int = 200) -> pd.DataFrame:
    import numpy as np

    rng = np.random.default_rng(0)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.005, n))
    open_ = np.roll(close, 1)
    open_[0] = 100.0
    high = np.maximum(open_, close) * 1.002
    low = np.minimum(open_, close) * 0.998
    df_1h = pd.DataFrame(
        {
            "open_time": pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(1000, 5000, n),
            "closed": True,
        }
    )
    rows = []
    for ts in df_1h["open_time"]:
        for i in range(12):
            rows.append(
                {
                    "open_time": ts + pd.Timedelta(minutes=5 * i),
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.1,
                    "volume": 100.0,
                    "closed": True,
                }
            )
    df_5m = pd.DataFrame(rows)
    return enrich_1h_with_intra(df_1h.iloc[:50], df_5m)


def test_compare_intra_descriptive() -> None:
    report = compare_intra_descriptive(_sample_features(), verbose=False)
    assert report.total_bars > 0
    assert len(report.yang_cnt_buckets) > 0
    assert len(report.cross_stats) > 0
    assert 0.0 <= report.baseline_up_rate <= 1.0
