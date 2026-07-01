"""实时 K 线增量同步调度。

流程（``--execute``）
--------------------
1. ``build_sync_plan`` — 计算 since / lookback
2. ``GateFetcher.fetch_klines`` — REST 拉取
3. ``KlineStore.merge_append`` — 合并 parquet
4. ``audit_klines`` — 质量检查
5. ``append_run_event`` — 写入 run_stats（供健康检查）
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bnb_quant_v2.data.importers import audit_interval_minutes
from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.data.live.config import LiveSyncConfig
from bnb_quant_v2.data.live.fetcher import FetchRequest, LiveDataUnavailableError, get_fetcher
from bnb_quant_v2.data.quality import audit_klines


@dataclass
class SyncPlan:
    """单次同步计划（dry-run 与真实模式共用）。"""

    symbol: str
    interval: str
    source: str
    store_path: str
    lookback_bars: int
    since: datetime | None
    enabled: bool
    dry_run: bool

    def describe(self) -> str:
        since_s = self.since.isoformat() if self.since else "latest"
        mode = "DRY-RUN" if self.dry_run else ("LIVE" if self.enabled else "DISABLED")
        return (
            f"[{mode}] {self.symbol} {self.interval} via {self.source} | "
            f"lookback={self.lookback_bars} since={since_s} → {self.store_path}"
        )


def build_sync_plan(
    cfg: LiveSyncConfig,
    interval: str,
    *,
    dry_run: bool = True,
) -> SyncPlan:
    """构建同步计划：从已有 parquet 末尾向前回溯 ``lookback_bars`` 根作为 ``since``。"""
    store = KlineStore(cfg.store_dir)
    lookback = cfg.lookback_bars.get(interval, 24)
    since: datetime | None = None
    p = store.path(cfg.symbol, interval)
    if p.exists():
        try:
            df = store.load(cfg.symbol, interval)
            if len(df):
                last = df["open_time"].iloc[-1]
                if hasattr(last, "to_pydatetime"):
                    last = last.to_pydatetime()
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                since = last - _interval_delta(interval, lookback)
        except FileNotFoundError:
            pass
    return SyncPlan(
        symbol=cfg.symbol,
        interval=interval,
        source=cfg.source,
        store_path=str(p),
        lookback_bars=lookback,
        since=since,
        enabled=cfg.enabled,
        dry_run=dry_run,
    )


def _interval_delta(interval: str, bars: int) -> timedelta:
    if interval.endswith("m"):
        minutes = int(interval[:-1]) * bars
        return timedelta(minutes=minutes)
    if interval.endswith("h"):
        hours = int(interval[:-1]) * bars
        return timedelta(hours=hours)
    raise ValueError(f"不支持的 interval: {interval}")


def run_live_sync(
    cfg: LiveSyncConfig,
    interval: str,
    *,
    dry_run: bool = True,
) -> SyncPlan:
    """执行一次增量同步。

    - ``dry_run=True``：只打印计划，不写 parquet
    - ``cfg.enabled=False`` 且非 dry-run：抛 ``LiveDataUnavailableError``
    """
    plan = build_sync_plan(cfg, interval, dry_run=dry_run)
    print(plan.describe())

    if dry_run:
        print("  → dry-run：跳过网络请求与 parquet 写入")
        return plan

    if not cfg.enabled:
        raise LiveDataUnavailableError(
            "live_sync.enabled=false。先在 config/live_sync.yaml 设 enabled: true。"
        )

    from bnb_quant_v2.runtime.run_stats import append_run_event

    fetcher = get_fetcher(cfg.source, enabled=True)
    req = FetchRequest(
        symbol=plan.symbol,
        interval=plan.interval,
        since=plan.since,
        limit=plan.lookback_bars,
    )
    try:
        bars = fetcher.fetch_klines(req)
        store = KlineStore(cfg.store_dir)
        if bars.empty:
            print("  → Gate 返回 0 行（可能无新 K 线）")
            append_run_event(
                _sync_event_type(interval),
                ok=True,
                detail="fetched=0",
                rows_fetched=0,
            )
            return plan

        out, total_rows = store.merge_append(plan.symbol, plan.interval, bars)
        bar_minutes = audit_interval_minutes(plan.interval)
        report = audit_klines(bars, bar_minutes=bar_minutes) if bar_minutes else audit_klines(bars)
        print(f"  → 拉取 {len(bars)} 行，合并后共 {total_rows} 行 → {out}")
        print(f"  → 质量: {report.summary()}")
        append_run_event(
            _sync_event_type(interval),
            ok=True,
            detail=f"fetched={len(bars)} total={total_rows}",
            rows_fetched=len(bars),
        )
    except Exception as e:
        append_run_event(
            _sync_event_type(interval),
            ok=False,
            detail=str(e),
        )
        raise

    return plan


def _sync_event_type(interval: str) -> str:
    if interval == "5m":
        return "sync_5m"
    if interval == "1h":
        return "sync_1h"
    return f"sync_{interval}"


def cron_hints() -> None:
    """打印建议的 cron / launchd 时间表（UTC）。"""
    print("================== 建议 cron（UTC）==================")
    print("*/5 * * * *  scripts/data/sync_live_klines.py --interval 5m --execute")
    print("2   * * * *  scripts/data/sync_live_klines.py --interval 1h --execute")
    print("30  * * * *  scripts/runtime/eval_p1_f6_signal.py --telegram")
    print("详见 docs/RUN.md")
    print("=" * 50)
