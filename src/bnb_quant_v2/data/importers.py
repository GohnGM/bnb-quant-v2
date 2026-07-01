"""Gate 历史 CSV 导入与 K 线规范化。

Gate 官方 CSV 列顺序（无表头时）::

    timestamp, volume, close, high, low, open

文件名约定（月度）::

    BTC_USDT-202401.csv.gz

导入流程
--------
1. ``discover_gate_files`` 扫描目录
2. ``read_gate_csv`` 逐文件读取并 ``normalize_kline_dataframe``
3. 合并去重 → ``KlineStore.save_dataframe``
4. 可选 ``audit_klines`` 质量检查
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from bnb_quant_v2.data.quality import audit_klines

# Gate 官方: timestamp, volume, close, high, low, open
GATE_CSV_COLUMNS = ("timestamp", "volume", "close", "high", "low", "open")
REQUIRED_COLS = ("open", "high", "low", "close", "volume")
GATE_MONTHLY_PATTERN = __import__("re").compile(
    r"^(?P<pair>[A-Za-z0-9]+_[A-Za-z0-9]+)-(?P<ym>\d{6})\.csv(?:\.gz)?$",
    __import__("re").IGNORECASE,
)

INTERVAL_BAR_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


def audit_interval_minutes(interval: str) -> float | None:
    """将周期字符串转为分钟数，供 ``audit_klines`` 检查时间间隔。"""
    return INTERVAL_BAR_MINUTES.get(interval.lower())


def symbol_to_gate_pair(symbol: str) -> str:
    """``BTCUSDT`` → ``BTC_USDT``（Gate 交易对命名）。"""
    upper = symbol.upper()
    if upper.endswith("USDT") and len(upper) > 4:
        return f"{upper[:-4]}_USDT"
    return upper


def _compression_for(path: Path) -> str | None:
    return "gzip" if path.name.lower().endswith(".gz") else None


def _parse_timestamps(series: pd.Series) -> pd.Series:
    """自动识别秒/毫秒时间戳或 ISO 字符串。"""
    numeric = pd.to_numeric(series, errors="coerce")
    sample = numeric.dropna()
    if sample.empty:
        return pd.to_datetime(series, utc=True)
    if sample.iloc[0] > 1e12:
        return pd.to_datetime(numeric, unit="ms", utc=True)
    return pd.to_datetime(numeric, unit="s", utc=True)


def read_gate_csv(csv_path: Path) -> pd.DataFrame:
    """读取单个 Gate CSV（支持 .gz、有/无表头）。"""
    compression = _compression_for(csv_path)
    peek = pd.read_csv(csv_path, compression=compression, nrows=1, header=None)
    if peek.shape[1] == 6 and pd.api.types.is_numeric_dtype(peek.iloc[:, 0]):
        df = pd.read_csv(
            csv_path,
            compression=compression,
            header=None,
            names=list(GATE_CSV_COLUMNS),
        )
    else:
        df = pd.read_csv(csv_path, compression=compression)
    return normalize_kline_dataframe(df)


def normalize_kline_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """将任意 Gate/通用 CSV 规范为 KlineStore 标准列。

    输出列：``open_time, open, high, low, close, volume, closed``（全部 UTC）。
    """
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    if "timestamp" in df.columns:
        df.rename(columns={"timestamp": "open_time"}, inplace=True)
    elif "open_time" not in df.columns:
        raise ValueError(f"缺少时间列，当前: {list(df.columns)}")

    if "size" in df.columns and "volume" not in df.columns:
        df.rename(columns={"size": "volume"}, inplace=True)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"缺少 OHLCV 列: {missing}")

    df["open_time"] = _parse_timestamps(df["open_time"])
    for col in REQUIRED_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["open_time", *REQUIRED_COLS])
    df["closed"] = True
    return df[["open_time", *REQUIRED_COLS, "closed"]].sort_values("open_time").reset_index(drop=True)


def discover_gate_files(
    directory: Path,
    *,
    symbol: str | None = None,
    pattern: str = "*.csv.gz",
) -> list[Path]:
    """扫描目录下 Gate 月度 CSV，可按 ``symbol`` 过滤交易对。"""
    root = directory.expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"目录不存在: {root}")

    expected = symbol_to_gate_pair(symbol).upper() if symbol else None
    paths = sorted(root.glob(pattern))
    if not paths and pattern == "*.csv.gz":
        paths = sorted(root.glob("*.csv"))

    matched: list[Path] = []
    for path in paths:
        m = GATE_MONTHLY_PATTERN.match(path.name)
        if m:
            if expected and m.group("pair").upper() != expected:
                continue
        matched.append(path)
    return matched


def import_gate_directory(
    directory: Path,
    symbol: str,
    interval: str,
    *,
    pattern: str = "*.csv.gz",
    run_quality_check: bool = True,
) -> Path:
    """批量导入 Gate CSV 目录并写入 ``KlineStore``。

    Returns:
        写入的 parquet 路径。
    """
    from bnb_quant_v2.data.kline_store import KlineStore

    files = discover_gate_files(directory, symbol=symbol, pattern=pattern)
    if not files:
        raise FileNotFoundError(f"未找到 Gate CSV: {directory}")

    frames = []
    for path in files:
        logger.info("Reading {}", path.name)
        frames.append(read_gate_csv(path))

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["open_time"], keep="last")
    merged = merged.sort_values("open_time").reset_index(drop=True)

    store = KlineStore()
    out = store.save_dataframe(symbol, interval, merged)
    logger.info("Saved {} bars → {}", len(merged), out)

    if run_quality_check:
        bar_minutes = audit_interval_minutes(interval)
        if bar_minutes is not None:
            report = audit_klines(merged, bar_minutes=bar_minutes)
        else:
            report = audit_klines(merged)
        logger.info("Quality: {}", report.summary())
        if report.has_critical_issues:
            logger.warning("K 线质量检查发现异常，请查看报告")

    return out
