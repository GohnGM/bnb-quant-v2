#!/usr/bin/env python3
"""实时 K 线增量同步（计划任务入口）。

启用步骤见 docs/RUN.md「实时数据（Gate）」。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.notify.config import load_env_file
from bnb_quant_v2.data.live import cron_hints, load_live_sync_config, run_live_sync


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(description="Live kline sync (scheduled task stub)")
    parser.add_argument("--interval", default=None, help="5m 或 1h；默认跑配置中全部")
    parser.add_argument("--config", type=Path, default=None, help="live_sync.yaml 路径")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="真实拉取并写入（需 config enabled=true；默认 dry-run）",
    )
    parser.add_argument("--show-cron", action="store_true", help="打印建议 crontab")
    args = parser.parse_args()

    if args.show_cron:
        cron_hints()
        return

    cfg = load_live_sync_config(args.config)
    dry_run = not args.execute
    intervals = [args.interval] if args.interval else cfg.intervals

    for iv in intervals:
        run_live_sync(cfg, iv, dry_run=dry_run)


if __name__ == "__main__":
    main()
