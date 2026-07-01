#!/usr/bin/env python3
"""从 Gate 目录导入 K 线到 data/klines/。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.data.importers import discover_gate_files, import_gate_directory


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Gate klines (correct OHLC column order)")
    parser.add_argument("--dir", type=Path, default=None, help="Gate CSV 目录")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--pattern", default="*.csv.gz")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    data_dir = args.dir
    if data_dir is None:
        data_dir = (
            Path.home() / "Downloads" / "5mdata"
            if args.interval == "5m"
            else Path.home() / "Downloads" / "gate1hData"
        )

    if args.dry_run:
        files = discover_gate_files(data_dir, symbol=args.symbol, pattern=args.pattern)
        print(f"目录: {data_dir}")
        print(f"匹配 {len(files)} 个文件 → {args.symbol}_{args.interval}.parquet")
        for f in files:
            print(f"  {f.name}")
        return

    path = import_gate_directory(
        data_dir,
        args.symbol,
        args.interval,
        pattern=args.pattern,
    )
    print(f"OK → {path}")


if __name__ == "__main__":
    main()
