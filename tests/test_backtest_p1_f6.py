from __future__ import annotations

import pandas as pd

from bnb_quant_v2.analysis.backtest_p1_f6 import (
    BACKTEST_COMPARE_RULES,
    LIVE_PUSH_RULES,
    PRIMARY_HOUR_RULE,
    PRIMARY_HOUR_SHORT_RULE,
    STRICT_HOUR_SHORT_RULE,
    run_p1_f6_backtest,
)
from bnb_quant_v2.analysis.intra_5m import enrich_p1_f6


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


def test_enrich_p1_f6_half2_labels() -> None:
    m5 = _make_two_hours_5m()
    h1 = _make_h1_from_m5(m5)
    out = enrich_p1_f6(h1, m5)
    row = out.iloc[0]
    assert bool(row["half2_up"]) is True
    assert row["half2_ret"] > 0
    assert row["entry_price"] == row["f6_close"]
    assert row["exit_price"] == h1.iloc[1]["close"]


def test_primary_hour_rule() -> None:
    m5 = _make_two_hours_5m()
    h1 = _make_h1_from_m5(m5)
    df = enrich_p1_f6(h1, m5)
    report = run_p1_f6_backtest(df, target_col="hour_up", rule_name=PRIMARY_HOUR_RULE)
    assert not isinstance(report, list)
    assert report.rule_name == PRIMARY_HOUR_RULE


def test_short_rules_registered() -> None:
    assert PRIMARY_HOUR_SHORT_RULE.endswith("→ 1H跌")
    assert STRICT_HOUR_SHORT_RULE.endswith("→ 1H跌")
    assert len(BACKTEST_COMPARE_RULES) == 4
    assert BACKTEST_COMPARE_RULES == LIVE_PUSH_RULES
    assert PRIMARY_HOUR_SHORT_RULE in BACKTEST_COMPARE_RULES
    assert STRICT_HOUR_SHORT_RULE in BACKTEST_COMPARE_RULES
