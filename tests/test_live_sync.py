from __future__ import annotations

import pytest

from bnb_quant_v2.data.live import LiveSyncConfig, build_sync_plan, load_live_sync_config
from bnb_quant_v2.data.live.fetcher import LiveDataUnavailableError, StubFetcher, get_fetcher
from bnb_quant_v2.data.live.scheduler import run_live_sync


def test_load_default_config() -> None:
    cfg = load_live_sync_config()
    assert cfg.symbol == "BTCUSDT"
    assert "5m" in cfg.intervals
    assert cfg.enabled is False


def test_build_sync_plan_dry_run() -> None:
    cfg = LiveSyncConfig(enabled=False)
    plan = build_sync_plan(cfg, "5m", dry_run=True)
    assert plan.symbol == "BTCUSDT"
    assert plan.interval == "5m"
    assert plan.dry_run is True
    assert "BTCUSDT_5m.parquet" in plan.store_path


def test_stub_fetcher_raises() -> None:
    from bnb_quant_v2.data.live.fetcher import FetchRequest

    with pytest.raises(LiveDataUnavailableError):
        StubFetcher().fetch_klines(
            FetchRequest(symbol="BTCUSDT", interval="5m", since=None, limit=10)
        )


def test_get_fetcher_disabled() -> None:
    assert get_fetcher("gate", enabled=False).name == "stub"


def test_run_live_sync_dry_run(capsys) -> None:
    cfg = LiveSyncConfig(enabled=False)
    run_live_sync(cfg, "1h", dry_run=True)
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "BTCUSDT" in out
