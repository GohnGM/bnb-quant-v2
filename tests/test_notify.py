from __future__ import annotations

import pandas as pd

from bnb_quant_v2.analysis.backtest_p1_f6 import PRIMARY_HOUR_RULE, PRIMARY_HOUR_SHORT_RULE
from bnb_quant_v2.notify.format import (
    format_alert_message,
    format_dual_time,
    format_signal_message,
    heartbeat_period_end,
)
from bnb_quant_v2.notify.telegram import TelegramClient
from bnb_quant_v2.analysis.evaluator import LiveSignal
from bnb_quant_v2.runtime.pipeline import run_eval_pipeline, run_pre_eval_sync


def test_format_dual_time() -> None:
    utc_s, bj_s = format_dual_time("2026-06-25 10:30:00+00:00")
    assert utc_s == "2026-06-25 10:30"
    assert bj_s == "2026-06-25 18:30"


def test_format_signal_message() -> None:
    sig = LiveSignal(
        hour_open_time=pd.Timestamp("2026-06-25 10:00:00", tz="UTC"),
        rule=PRIMARY_HOUR_RULE,
        direction=1,
        prediction="涨",
        entry_at=pd.Timestamp("2026-06-25 10:30:00", tz="UTC"),
        entry_price=67890.12,
        exit_at=pd.Timestamp("2026-06-25 11:00:00", tz="UTC"),
        hour_open_price=67750.00,
        p1_candle_type="大阴线",
        f6_yang_cnt=5,
        f6_close_strength=0.82,
        f6_ret_sum=0.003,
    )
    text = format_signal_message(sig, tier="primary")
    assert "主规则·做多" in text
    assert "67,890.12 USDT" in text
    assert "67,750.00 USDT" in text
    assert "入场价 (:30)" in text
    assert "北京" in text


def test_format_signal_message_short() -> None:
    sig = LiveSignal(
        hour_open_time=pd.Timestamp("2026-06-25 10:00:00", tz="UTC"),
        rule=PRIMARY_HOUR_SHORT_RULE,
        direction=-1,
        prediction="跌",
        entry_at=pd.Timestamp("2026-06-25 10:30:00", tz="UTC"),
        entry_price=68000.0,
        exit_at=pd.Timestamp("2026-06-25 11:00:00", tz="UTC"),
        hour_open_price=68200.0,
        p1_candle_type="大阳线",
        f6_yang_cnt=1,
        f6_close_strength=0.2,
        f6_ret_sum=-0.003,
    )
    text = format_signal_message(sig, tier="primary_short")
    assert "主规则·做空" in text
    assert "做空" in text
    assert "68,000.00 USDT" in text
    assert "f6阴: 5" in text


def test_telegram_dry_run() -> None:
    from bnb_quant_v2.notify.config import TelegramConfig

    cfg = TelegramConfig(enabled=True, dry_run=True, bot_token="", chat_id="")
    res = TelegramClient(cfg).send("test")
    assert res.ok is True
    assert res.dry_run is True


def test_pre_eval_sync_disabled() -> None:
    from bnb_quant_v2.data.live.config import LiveSyncConfig

    cfg = LiveSyncConfig(enabled=False)
    result = run_pre_eval_sync(cfg, dry_run=False)
    assert result.attempted is True
    assert result.ok is False


def test_pipeline_notify_dry_run() -> None:
    from bnb_quant_v2.notify.config import TelegramConfig

    tg = TelegramConfig(enabled=True, dry_run=True, send_on_signal=True, send_on_error=True)
    pipeline = run_eval_pipeline(
        "BTCUSDT",
        as_of=pd.Timestamp("2023-01-01T14:30:00", tz="UTC"),
        hour_open=pd.Timestamp("2023-01-01T14:00:00", tz="UTC"),
        notify=True,
        no_dedup=True,
        tg_cfg=tg,
    )
    assert pipeline.eval.ready is True
    assert pipeline.notify is not None
    assert pipeline.notify.signals_sent >= 1


def test_heartbeat_period() -> None:
    end = pd.Timestamp("2026-06-25 04:00:00", tz="UTC")
    start, end_out = heartbeat_period_end(end)
    assert end_out == end
    assert (end - start).total_seconds() == 86400
