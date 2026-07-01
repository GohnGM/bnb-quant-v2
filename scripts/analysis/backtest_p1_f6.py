#!/usr/bin/env python3
"""p1×f6 策略方向准确率回测（默认主规则：p1大阴 & f6阳>=4 & f6收盘强>=67%）。

模块归属：analysis

示例
----
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --rebuild --yearly --monthly
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --all-rules
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --push-rules --rebuild
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.analysis.backtest_p1_f6 import (
    PRIMARY_HOUR_RULE,
    compare_p1_f6_backtests,
    compare_push_rules_backtest,
    export_p1_f6_monthly_csv,
    export_p1_f6_signals_csv,
    export_p1_f6_summary_csv,
    print_p1_f6_backtest_report,
    print_p1_f6_monthly_accuracy,
    print_p1_f6_yearly_accuracy,
    run_p1_f6_backtest,
    run_primary_hour_backtest,
)
from bnb_quant_v2.analysis.intra_5m import enrich_p1_f6
from bnb_quant_v2.data.kline_store import KlineStore

DEFAULT_FEATURES = ROOT / "data" / "analysis" / "BTCUSDT_1h_p1_f6_features.parquet"
DEFAULT_SUMMARY = ROOT / "data" / "analysis" / "p1_f6_hour_backtest_summary.csv"
DEFAULT_PUSH_COMPARE = ROOT / "data" / "analysis" / "p1_f6_push_rules_compare.csv"
DEFAULT_SIGNALS = ROOT / "data" / "analysis" / "p1_f6_primary_signals.csv"
DEFAULT_MONTHLY = ROOT / "data" / "analysis" / "p1_f6_primary_monthly.csv"


def _load_frame(args: argparse.Namespace):
    import pandas as pd

    if args.path:
        return pd.read_parquet(args.path)
    if DEFAULT_FEATURES.exists() and not args.rebuild:
        return pd.read_parquet(DEFAULT_FEATURES)
    store = KlineStore()
    return enrich_p1_f6(store.load(args.symbol, "1h"), store.load(args.symbol, "5m"))


def main() -> None:
    parser = argparse.ArgumentParser(description="p1×f6 direction accuracy backtest")
    parser.add_argument(
        "--target",
        choices=("hour", "half2"),
        default="hour",
        help="hour=整根1H(默认), half2=后30分钟",
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--path", type=Path, default=None, help="p1_f6 特征 parquet")
    parser.add_argument("--rebuild", action="store_true", help="从 klines 重算特征")
    parser.add_argument("--rule", default=None, help="指定规则（默认主规则）")
    parser.add_argument(
        "--all-rules",
        action="store_true",
        help="对比全部规则（默认只跑主规则）",
    )
    parser.add_argument(
        "--push-rules",
        action="store_true",
        help="对比四条推送规则（做多主/严格 + 做空主/严格）并导出 CSV",
    )
    parser.add_argument("--csv", type=Path, default=None, help="汇总 CSV 路径")
    parser.add_argument("--signals-csv", type=Path, default=None, help="信号明细 CSV")
    parser.add_argument("--monthly-csv", type=Path, default=None, help="逐月统计 CSV")
    parser.add_argument("--yearly", action="store_true", help="输出按年准确率")
    parser.add_argument("--monthly", action="store_true", help="输出逐月准确率")
    args = parser.parse_args()

    target_col = "hour_up" if args.target == "hour" else "half2_up"
    df = _load_frame(args)

    if args.push_rules:
        reports = compare_push_rules_backtest(df, target_col=target_col, verbose=True)
        out = export_p1_f6_summary_csv(reports, args.csv or DEFAULT_PUSH_COMPARE)
        print(f"\n推送规则对比 CSV → {out}")
        return

    if args.all_rules:
        reports = compare_p1_f6_backtests(df, target_col=target_col, verbose=True)
        default_summary = (
            ROOT / "data" / "analysis" / "p1_f6_hour_backtest_summary.csv"
            if args.target == "hour"
            else ROOT / "data" / "analysis" / "p1_f6_half2_backtest_summary.csv"
        )
        out = export_p1_f6_summary_csv(reports, args.csv or default_summary)
        print(f"\n汇总 CSV → {out}")
        return

    if args.target == "hour" and args.rule is None and not args.yearly and not args.monthly:
        report, monthly = run_primary_hour_backtest(df, verbose=True)
        export_p1_f6_signals_csv(report, args.signals_csv or DEFAULT_SIGNALS)
        export_p1_f6_monthly_csv(monthly, args.monthly_csv or DEFAULT_MONTHLY)
        print(f"\n信号明细 → {args.signals_csv or DEFAULT_SIGNALS}")
        print(f"逐月统计 → {args.monthly_csv or DEFAULT_MONTHLY}")
        return

    rule = args.rule or (PRIMARY_HOUR_RULE if args.target == "hour" else None)
    if rule is None:
        reports = compare_p1_f6_backtests(df, target_col=target_col, verbose=True)
        out = export_p1_f6_summary_csv(reports, args.csv or DEFAULT_SUMMARY)
        print(f"\n汇总 CSV → {out}")
        return

    report = run_p1_f6_backtest(df, target_col=target_col, rule_name=rule)
    assert not isinstance(report, list)
    print_p1_f6_backtest_report(report)
    if args.yearly:
        print_p1_f6_yearly_accuracy(df, rule, target_col=target_col)
    if args.monthly:
        monthly = print_p1_f6_monthly_accuracy(df, rule, target_col=target_col)
        out = export_p1_f6_monthly_csv(monthly, args.monthly_csv or DEFAULT_MONTHLY)
        print(f"逐月统计 → {out}")
    out = export_p1_f6_signals_csv(report, args.signals_csv or DEFAULT_SIGNALS)
    print(f"信号明细 → {out}")


if __name__ == "__main__":
    main()
