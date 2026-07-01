from __future__ import annotations

from pathlib import Path

import pandas as pd

from bnb_quant_v2.analysis.backtest_p1_f6 import LIVE_PUSH_RULES, PRIMARY_HOUR_RULE
from bnb_quant_v2.analysis.intra_5m import enrich_p1_f6
from bnb_quant_v2.analysis.evaluator import (
    build_live_p1_f6_row,
    evaluate_live_at,
    validate_against_enriched,
)
from bnb_quant_v2.runtime.dedup import SignalDedup


def _make_5m_hour(base: float = 100.0, second_half_boost: float = 0.0) -> pd.DataFrame:
    times = pd.date_range("2024-01-01 00:00", periods=12, freq="5min", tz="UTC")
    close = base + pd.Series(range(12), dtype=float) * 0.1
    if second_half_boost:
        close.iloc[6:] = close.iloc[5] + pd.Series(range(6), dtype=float) * second_half_boost + 0.5
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


def _make_two_hours_5m() -> pd.DataFrame:
    h0 = _make_5m_hour(base=100.0)
    h1 = _make_5m_hour(base=101.0, second_half_boost=0.3)
    h1["open_time"] = h1["open_time"] + pd.Timedelta(hours=1)
    return pd.concat([h0, h1], ignore_index=True)


def _make_h1_from_m5(m5: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ts in m5["open_time"].dt.floor("1h").unique():
        sub = m5.loc[m5["open_time"].dt.floor("1h") == ts]
        rows.append(
            {
                "open_time": ts,
                "open": sub["open"].iloc[0],
                "high": sub["high"].max(),
                "low": sub["low"].min(),
                "close": sub["close"].iloc[-1],
                "volume": sub["volume"].sum(),
                "closed": True,
            }
        )
    return pd.DataFrame(rows)


def test_build_live_row_matches_enriched() -> None:
    m5 = _make_two_hours_5m()
    h1 = _make_h1_from_m5(m5)
    hour = pd.Timestamp("2024-01-01 01:00:00", tz="UTC")
    assert validate_against_enriched(h1, m5, hour) is True


def test_evaluate_live_returns_all_push_rules() -> None:
    m5 = _make_two_hours_5m()
    h1 = _make_h1_from_m5(m5)
    result = evaluate_live_at(
        h1,
        m5,
        as_of=pd.Timestamp("2024-01-01 01:30:00", tz="UTC"),
    )
    assert result.ready is True
    assert len(result.signals) == len(LIVE_PUSH_RULES)
    assert {s.rule for s in result.signals} == set(LIVE_PUSH_RULES)


def test_evaluate_skips_when_f6_incomplete() -> None:
    m5 = _make_two_hours_5m().iloc[:7]
    h1 = _make_h1_from_m5(m5)
    result = evaluate_live_at(
        h1,
        m5,
        hour_open=pd.Timestamp("2024-01-01 01:00:00", tz="UTC"),
    )
    assert result.ready is False
    assert result.skip_reason is not None


def test_dedup_per_rule(tmp_path: Path) -> None:
    dedup = SignalDedup(path=tmp_path / "state.json")
    hour = pd.Timestamp("2024-01-01 01:00:00", tz="UTC")
    dedup.mark_sent(hour, PRIMARY_HOUR_RULE)
    dedup.save()

    dedup2 = SignalDedup(path=tmp_path / "state.json")
    dedup2.load()
    assert dedup2.is_sent(hour, PRIMARY_HOUR_RULE)
    assert not dedup2.is_sent(hour, LIVE_PUSH_RULES[1])

    unsent = dedup2.filter_unsent(hour, list(LIVE_PUSH_RULES))
    assert PRIMARY_HOUR_RULE not in unsent
    assert len(unsent) == len(LIVE_PUSH_RULES) - 1


def test_live_row_on_enriched_sample() -> None:
    m5 = _make_two_hours_5m()
    h1 = _make_h1_from_m5(m5)
    enriched = enrich_p1_f6(h1, m5)
    hour = enriched.iloc[0]["open_time"]
    live = build_live_p1_f6_row(h1, m5, hour)
    assert live is not None
    assert live["entry_price"] == live["f6_close"]
