"""实时评估流水线：sync → eval → dedup → Telegram。

``run_eval_pipeline`` 是 launchd :30 任务的核心编排函数。

步骤
----
1. （可选）``run_pre_eval_sync`` — eval 前拉取最新 5m
2. ``evaluate_from_store`` — 模块二判定主/严格规则
3. ``SignalDedup`` — 过滤已推送的 (hour, rule)
4. （可选）``run_notify_step`` — 发信号 / 数据不足告警

CLI 入口：``scripts/runtime/eval_p1_f6_signal.py``
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from bnb_quant_v2.analysis.evaluator import (
    EvalResult,
    LiveSignal,
    evaluate_from_store,
    rule_tier,
    utc_now,
)
from bnb_quant_v2.data.live.config import LiveSyncConfig, load_live_sync_config
from bnb_quant_v2.data.live.fetcher import LiveDataUnavailableError
from bnb_quant_v2.data.live.scheduler import run_live_sync
from bnb_quant_v2.notify.config import TelegramConfig, load_telegram_config
from bnb_quant_v2.notify.format import format_alert_message, format_signal_message
from bnb_quant_v2.notify.telegram import SendResult, TelegramClient
from bnb_quant_v2.runtime.dedup import SignalDedup


@dataclass
class SyncStepResult:
    """eval 前 5m 同步步骤结果。"""

    attempted: bool
    ok: bool
    detail: str


@dataclass
class NotifyStepResult:
    """Telegram 推送步骤结果。"""

    attempted: bool
    signals_sent: int
    alerts_sent: int
    dry_run: bool
    errors: list[str]


@dataclass
class PipelineResult:
    """``run_eval_pipeline`` 完整输出。"""

    sync: SyncStepResult | None
    eval: EvalResult
    notify: NotifyStepResult | None
    triggered_new: list[dict]
    triggered_skipped: list[dict]


def run_pre_eval_sync(
    cfg: LiveSyncConfig | None = None,
    *,
    dry_run: bool = False,
) -> SyncStepResult:
    """阶段 B/C7：:30 评估前强制 sync 5m。"""
    cfg = cfg or load_live_sync_config()
    if not cfg.enabled and not dry_run:
        return SyncStepResult(
            attempted=True,
            ok=False,
            detail="live_sync.enabled=false（阶段 B 未启用，跳过真实拉取）",
        )
    try:
        run_live_sync(cfg, "5m", dry_run=dry_run)
        return SyncStepResult(attempted=True, ok=True, detail="5m sync 完成")
    except LiveDataUnavailableError as e:
        return SyncStepResult(attempted=True, ok=False, detail=str(e))
    except Exception as e:
        return SyncStepResult(attempted=True, ok=False, detail=f"sync 异常: {e}")


def _notify_alert(
    client: TelegramClient,
    title: str,
    detail: str,
    *,
    as_of: pd.Timestamp | None = None,
) -> SendResult:
    text = format_alert_message(title, detail, as_of=as_of)
    return client.send(text)


def run_notify_step(
    eval_result: EvalResult,
    triggered_new: list[dict],
    *,
    tg_cfg: TelegramConfig | None = None,
    dedup: SignalDedup | None = None,
    mark_sent: bool = False,
    alert_on_error: bool = True,
) -> NotifyStepResult:
    tg_cfg = tg_cfg or load_telegram_config()
    if not tg_cfg.enabled and not tg_cfg.dry_run:
        return NotifyStepResult(
            attempted=False,
            signals_sent=0,
            alerts_sent=0,
            dry_run=True,
            errors=[],
        )

    client = TelegramClient(tg_cfg)
    errors: list[str] = []
    signals_sent = 0
    alerts_sent = 0

    if alert_on_error and tg_cfg.send_on_error:
        if eval_result.ready is False and eval_result.skip_reason:
            res = _notify_alert(
                client,
                "eval 数据不足",
                eval_result.skip_reason,
                as_of=eval_result.as_of,
            )
            if res.ok:
                alerts_sent += 1
            elif not res.dry_run:
                errors.append(res.error or "alert failed")

    if tg_cfg.send_on_signal:
        for item in triggered_new:
            sig = LiveSignal(
                hour_open_time=pd.Timestamp(item["hour_open_time"]),
                rule=item["rule"],
                direction=int(item["direction"]),
                prediction=item["prediction"],
                entry_at=pd.Timestamp(item["entry_at"]),
                entry_price=float(item["entry_price"]),
                exit_at=pd.Timestamp(item["exit_at"]),
                p1_candle_type=item["p1_candle_type"],
                f6_yang_cnt=int(item["f6_yang_cnt"]),
                f6_close_strength=float(item["f6_close_strength"]),
                f6_ret_sum=float(item["f6_ret_sum"]),
                hour_open_price=float(item.get("hour_open_price", float("nan"))),
            )
            text = format_signal_message(sig, tier=rule_tier(sig.rule))
            res = client.send(text)
            if res.ok:
                signals_sent += 1
                if mark_sent and dedup is not None:
                    dedup.mark_sent(sig.hour_open_time, sig.rule)
            elif not res.dry_run:
                errors.append(res.error or f"signal send failed: {sig.rule}")

    if mark_sent and dedup is not None:
        dedup.save()

    return NotifyStepResult(
        attempted=True,
        signals_sent=signals_sent,
        alerts_sent=alerts_sent,
        dry_run=tg_cfg.dry_run or not tg_cfg.can_send,
        errors=errors,
    )


def run_eval_pipeline(
    symbol: str = "BTCUSDT",
    *,
    as_of: datetime | pd.Timestamp | None = None,
    hour_open: datetime | pd.Timestamp | None = None,
    sync_before: bool = False,
    sync_dry_run: bool = False,
    notify: bool = False,
    mark_sent: bool = False,
    no_dedup: bool = False,
    live_sync_cfg: LiveSyncConfig | None = None,
    tg_cfg: TelegramConfig | None = None,
) -> PipelineResult:
    """端到端评估流水线。

    Args:
        symbol: 交易对，默认 BTCUSDT。
        as_of: 回放时刻；与 ``hour_open`` 均指定时用于历史回放。
        hour_open: 显式指定评估的 1H 开盘时间。
        sync_before: eval 前是否 sync 5m（需 live_sync.enabled）。
        notify: 是否调用 Telegram（信号 + 告警）。
        mark_sent: 推送成功后写入 dedup 状态。
        no_dedup: 跳过去重（测试用）。
    """
    sync_result: SyncStepResult | None = None
    if sync_before:
        sync_result = run_pre_eval_sync(live_sync_cfg, dry_run=sync_dry_run)
        if (
            notify
            and tg_cfg
            and tg_cfg.send_on_error
            and sync_result
            and not sync_result.ok
        ):
            client = TelegramClient(tg_cfg)
            _notify_alert(
                client,
                "sync 5m 失败",
                sync_result.detail,
                as_of=utc_now(),
            )

    eval_result = evaluate_from_store(symbol, as_of=as_of, hour_open=hour_open)

    triggered_new: list[dict] = []
    triggered_skipped: list[dict] = []
    dedup: SignalDedup | None = None

    if eval_result.ready and not no_dedup:
        dedup = SignalDedup()
        dedup.load()
        for sig in eval_result.signals:
            if not sig.triggered:
                continue
            item = {**sig.to_dict(), "dedup": "new"}
            if dedup.is_sent(sig.hour_open_time, sig.rule):
                item["dedup"] = "already_sent"
                triggered_skipped.append(item)
            else:
                triggered_new.append(item)
    else:
        triggered_new = [s.to_dict() for s in eval_result.signals if s.triggered]

    notify_result: NotifyStepResult | None = None
    if notify:
        notify_result = run_notify_step(
            eval_result,
            triggered_new,
            tg_cfg=tg_cfg,
            dedup=dedup,
            mark_sent=mark_sent,
        )

    return PipelineResult(
        sync=sync_result,
        eval=eval_result,
        notify=notify_result,
        triggered_new=triggered_new,
        triggered_skipped=triggered_skipped,
    )
