#!/usr/bin/env python3
"""5m 微观结构分析 CLI。

默认 --mode t-next：阶段 4，第 t 根整小时 5m → 下一根 1H。
--mode p1-f6：前一根 1H+5m + 当前小时前 6 根 5m → 当前 1H。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.analysis.intra_5m import enrich_1h_with_intra, enrich_p1_f6
from bnb_quant_v2.analysis.prediction_intra import compare_intra_descriptive, export_intra_descriptive_csv
from bnb_quant_v2.analysis.prediction_p1_f6 import compare_p1_f6_descriptive, export_p1_f6_cross_csv
from bnb_quant_v2.data.kline_store import KlineStore

DEFAULT_FEATURES = ROOT / "data" / "analysis" / "BTCUSDT_1h_intra5m_features.parquet"
DEFAULT_CSV = ROOT / "data" / "analysis" / "intra5m_descriptive.csv"
DEFAULT_P1_F6_FEATURES = ROOT / "data" / "analysis" / "BTCUSDT_1h_p1_f6_features.parquet"
DEFAULT_P1_F6_CSV = ROOT / "data" / "analysis" / "intra5m_p1_f6_cross.csv"


def _load_t_next(args: argparse.Namespace):
    import pandas as pd

    if args.path:
        return pd.read_parquet(args.path)
    if DEFAULT_FEATURES.exists() and not args.rebuild:
        return pd.read_parquet(DEFAULT_FEATURES)
    store = KlineStore()
    return enrich_1h_with_intra(store.load(args.symbol, "1h"), store.load(args.symbol, "5m"))


def _load_p1_f6(args: argparse.Namespace):
    import pandas as pd

    if args.path:
        return pd.read_parquet(args.path)
    if DEFAULT_P1_F6_FEATURES.exists() and not args.rebuild:
        return pd.read_parquet(DEFAULT_P1_F6_FEATURES)
    store = KlineStore()
    return enrich_p1_f6(store.load(args.symbol, "1h"), store.load(args.symbol, "5m"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Intra-5m descriptive analysis")
    parser.add_argument(
        "--mode",
        choices=("t-next", "p1-f6"),
        default="t-next",
        help="t-next=阶段4(默认); p1-f6=前一根+前6根5m→当前1H",
    )
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--path", type=Path, default=None, help="特征 parquet 路径")
    parser.add_argument("--rebuild", action="store_true", help="忽略缓存 parquet，从 klines 重算")
    parser.add_argument("--csv", type=Path, default=None, help="导出 CSV 路径")
    args = parser.parse_args()

    if args.mode == "t-next":
        df = _load_t_next(args)
        report = compare_intra_descriptive(df, verbose=True)
        csv_path = args.csv or DEFAULT_CSV
        out = export_intra_descriptive_csv(report, csv_path)
    else:
        df = _load_p1_f6(args)
        report = compare_p1_f6_descriptive(df, verbose=True)
        csv_path = args.csv or DEFAULT_P1_F6_CSV
        out = export_p1_f6_cross_csv(report, csv_path)

    print(f"\nCSV → {out}")


if __name__ == "__main__":
    main()
