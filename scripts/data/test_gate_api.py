#!/usr/bin/env python3
"""Gate API 连通性测试（交接 / 排障用）。

不写入 parquet，只测网络 + 解析是否正常。

用法:
    PYTHONPATH=src python scripts/data/test_gate_api.py
    PYTHONPATH=src python scripts/data/test_gate_api.py --interval 1h
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.data.live.gate_rest import (
    GATE_API_BASE,
    fetch_spot_candlesticks,
    load_gate_credentials,
)
from bnb_quant_v2.notify.config import load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Gate spot candlesticks API")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="5m", choices=["5m", "1h"])
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    load_env_file()
    key, secret = load_gate_credentials()
    print(f"Gate API: {GATE_API_BASE}")
    print(f"GATE_API_KEY: {'已配置 (' + key[:8] + '...)' if key else '未配置（公开接口可不用）'}")
    print(f"测试: {args.symbol} {args.interval} limit={args.limit}")
    print()

    try:
        df = fetch_spot_candlesticks(
            args.symbol,
            args.interval,
            limit=args.limit,
            api_key=key,
        )
    except Exception as e:
        print(f"✗ Gate API 失败: {e}")
        print()
        print("排障建议:")
        print("  1. curl -s \"https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair=BTC_USDT&interval=5m&limit=3\"")
        print("  2. 检查代理 / 防火墙 / 地区网络")
        print("  3. 可选：在 .env 配置 GATE_API_KEY")
        print("  详见 docs/GATE_API_SETUP.md")
        return 1

    if df.empty:
        print("✗ API 返回 0 行")
        return 1

    last = df.iloc[-1]
    print(f"✓ Gate API 可达，返回 {len(df)} 根 {args.interval} K 线")
    print(f"  最新 open_time: {last['open_time']}")
    print(f"  OHLC: {last['open']} / {last['high']} / {last['low']} / {last['close']}")
    print()

    store = KlineStore()
    p = store.path(args.symbol, args.interval)
    if p.exists():
        local = store.load(args.symbol, args.interval)
        local_last = local["open_time"].iloc[-1]
        print(f"本地 parquet: {p}")
        print(f"  行数: {len(local)}")
        print(f"  最后一条: {local_last}")
        print("  → 若明显早于 API 最新时间，请运行 sync_live_klines.py --execute")
    else:
        print(f"本地 parquet 不存在: {p}")
        print("  → 可先 import_gate.py 导入历史，或 sync --execute 冷启动")

    print()
    print("下一步:")
    print("  PYTHONPATH=src python scripts/data/sync_live_klines.py --interval 5m --execute")
    return 0


if __name__ == "__main__":
    sys.exit(main())
