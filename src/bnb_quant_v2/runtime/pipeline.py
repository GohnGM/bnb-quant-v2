"""实时评估流水线：sync → eval → dedup → Telegram。

管道模式（Pipeline Pattern）
--------------------------
- ``Pipeline`` 类管理步骤列表
- 每个步骤实现 ``PipelineStep`` 协议
- ``PipelineContext`` 在步骤间传递状态
- 易于扩展中间步骤（如风控、仓位管理）

``run_eval_pipeline`` 保持向后兼容，是 launchd :30 任务的核心编排函数。

步骤
----
1. （可选）``SyncStep`` — eval 前拉取最新 5m
2. ``EvalStep`` — 模块二判定主/严格规则
3. ``DedupStep`` — 过滤已推送的 (hour, rule)
4. （可选）``NotifyStep`` — 发信号 / 数据不足告警

CLI 入口：``scripts/runtime/eval_p1_f6_signal.py``
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, runtime_checkable

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
from bnb_quant_v2.notify.config import TelegramConfig, load_telegram_config, load_email_config
from bnb_quant_v2.notify.email import EmailClient, EmailConfig
from bnb_quant_v2.notify.format import format_alert_message, format_signal_message
from bnb_quant_v2.notify.telegram import SendResult, TelegramClient
from bnb_quant_v2.runtime.dedup import SignalDedup


if TYPE_CHECKING:
    from bnb_quant_v2.strategy.base import Strategy


@dataclass
class SyncStepResult:
    attempted: bool
    ok: bool
    detail: str


@dataclass
class NotifyStepResult:
    attempted: bool
    signals_sent: int
    alerts_sent: int
    dry_run: bool
    errors: list[str]


@dataclass
class PipelineResult:
    sync: SyncStepResult | None
    eval: EvalResult
    notify: NotifyStepResult | None
    triggered_new: list[dict]
    triggered_skipped: list[dict]


@dataclass
class PipelineContext:
    symbol: str = "BTCUSDT"
    as_of: pd.Timestamp | None = None
    hour_open: pd.Timestamp | None = None
    sync_result: SyncStepResult | None = None
    eval_result: EvalResult | None = None
    triggered_new: list[dict] = field(default_factory=list)
    triggered_skipped: list[dict] = field(default_factory=list)
    notify_result: NotifyStepResult | None = None
    dedup: SignalDedup | None = None
    strategy: Strategy | None = None
    extras: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PipelineStep(Protocol):
    """流水线步骤协议。"""

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        ...


class SyncStep:
    """同步步骤：eval 前拉取最新 5m。"""

    def __init__(self, cfg: LiveSyncConfig | None = None, dry_run: bool = False):
        self.cfg = cfg or load_live_sync_config()
        self.dry_run = dry_run

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not self.cfg.enabled and not self.dry_run:
            ctx.sync_result = SyncStepResult(
                attempted=True,
                ok=False,
                detail="live_sync.enabled=false（阶段 B 未启用，跳过真实拉取）",
            )
            return ctx
        try:
            run_live_sync(self.cfg, "5m", dry_run=self.dry_run)
            ctx.sync_result = SyncStepResult(attempted=True, ok=True, detail="5m sync 完成")
        except LiveDataUnavailableError as e:
            ctx.sync_result = SyncStepResult(attempted=True, ok=False, detail=str(e))
        except Exception as e:
            ctx.sync_result = SyncStepResult(attempted=True, ok=False, detail=f"sync 异常: {e}")
        return ctx


class EvalStep:
    """评估步骤：判定主/严格规则。"""

    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        ctx.eval_result = evaluate_from_store(
            self.symbol,
            as_of=ctx.as_of,
            hour_open=ctx.hour_open,
        )
        return ctx


class DedupStep:
    """去重步骤：过滤已推送的 (hour, rule)。"""

    def __init__(self, mark_sent: bool = False):
        self.mark_sent = mark_sent

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.eval_result is None or not ctx.eval_result.ready:
            if ctx.eval_result:
                ctx.triggered_new = [s.to_dict() for s in ctx.eval_result.signals if s.triggered]
            return ctx

        ctx.dedup = SignalDedup()
        ctx.dedup.load()

        for sig in ctx.eval_result.signals:
            if not sig.triggered:
                continue
            item = {**sig.to_dict(), "dedup": "new"}
            if ctx.dedup.is_sent(sig.hour_open_time, sig.rule):
                item["dedup"] = "already_sent"
                ctx.triggered_skipped.append(item)
            else:
                ctx.triggered_new.append(item)
        return ctx


class NotifyStep:
    """通知步骤：支持 Telegram 和 Email 双通道。"""

    def __init__(
        self,
        tg_cfg: TelegramConfig | None = None,
        email_cfg: EmailConfig | None = None,
        alert_on_error: bool = True,
        mark_sent: bool = False,
    ):
        self.tg_cfg = tg_cfg or load_telegram_config()
        self.email_cfg = email_cfg or load_email_config()
        self.alert_on_error = alert_on_error
        self.mark_sent = mark_sent

        self.tg_client = TelegramClient(self.tg_cfg) if self.tg_cfg.can_send or self.tg_cfg.dry_run else None
        self.email_client = EmailClient(self.email_cfg) if self.email_cfg.can_send or self.email_cfg.dry_run else None

    def execute(self, ctx: PipelineContext) -> PipelineContext:
        errors: list[str] = []
        signals_sent = 0
        alerts_sent = 0

        # 检查是否有可用的通知渠道
        has_any_channel = self.tg_client is not None or self.email_client is not None
        if not has_any_channel:
            ctx.notify_result = NotifyStepResult(
                attempted=False,
                signals_sent=0,
                alerts_sent=0,
                dry_run=True,
                errors=[],
            )
            return ctx

        if self.alert_on_error:
            alerts_sent += self._send_alerts(ctx, errors)

        signals_sent += self._send_signals(ctx, errors)

        if self.mark_sent and ctx.dedup is not None:
            ctx.dedup.save()

        is_dry_run = (
            (self.tg_client is not None and self.tg_cfg.dry_run) or
            (self.email_client is not None and self.email_cfg.dry_run)
        )
        ctx.notify_result = NotifyStepResult(
            attempted=True,
            signals_sent=signals_sent,
            alerts_sent=alerts_sent,
            dry_run=is_dry_run,
            errors=errors,
        )
        return ctx

    def _send_alerts(self, ctx: PipelineContext, errors: list[str]) -> int:
        """发送告警消息。"""
        count = 0
        should_send = self.tg_cfg.send_on_error or self.email_cfg.send_on_error

        if not should_send:
            return 0

        # sync 失败告警
        if ctx.sync_result and not ctx.sync_result.ok:
            title = "sync 5m 失败"
            detail = ctx.sync_result.detail
            if self._send_multi_channel(title, detail, errors, channel="alert"):
                count += 1

        # eval 数据不足告警
        if ctx.eval_result and ctx.eval_result.ready is False and ctx.eval_result.skip_reason:
            title = "eval 数据不足"
            detail = ctx.eval_result.skip_reason
            if self._send_multi_channel(title, detail, errors, channel="alert", as_of=ctx.eval_result.as_of):
                count += 1

        return count

    def _send_signals(self, ctx: PipelineContext, errors: list[str]) -> int:
        """发送信号消息。"""
        count = 0
        if not self.tg_cfg.send_on_signal and not self.email_cfg.send_on_signal:
            return 0

        for item in ctx.triggered_new:
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
            title = f"BTCUSDT p1×f6 · {rule_tier(sig.rule)} · {sig.prediction}"

            if self._send_multi_channel(title, text, errors, channel="signal"):
                count += 1
                if self.mark_sent and ctx.dedup is not None:
                    ctx.dedup.mark_sent(sig.hour_open_time, sig.rule)

        return count

    def _send_multi_channel(
        self,
        title: str,
        text: str,
        errors: list[str],
        *,
        channel: str = "signal",
        as_of: pd.Timestamp | None = None,
    ) -> bool:
        """通过所有可用渠道发送消息。"""
        sent_any = False

        # Telegram
        if self.tg_client and (channel == "signal" and self.tg_cfg.send_on_signal or
                               channel == "alert" and self.tg_cfg.send_on_error):
            text_to_send = text
            if channel == "alert":
                text_to_send = format_alert_message(title, text, as_of=as_of)
            res = self.tg_client.send(text_to_send)
            if res.ok:
                sent_any = True
            elif not res.dry_run:
                errors.append(f"Telegram {channel} 发送失败: {res.error}")

        # Email
        if self.email_client and (channel == "signal" and self.email_cfg.send_on_signal or
                                  channel == "alert" and self.email_cfg.send_on_error):
            res = self.email_client.send(title, text)
            if res.ok:
                sent_any = True
            elif not res.dry_run:
                errors.append(f"Email {channel} 发送失败: {res.error}")

        return sent_any


class Pipeline:
    """流水线：管理步骤列表并执行。"""

    def __init__(self, steps: List[PipelineStep]):
        self.steps = steps

    def run(self, ctx: PipelineContext) -> PipelineContext:
        for step in self.steps:
            ctx = step.execute(ctx)
        return ctx


def build_eval_pipeline(
    *,
    sync_before: bool = False,
    sync_dry_run: bool = False,
    notify: bool = False,
    mark_sent: bool = False,
    live_sync_cfg: LiveSyncConfig | None = None,
    tg_cfg: TelegramConfig | None = None,
    email_cfg: EmailConfig | None = None,
) -> Pipeline:
    """构建评估流水线。"""
    steps: List[PipelineStep] = []

    if sync_before:
        steps.append(SyncStep(cfg=live_sync_cfg, dry_run=sync_dry_run))

    steps.append(EvalStep())
    steps.append(DedupStep(mark_sent=False))

    if notify:
        steps.append(NotifyStep(tg_cfg=tg_cfg, email_cfg=email_cfg, mark_sent=mark_sent))

    return Pipeline(steps)


def run_pre_eval_sync(
    cfg: LiveSyncConfig | None = None,
    *,
    dry_run: bool = False,
) -> SyncStepResult:
    """阶段 B/C7：:30 评估前强制 sync 5m（向后兼容）。"""
    step = SyncStep(cfg=cfg, dry_run=dry_run)
    ctx = step.execute(PipelineContext())
    return ctx.sync_result


def run_notify_step(
    eval_result: EvalResult,
    triggered_new: list[dict],
    *,
    tg_cfg: TelegramConfig | None = None,
    email_cfg: EmailConfig | None = None,
    dedup: SignalDedup | None = None,
    mark_sent: bool = False,
    alert_on_error: bool = True,
) -> NotifyStepResult:
    """通知推送步骤（支持 Telegram + Email）。"""
    step = NotifyStep(tg_cfg=tg_cfg, email_cfg=email_cfg, alert_on_error=alert_on_error, mark_sent=mark_sent)
    ctx = PipelineContext(
        eval_result=eval_result,
        triggered_new=triggered_new,
        dedup=dedup,
    )
    ctx = step.execute(ctx)
    return ctx.notify_result


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
    email_cfg: EmailConfig | None = None,
) -> PipelineResult:
    """端到端评估流水线（支持 Telegram + Email）。

    Args:
        symbol: 交易对，默认 BTCUSDT。
        as_of: 回放时刻；与 ``hour_open`` 均指定时用于历史回放。
        hour_open: 显式指定评估的 1H 开盘时间。
        sync_before: eval 前是否 sync 5m（需 live_sync.enabled）。
        notify: 是否调用通知渠道（信号 + 告警）。
        mark_sent: 推送成功后写入 dedup 状态。
        no_dedup: 跳过去重（测试用）。
    """
    ctx = PipelineContext(
        symbol=symbol,
        as_of=pd.Timestamp(as_of) if as_of else None,
        hour_open=pd.Timestamp(hour_open) if hour_open else None,
    )

    if sync_before:
        sync_step = SyncStep(cfg=live_sync_cfg, dry_run=sync_dry_run)
        ctx = sync_step.execute(ctx)

        if notify and ctx.sync_result and not ctx.sync_result.ok:
            error_detail = ctx.sync_result.detail
            if tg_cfg and tg_cfg.send_on_error and tg_cfg.can_send:
                client = TelegramClient(tg_cfg)
                text = format_alert_message("sync 5m 失败", error_detail, as_of=utc_now())
                client.send(text)
            if email_cfg and email_cfg.send_on_error and email_cfg.can_send:
                client = EmailClient(email_cfg)
                client.send("sync 5m 失败", error_detail)

    eval_step = EvalStep(symbol=symbol)
    ctx = eval_step.execute(ctx)

    if not no_dedup:
        dedup_step = DedupStep(mark_sent=False)
        ctx = dedup_step.execute(ctx)
    else:
        if ctx.eval_result:
            ctx.triggered_new = [s.to_dict() for s in ctx.eval_result.signals if s.triggered]

    if notify:
        notify_step = NotifyStep(tg_cfg=tg_cfg, email_cfg=email_cfg, mark_sent=mark_sent)
        ctx = notify_step.execute(ctx)

    return PipelineResult(
        sync=ctx.sync_result,
        eval=ctx.eval_result,
        notify=ctx.notify_result,
        triggered_new=ctx.triggered_new,
        triggered_skipped=ctx.triggered_skipped,
    )