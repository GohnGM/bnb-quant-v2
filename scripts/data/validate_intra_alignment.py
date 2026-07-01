#!/usr/bin/env python3
"""校验 5m 聚合与 1H K 线 OHLC 是否一致。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.analysis.intra_5m import (
    align_5m_to_1h,
    filter_complete_hours,
    list_incomplete_hours,
    print_alignment_report,
    validate_hour_alignment,
)
from bnb_quant_v2.data.kline_store import KlineStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate 5m vs 1h alignment")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--path-1h", type=Path, default=None)
    parser.add_argument("--path-5m", type=Path, default=None)
    args = parser.parse_args()

    store = KlineStore()
    if args.path_1h:
        import pandas as pd

        df_1h = pd.read_parquet(args.path_1h)
    else:
        df_1h = store.load(args.symbol, "1h")

    if args.path_5m:
        import pandas as pd

        df_5m = pd.read_parquet(args.path_5m)
    else:
        df_5m = store.load(args.symbol, "5m")

    aligned = align_5m_to_1h(df_1h, df_5m, complete_only=False)
    incomplete = list_incomplete_hours(aligned)
    if not incomplete.empty:
        print(f"--- 已过滤不完整小时: {len(incomplete)} 个 ---")
        for _, row in incomplete.iterrows():
            print(f"  {row['open_time']}  m5_count={int(row['m5_count'])}")
        print()

    filtered = filter_complete_hours(aligned)
    report = validate_hour_alignment(filtered)
    print_alignment_report(report)

    if not report.passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
