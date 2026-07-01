#!/usr/bin/env python3
""":30 评估 p1×f6 做多/做空四条规则，可选 Telegram 推送。

模块归属：runtime（编排） + analysis（评估） + notify（推送）

典型用法
--------
# 手动评估（不发 Telegram）
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py

# launchd 等价（带 Telegram + dedup）
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py --telegram --mark-sent

# 历史回放
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py --hour-open 2024-01-01T14:00:00+00:00
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.analysis.backtest_p1_f6 import (
    LIVE_PUSH_RULES,
    PRIMARY_HOUR_RULE,
    PRIMARY_HOUR_SHORT_RULE,
    STRICT_HOUR_RULE,
    STRICT_HOUR_SHORT_RULE,
)
from bnb_quant_v2.notify.config import load_telegram_config
from bnb_quant_v2.data.live.config import load_live_sync_config
from bnb_quant_v2.analysis.evaluator import rule_tier
from bnb_quant_v2.runtime.dedup import SignalDedup
from bnb_quant_v2.runtime.pipeline import run_eval_pipeline
from bnb_quant_v2.runtime.run_stats import append_run_event

DEFAULT_OUTPUT = ROOT / "data" / "live" / "latest_signal.json"


def _parse_as_of(value: str) -> datetime:
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate p1×f6 live signals at :30")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="回放时刻 ISO8601（默认 UTC now）；回放时默认不 sync",
    )
    parser.add_argument("--hour-open", type=str, default=None, help="显式指定 1H open_time")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mark-sent", action="store_true", help="dedup 标记已推送")
    parser.add_argument("--no-dedup", action="store_true")
    parser.add_argument("--exit-on-trigger", action="store_true")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="评估前 sync 5m（阶段 B/C7；需 live_sync.enabled=true）",
    )
    parser.add_argument(
        "--sync-dry-run",
        action="store_true",
        help="sync 仅打印计划，不写入",
    )
    parser.add_argument(
        "--telegram",
        action="store_true",
        help="推送触发信号 / 数据不足告警（阶段 D）",
    )
    parser.add_argument(
        "--telegram-config",
        type=Path,
        default=None,
        help="telegram.yaml 路径",
    )
    args = parser.parse_args()

    as_of = _parse_as_of(args.as_of) if args.as_of else None
    hour_open = _parse_as_of(args.hour_open) if args.hour_open else None
    is_replay = as_of is not None or hour_open is not None

    tg_cfg = load_telegram_config(args.telegram_config)
    if args.telegram and tg_cfg.dry_run:
        print("Telegram: dry_run（打印/模拟，不调用 API）")

    try:
        pipeline = run_eval_pipeline(
            args.symbol,
            as_of=as_of,
            hour_open=hour_open,
            sync_before=args.sync and not is_replay,
            sync_dry_run=args.sync_dry_run,
            notify=args.telegram,
            mark_sent=args.mark_sent or args.telegram,
            no_dedup=args.no_dedup,
            live_sync_cfg=load_live_sync_config(),
            tg_cfg=tg_cfg if args.telegram else None,
        )
    except FileNotFoundError as e:
        msg = f"缺少 K 线 parquet — {e}"
        print(f"错误: {msg}", file=sys.stderr)
        if args.telegram and tg_cfg.send_on_error:
            from bnb_quant_v2.notify.format import format_alert_message
            from bnb_quant_v2.notify.telegram import TelegramClient

            TelegramClient(tg_cfg).send(format_alert_message("eval 失败", msg))
        return 1

    result = pipeline.eval
    if pipeline.sync:
        append_run_event(
            "sync_5m",
            ok=pipeline.sync.ok,
            detail=pipeline.sync.detail,
            dry_run=args.sync_dry_run,
        )
        print(f"sync: ok={pipeline.sync.ok} {pipeline.sync.detail}")

    append_run_event(
        "eval",
        ready=result.ready,
        any_triggered=result.any_triggered,
        skip_reason=result.skip_reason,
        hour_open=result.hour_open_time.isoformat(),
        primary_triggers=sum(
            1 for s in result.signals if s.triggered and s.rule == PRIMARY_HOUR_RULE
        ),
        strict_triggers=sum(
            1 for s in result.signals if s.triggered and s.rule == STRICT_HOUR_RULE
        ),
        primary_short_triggers=sum(
            1 for s in result.signals if s.triggered and s.rule == PRIMARY_HOUR_SHORT_RULE
        ),
        strict_short_triggers=sum(
            1 for s in result.signals if s.triggered and s.rule == STRICT_HOUR_SHORT_RULE
        ),
    )

    if args.mark_sent and not args.telegram and pipeline.triggered_new:
        dedup = SignalDedup()
        dedup.load()
        for item in pipeline.triggered_new:
            dedup.mark_sent(result.hour_open_time, item["rule"])
        dedup.save()

    payload = result.to_dict()
    payload["rules"] = list(LIVE_PUSH_RULES)
    payload["primary_rule"] = PRIMARY_HOUR_RULE
    payload["strict_rule"] = STRICT_HOUR_RULE
    payload["primary_short_rule"] = PRIMARY_HOUR_SHORT_RULE
    payload["strict_short_rule"] = STRICT_HOUR_SHORT_RULE
    payload["triggered_new"] = pipeline.triggered_new
    payload["triggered_skipped"] = pipeline.triggered_skipped
    if pipeline.sync:
        payload["sync"] = {
            "attempted": pipeline.sync.attempted,
            "ok": pipeline.sync.ok,
            "detail": pipeline.sync.detail,
        }
    if pipeline.notify:
        payload["notify"] = {
            "signals_sent": pipeline.notify.signals_sent,
            "alerts_sent": pipeline.notify.alerts_sent,
            "dry_run": pipeline.notify.dry_run,
            "errors": pipeline.notify.errors,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"as_of={payload['as_of']} hour={payload['hour_open_time']} ready={result.ready}")
    if result.skip_reason:
        print(f"  skip: {result.skip_reason}")
    for sig in result.signals:
        tier = rule_tier(sig.rule)
        flag = "TRIGGER" if sig.triggered else "—"
        strength = sig.f6_close_strength
        strength_s = f"{strength:.2%}" if strength == strength else "n/a"
        print(
            f"  [{flag}] {tier}: dir={sig.direction} "
            f"p1={sig.p1_candle_type} f6阳={sig.f6_yang_cnt} f6强={strength_s}"
        )
    if pipeline.notify:
        print(
            f"telegram: signals={pipeline.notify.signals_sent} "
            f"alerts={pipeline.notify.alerts_sent} dry_run={pipeline.notify.dry_run}"
        )
        for err in pipeline.notify.errors:
            print(f"  telegram error: {err}", file=sys.stderr)
    print(f"→ {args.output}")

    if args.exit_on_trigger and result.any_triggered:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
