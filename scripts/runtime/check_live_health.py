#!/usr/bin/env python3
"""本机 live 流水线健康检查。

模块归属：runtime（读 run_stats） + data（K 线新鲜度） + notify（配置）

检查项：5m/1h 数据是否过旧、近 26h eval/sync 记录、Telegram 是否可发。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.data.live.config import load_live_sync_config
from bnb_quant_v2.notify.config import load_telegram_config
from bnb_quant_v2.runtime.run_stats import DEFAULT_STATS_PATH, _load_events

LOG_DIR = ROOT / "logs"
STALE_5M_MINUTES = 15
STALE_1H_HOURS = 2


def _read_log_mtime(name: str) -> datetime | None:
    p = LOG_DIR / name
    if not p.exists():
        return None
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)


def _kline_age(symbol: str, interval: str) -> dict:
    store = KlineStore()
    try:
        df = store.load(symbol, interval)
        last = pd.to_datetime(df["open_time"].iloc[-1], utc=True)
        age = datetime.now(timezone.utc) - last.to_pydatetime()
        return {
            "ok": True,
            "last_open_time": last.isoformat(),
            "age_minutes": round(age.total_seconds() / 60, 1),
            "rows": len(df),
        }
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}


def _recent_events(hours: float = 26) -> list[dict]:
    if not DEFAULT_STATS_PATH.exists():
        return []
    end = datetime.now(timezone.utc)
    start = end - pd.Timedelta(hours=hours).to_pytimedelta()
    return [
        e
        for e in _load_events(DEFAULT_STATS_PATH)
        if start <= datetime.fromisoformat(e["at"]).replace(tzinfo=timezone.utc) <= end
    ]


def run_health_check(symbol: str = "BTCUSDT") -> dict:
    now = datetime.now(timezone.utc)
    live_sync = load_live_sync_config()
    telegram = load_telegram_config()

    m5 = _kline_age(symbol, "5m")
    h1 = _kline_age(symbol, "1h")
    events = _recent_events()

    evals = [e for e in events if e.get("type") == "eval"]
    sync5 = [e for e in events if e.get("type") == "sync_5m"]
    last_eval = evals[-1] if evals else None

    issues: list[str] = []
    warnings: list[str] = []

    if not m5.get("ok"):
        issues.append(f"缺少 5m parquet: {m5.get('error')}")
    elif m5["age_minutes"] > STALE_5M_MINUTES:
        if live_sync.enabled:
            issues.append(f"5m 数据偏旧 ({m5['age_minutes']} 分钟)")
        else:
            warnings.append(
                f"5m 数据偏旧 ({m5['age_minutes']} 分钟)；live_sync 未启用，离线数据属预期"
            )

    if not h1.get("ok"):
        issues.append(f"缺少 1h parquet: {h1.get('error')}")
    elif h1["age_minutes"] > STALE_1H_HOURS * 60:
        if live_sync.enabled:
            issues.append(f"1h 数据偏旧 ({h1['age_minutes']} 分钟)")
        else:
            warnings.append(f"1h 数据偏旧；live_sync 未启用")

    if live_sync.enabled and not sync5:
        warnings.append("过去 26h 无 sync_5m 记录（launchd 未跑或阶段 B 未通）")

    if not evals:
        warnings.append("过去 26h 无 eval 记录（:30 任务可能未启动）")
    elif last_eval and not last_eval.get("ready"):
        warnings.append(f"最近一次 eval 未就绪: {last_eval.get('skip_reason')}")

    if not telegram.can_send and not telegram.dry_run:
        warnings.append("Telegram 未配置完整（缺 token/chat_id）")

    signal_log = _read_log_mtime("signal.log")
    if signal_log is None:
        warnings.append("logs/signal.log 不存在（尚未有定时任务输出）")

    status = "ok" if not issues else "error"
    if status == "ok" and warnings:
        status = "warn"

    return {
        "checked_at": now.isoformat(),
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "live_sync_enabled": live_sync.enabled,
        "telegram_ready": telegram.can_send or telegram.dry_run,
        "klines": {"5m": m5, "1h": h1},
        "run_stats_26h": {
            "eval_count": len(evals),
            "sync_5m_count": len(sync5),
            "last_eval": last_eval,
        },
        "logs": {
            "signal.log_mtime": signal_log.isoformat() if signal_log else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Live pipeline health check")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    report = run_health_check(args.symbol)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"状态: {report['status'].upper()}  @ {report['checked_at']}")
        print(f"live_sync.enabled={report['live_sync_enabled']}")
        m5 = report["klines"]["5m"]
        h1 = report["klines"]["1h"]
        if m5.get("ok"):
            print(f"5m: last={m5['last_open_time']} age={m5['age_minutes']}min")
        if h1.get("ok"):
            print(f"1h: last={h1['last_open_time']} age={h1['age_minutes']}min")
        rs = report["run_stats_26h"]
        print(f"26h eval={rs['eval_count']} sync_5m={rs['sync_5m_count']}")
        for w in report["warnings"]:
            print(f"  ⚠ {w}")
        for i in report["issues"]:
            print(f"  ✗ {i}")

    return 2 if report["status"] == "error" else (1 if report["status"] == "warn" else 0)


if __name__ == "__main__":
    sys.exit(main())
