#!/usr/bin/env python3
"""每日 04:00 UTC（12:00 北京）Telegram 心跳（阶段 D）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.notify.config import load_telegram_config
from bnb_quant_v2.notify.format import format_heartbeat_message, heartbeat_period_end
from bnb_quant_v2.notify.telegram import TelegramClient
from bnb_quant_v2.runtime.run_stats import events_in_window

DEFAULT_HEARTBEAT_STATE = ROOT / "data" / "live" / "heartbeat_state.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily Telegram heartbeat")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--as-of", type=str, default=None, help="ISO8601，默认 UTC now")
    parser.add_argument("--telegram-config", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="只打印，不发送")
    args = parser.parse_args()

    as_of = pd.Timestamp(args.as_of, tz="UTC") if args.as_of else pd.Timestamp.now(tz="UTC")
    period_start, period_end = heartbeat_period_end(as_of)

    events = events_in_window(
        period_start.to_pydatetime(),
        period_end.to_pydatetime(),
    )
    sync_5m = [e for e in events if e.get("type") == "sync_5m"]
    sync_1h = [e for e in events if e.get("type") == "sync_1h"]
    evals = [e for e in events if e.get("type") == "eval"]

    primary_triggers = sum(int(e.get("primary_triggers", 0)) for e in evals)
    strict_triggers = sum(int(e.get("strict_triggers", 0)) for e in evals)
    primary_short_triggers = sum(int(e.get("primary_short_triggers", 0)) for e in evals)
    strict_short_triggers = sum(int(e.get("strict_short_triggers", 0)) for e in evals)

    latest_5m: pd.Timestamp | None = None
    try:
        store = KlineStore()
        m5 = store.load(args.symbol, "5m")
        latest_5m = pd.to_datetime(m5["open_time"].iloc[-1], utc=True)
    except FileNotFoundError:
        pass

    live_sync_enabled = False
    try:
        from bnb_quant_v2.data.live.config import load_live_sync_config

        live_sync_enabled = load_live_sync_config().enabled
    except Exception:
        pass

    if not live_sync_enabled and not sync_5m:
        sync_5m_ok, sync_5m_total = 0, 0
        sync_1h_ok, sync_1h_total = 0, 0
        status = "⚠️ 离线/mock（阶段 B 未启用）"
    else:
        sync_5m_ok = sum(1 for e in sync_5m if e.get("ok"))
        sync_5m_total = len(sync_5m) or 288
        sync_1h_ok = sum(1 for e in sync_1h if e.get("ok"))
        sync_1h_total = len(sync_1h) or 24
        status = "✅ 正常" if sync_5m_ok >= sync_5m_total * 0.99 else "⚠️ sync 有失败"

    text = format_heartbeat_message(
        period_start=period_start,
        period_end=period_end,
        sync_5m_ok=sync_5m_ok,
        sync_5m_total=sync_5m_total,
        sync_1h_ok=sync_1h_ok,
        sync_1h_total=sync_1h_total,
        eval_count=len(evals) or 24,
        primary_triggers=primary_triggers,
        strict_triggers=strict_triggers,
        primary_short_triggers=primary_short_triggers,
        strict_short_triggers=strict_short_triggers,
        latest_5m=latest_5m,
        status=status,
    )

    print(text)

    tg_cfg = load_telegram_config(args.telegram_config)
    if args.dry_run:
        tg_cfg = type(tg_cfg)(**{**tg_cfg.__dict__, "dry_run": True})

    if not tg_cfg.send_daily_heartbeat and not args.dry_run:
        print("心跳已禁用（send_daily_heartbeat=false）")
        return 0

    res = TelegramClient(tg_cfg).send(text)
    if not res.ok and not res.dry_run:
        print(f"发送失败: {res.error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
