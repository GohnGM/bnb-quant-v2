#!/usr/bin/env python3
"""构建 1H + 小时内 5m 特征表（阶段 3）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.analysis.intra_5m import (
    enrich_1h_with_intra,
    enrich_p1_f6,
    print_intra_feature_summary,
    save_intra_features,
    save_p1_f6_features,
)
from bnb_quant_v2.data.kline_store import KlineStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Build 1h + intra-5m feature parquet")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument(
        "--mode",
        choices=("t-next", "p1-f6"),
        default="t-next",
        help="t-next=阶段3/4特征(默认); p1-f6=前一根+前6根5m特征",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="输出 parquet 路径（默认随 --mode 而定）",
    )
    parser.add_argument("--no-save", action="store_true", help="只打印摘要，不写 parquet")
    args = parser.parse_args()

    store = KlineStore()
    df_1h = store.load(args.symbol, "1h")
    df_5m = store.load(args.symbol, "5m")

    if args.mode == "p1-f6":
        default_out = ROOT / "data" / "analysis" / "BTCUSDT_1h_p1_f6_features.parquet"
        features = enrich_p1_f6(df_1h, df_5m, complete_only=True)
        print(f"p1+f6 样本: {len(features)}  |  hour_up 基准 {features['hour_up'].mean()*100:.2f}%")
    else:
        default_out = ROOT / "data" / "analysis" / "BTCUSDT_1h_intra5m_features.parquet"
        features = enrich_1h_with_intra(df_1h, df_5m, complete_only=True)
        print_intra_feature_summary(features)

    if not args.no_save:
        out = (
            save_p1_f6_features(features, args.output or default_out)
            if args.mode == "p1-f6"
            else save_intra_features(features, args.output or default_out)
        )
        print(f"\n已保存 → {out}  ({len(features)} 行, {len(features.columns)} 列)")


if __name__ == "__main__":
    main()
