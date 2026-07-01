#!/usr/bin/env python3
"""第 t 根 K 线 → 预测第 t+1 根开→收方向（对比分析）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.analysis.prediction_1h import (
    analyze_1h_prediction,
    compare_prev1_rules,
    compare_prev2_rules,
    compare_prev2_shadow_body_rules,
    compare_shadow_body_rules,
)
from bnb_quant_v2.data.kline_store import KlineStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Bar-t next-bar direction comparison")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--path", type=Path, default=None)
    parser.add_argument(
        "--prev",
        type=int,
        default=1,
        choices=(1, 2),
        help="前置 K 线根数：1=第t根→第t+1根（默认），2=前两根→当前",
    )
    parser.add_argument("--rule", default=None, help="只跑指定规则")
    parser.add_argument(
        "--shadow-body",
        action="store_true",
        help="影线/实体分析（prev=1 第t根→t+1，prev=2 前两根组合→当前）",
    )
    args = parser.parse_args()

    if args.path:
        import pandas as pd

        df = pd.read_parquet(args.path)
    else:
        df = KlineStore().load(args.symbol, args.interval)

    if args.shadow_body:
        if args.prev == 2:
            compare_prev2_shadow_body_rules(df)
        else:
            compare_shadow_body_rules(df)
    elif args.rule:
        analyze_1h_prediction(df, rule_name=args.rule, prev_bars=args.prev)
    elif args.prev == 2:
        compare_prev2_rules(df)
    else:
        compare_prev1_rules(df)


if __name__ == "__main__":
    main()
