"""Gate.io REST v4 — spot K 线（公开接口，API Key 可选）。

文档：https://www.gate.io/docs/developers/apiv4/en/#market-candlesticks

响应每行（与 Gate CSV 一致）::

    [timestamp, volume, close, high, low, open]

注意：``limit`` 与 ``from``/``to`` 互斥，增量同步使用 ``from``+``to``。
单次最多 1000 根，超出时本模块自动分片请求。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from bnb_quant_v2.data.importers import GATE_CSV_COLUMNS, normalize_kline_dataframe, symbol_to_gate_pair

GATE_API_BASE = "https://api.gateio.ws/api/v4"
MAX_CANDLES_PER_REQUEST = 1000

_INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def load_gate_credentials() -> tuple[str, str]:
    """从环境变量读取 Gate 凭证（公开 K 线可不填）。"""
    return os.environ.get("GATE_API_KEY", ""), os.environ.get("GATE_API_SECRET", "")


def _interval_seconds(interval: str) -> int:
    if interval not in _INTERVAL_SECONDS:
        raise ValueError(f"Gate 不支持的 interval: {interval}")
    return _INTERVAL_SECONDS[interval]


def parse_gate_candlesticks(rows: list) -> pd.DataFrame:
    """将 Gate API 原始二维数组转为标准 K 线 DataFrame。"""
    if not rows:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume", "closed"])
    df = pd.DataFrame(rows, columns=list(GATE_CSV_COLUMNS))
    return normalize_kline_dataframe(df)


def _http_get_candlesticks(
    params: dict[str, str | int],
    *,
    api_key: str = "",
    timeout: int = 30,
) -> list:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{GATE_API_BASE}/spot/candlesticks?{query}"
    headers = {"Accept": "application/json", "User-Agent": "bnb-quant-v2/0.1"}
    if api_key:
        headers["KEY"] = api_key
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gate API HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gate API 网络错误: {e}") from e
    if not isinstance(body, list):
        raise RuntimeError(f"Gate API 响应异常: {body!r}")
    return body


def fetch_spot_candlesticks(
    symbol: str,
    interval: str,
    *,
    from_ts: int | None = None,
    to_ts: int | None = None,
    limit: int | None = None,
    api_key: str = "",
) -> pd.DataFrame:
    """拉取 Gate spot K 线并规范为标准列。

    使用 ``from_ts``+``to_ts`` 时不可传 ``limit``（Gate 限制）。
  仅 ``limit`` 时拉最近 N 根（适合冷启动无 parquet）。
    """
    pair = symbol_to_gate_pair(symbol)
    base_params: dict[str, str | int] = {
        "currency_pair": pair,
        "interval": interval,
    }

    if from_ts is not None or to_ts is not None:
        if limit is not None:
            raise ValueError("Gate API: limit 与 from/to 互斥")
        end = to_ts if to_ts is not None else int(datetime.now(timezone.utc).timestamp())
        start = from_ts if from_ts is not None else end - _interval_seconds(interval) * 100
        return _fetch_range(symbol, interval, start, end, api_key=api_key)

    req_limit = min(int(limit or 100), MAX_CANDLES_PER_REQUEST)
    rows = _http_get_candlesticks({**base_params, "limit": req_limit}, api_key=api_key)
    return parse_gate_candlesticks(rows)


def _fetch_range(
    symbol: str,
    interval: str,
    from_ts: int,
    to_ts: int,
    *,
    api_key: str = "",
) -> pd.DataFrame:
    """按时间范围分片拉取（每片 ≤1000 根）。"""
    if from_ts >= to_ts:
        return parse_gate_candlesticks([])

    step = _interval_seconds(interval) * MAX_CANDLES_PER_REQUEST
    pair = symbol_to_gate_pair(symbol)
    frames: list[pd.DataFrame] = []
    cursor = from_ts

    while cursor < to_ts:
        chunk_to = min(cursor + step, to_ts)
        rows = _http_get_candlesticks(
            {
                "currency_pair": pair,
                "interval": interval,
                "from": cursor,
                "to": chunk_to,
            },
            api_key=api_key,
        )
        part = parse_gate_candlesticks(rows)
        if not part.empty:
            frames.append(part)
        if not rows:
            break
        last_ts = int(pd.Timestamp(part["open_time"].iloc[-1]).timestamp())
        next_cursor = last_ts + _interval_seconds(interval)
        if next_cursor <= cursor:
            break
        cursor = next_cursor

    if not frames:
        return parse_gate_candlesticks([])
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["open_time"], keep="last")
    return merged.sort_values("open_time").reset_index(drop=True)
