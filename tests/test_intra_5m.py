from __future__ import annotations

import pandas as pd

from bnb_quant_v2.analysis.intra_5m import (
    aggregate_5m_to_1h,
    align_5m_to_1h,
    compute_first6_features,
    compute_intra_features,
    enrich_1h_with_intra,
    enrich_p1_f6,
    filter_complete_hours,
    validate_hour_alignment,
)


def _make_5m_hour(base: float = 100.0) -> pd.DataFrame:
    """合成 1 小时 12 根 5m。"""
    times = pd.date_range("2024-01-01 00:00", periods=12, freq="5min", tz="UTC")
    close = base + pd.Series(range(12), dtype=float) * 0.1
    open_ = close.shift(1).fillna(base)
    return pd.DataFrame(
        {
            "open_time": times,
            "open": open_,
            "high": pd.concat([open_, close], axis=1).max(axis=1) + 0.05,
            "low": pd.concat([open_, close], axis=1).min(axis=1) - 0.05,
            "close": close,
            "volume": 100.0,
            "closed": True,
        }
    )


def test_aggregate_and_validate_clean() -> None:
    m5 = _make_5m_hour()
    agg = aggregate_5m_to_1h(m5)
    assert len(agg) == 1
    assert agg.iloc[0]["m5_count"] == 12

    h1 = pd.DataFrame(
        {
            "open_time": [pd.Timestamp("2024-01-01 00:00", tz="UTC")],
            "open": [m5["open"].iloc[0]],
            "high": [m5["high"].max()],
            "low": [m5["low"].min()],
            "close": [m5["close"].iloc[-1]],
            "volume": [m5["volume"].sum()],
            "closed": [True],
        }
    )
    aligned = align_5m_to_1h(h1, m5, complete_only=False)
    report = validate_hour_alignment(aligned)
    assert report.passed
    assert report.ohlc_all_match == 1

    filtered = filter_complete_hours(aligned)
    assert len(filtered) == 1
    assert filtered.iloc[0]["m5_complete"]


def test_filter_complete_hours_drops_incomplete() -> None:
    m5 = _make_5m_hour().iloc[:11]
    h1 = pd.DataFrame(
        {
            "open_time": [pd.Timestamp("2024-01-01 00:00", tz="UTC")],
            "open": [100.0],
            "high": [101.5],
            "low": [99.5],
            "close": [101.0],
            "volume": [1100.0],
            "closed": [True],
        }
    )
    aligned = align_5m_to_1h(h1, m5, complete_only=False)
    assert len(aligned) == 1
    assert len(filter_complete_hours(aligned)) == 0
    assert len(align_5m_to_1h(h1, m5, complete_only=True)) == 0


def test_validate_detects_incomplete_hour() -> None:
    m5 = _make_5m_hour().iloc[:11]
    h1 = pd.DataFrame(
        {
            "open_time": [pd.Timestamp("2024-01-01 00:00", tz="UTC")],
            "open": [100.0],
            "high": [101.5],
            "low": [99.5],
            "close": [101.0],
            "volume": [1100.0],
            "closed": [True],
        }
    )
    aligned = align_5m_to_1h(h1, m5, complete_only=False)
    report = validate_hour_alignment(aligned)
    assert report.complete_hours == 0
    assert not report.passed


def test_compute_intra_features_on_synthetic_hour() -> None:
    m5 = _make_5m_hour()
    feat = compute_intra_features(m5)
    assert feat["m5_count"] == 12
    assert feat["m5_yang_cnt"] + feat["m5_yin_cnt"] == 12
    assert feat["m5_last1_yang"] == bool(m5.iloc[-1]["close"] > m5.iloc[-1]["open"])
    assert feat["m5_pattern_last3"] in {"阳阳阳", "阳阳阴", "阳阴阳", "阳阴阴", "阴阳阳", "阴阳阴", "阴阴阳", "阴阴阴"}
    assert abs(feat["m5_ret_sum"] - feat["m5_first_half_ret"] - feat["m5_second_half_ret"]) < 1e-12


def test_enrich_1h_with_intra() -> None:
    m5 = _make_5m_hour()
    h1 = pd.DataFrame(
        {
            "open_time": [pd.Timestamp("2024-01-01 00:00", tz="UTC")],
            "open": [m5["open"].iloc[0]],
            "high": [m5["high"].max()],
            "low": [m5["low"].min()],
            "close": [m5["close"].iloc[-1]],
            "volume": [m5["volume"].sum()],
            "closed": [True],
        }
    )
    out = enrich_1h_with_intra(h1, m5)
    assert len(out) == 1
    assert "m5_yang_cnt" in out.columns
    assert "candle_type" in out.columns
    assert "next_bar_up" in out.columns
    assert out.iloc[0]["m5_count"] == 12


def _make_two_hours_5m() -> pd.DataFrame:
    h0 = _make_5m_hour(base=100.0)
    h1 = _make_5m_hour(base=101.0)
    h1["open_time"] = h1["open_time"] + pd.Timedelta(hours=1)
    return pd.concat([h0, h1], ignore_index=True)


def test_compute_first6_features() -> None:
    m5 = _make_5m_hour()
    feat = compute_first6_features(m5)
    assert feat["f6_count"] == 6
    assert feat["f6_yang_cnt"] + feat["f6_yin_cnt"] == 6
    assert len(feat["f6_pattern"]) == 6
    assert feat["f6_high"] >= feat["f6_low"]
    assert 0.0 <= feat["f6_close_strength"] <= 1.0
    assert feat["f6_range_hl"] > 0
    assert feat["f6_volume"] > 0


def test_enrich_p1_f6_two_hours() -> None:
    m5 = _make_two_hours_5m()
    rows = []
    for i, ts in enumerate(["2024-01-01 00:00", "2024-01-01 01:00"]):
        sub = m5.loc[m5["open_time"].dt.floor("1h") == pd.Timestamp(ts, tz="UTC")]
        rows.append(
            {
                "open_time": pd.Timestamp(ts, tz="UTC"),
                "open": sub["open"].iloc[0],
                "high": sub["high"].max(),
                "low": sub["low"].min(),
                "close": sub["close"].iloc[-1],
                "volume": sub["volume"].sum(),
                "closed": True,
            }
        )
    h1 = pd.DataFrame(rows)
    out = enrich_p1_f6(h1, m5)
    assert len(out) == 1
    assert "p1_yin" in out.columns
    assert "f6_yang_cnt" in out.columns
    assert "hour_up" in out.columns
    assert "half2_up" in out.columns
    assert "entry_price" in out.columns
    assert "f6_close_strength" in out.columns
    assert "f6_range_hl" in out.columns
    assert "gap_hour" in out.columns
    assert "exit_at" in out.columns
    assert out.iloc[0]["hour_up"] == out.iloc[0]["yang"]
    assert out.iloc[0]["p1_yin"] == (h1.iloc[0]["close"] < h1.iloc[0]["open"])
