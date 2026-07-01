from __future__ import annotations

import numpy as np
import pandas as pd

from bnb_quant_v2.analysis.prediction_1h import (
    analyze_1h_prediction,
    compare_prev1_rules,
    compare_prev2_rules,
    compare_prev2_shadow_body_rules,
    compare_shadow_body_rules,
    enrich_bar_features,
    enrich_prev2_features,
)


def _sample_df(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.005, n))
    open_ = np.roll(close, 1)
    open_[0] = 100.0
    high = np.maximum(open_, close) * 1.002
    low = np.minimum(open_, close) * 0.998
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.uniform(1000, 5000, n),
        }
    )


def test_enrich_bar_features() -> None:
    df = enrich_bar_features(_sample_df(50))
    assert "body_pct" in df.columns
    assert "yang" in df.columns
    assert "body_range" in df.columns
    assert "candle_type" in df.columns
    assert len(df) == 50


def test_compare_shadow_body_rules() -> None:
    report = compare_shadow_body_rules(_sample_df(200), verbose=False)
    assert report.total_bars > 0
    assert len(report.candle_types) > 0
    assert len(report.results) > 0


def test_compare_prev2_shadow_body_rules() -> None:
    report = compare_prev2_shadow_body_rules(_sample_df(200), verbose=False)
    assert report.total_bars > 0
    assert len(report.results) > 0


def test_compare_prev2_rules() -> None:
    report = compare_prev2_rules(_sample_df(200), verbose=False)
    assert report.total_bars > 0
    assert len(report.results) > 0
    for r in report.results:
        assert r.correct + r.wrong == r.signals


def test_enrich_prev2_features() -> None:
    df = enrich_prev2_features(_sample_df(50))
    assert "p1_yang" in df.columns
    assert "p2_body_pct" in df.columns
    assert "bar_up" in df.columns
    assert pd.isna(df["p1_yang"].iloc[0])
    assert pd.isna(df["p2_yang"].iloc[1])
    assert not pd.isna(df["p1_yang"].iloc[2])


def test_compare_prev1_rules() -> None:
    report = compare_prev1_rules(_sample_df(200), verbose=False)
    assert report.total_bars > 0
    assert len(report.results) > 0
    for r in report.results:
        assert r.correct + r.wrong == r.signals
