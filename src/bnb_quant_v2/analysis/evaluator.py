"""实时 :30 信号评估（与回测共用规则注册表）。

评估时刻
--------
默认在每小时 **:30 UTC**（第 6 根 5m 收盘后），对**当前整点小时**判定主/严格做多与做空规则。

数据要求
--------
- 当前小时已有 **≥6 根 5m**（f6）
- 上一小时有完整 **12 根 5m**（p1）

不足时 ``EvalResult.ready=False``，``runtime`` 流水线会发 Telegram 告警。

与回测一致性
------------
``validate_against_enriched`` 确保完整小时的 live 行与 ``enrich_p1_f6`` 回测行预测一致。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from bnb_quant_v2.analysis.backtest_p1_f6 import (
    LIVE_PUSH_RULES,
    PRIMARY_HOUR_RULE,
    PRIMARY_HOUR_SHORT_RULE,
    STRICT_HOUR_RULE,
    STRICT_HOUR_SHORT_RULE,
)
from bnb_quant_v2.analysis.intra_5m import (
    EXPECTED_M5_PER_HOUR,
    F6_BARS,
    P1_SHIFT_COLS,
    compute_first6_features,
    compute_intra_features,
    enrich_p1_f6,
)
from bnb_quant_v2.analysis.prediction_1h import enrich_bar_features
from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.strategy.p1f6_rules import rule_registry


@dataclass
class LiveSignal:
    """:30 实时信号（尚未知道 actual / correct）。"""

    hour_open_time: pd.Timestamp
    rule: str
    direction: int
    prediction: str
    entry_at: pd.Timestamp
    entry_price: float
    exit_at: pd.Timestamp
    p1_candle_type: str
    f6_yang_cnt: int
    f6_close_strength: float
    f6_ret_sum: float
    hour_open_price: float = float("nan")

    @property
    def triggered(self) -> bool:
        return self.direction != 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key, val in d.items():
            if isinstance(val, pd.Timestamp):
                d[key] = val.isoformat()
        d["triggered"] = self.triggered
        return d


@dataclass
class EvalResult:
    as_of: pd.Timestamp
    hour_open_time: pd.Timestamp
    ready: bool
    skip_reason: str | None
    signals: list[LiveSignal]

    @property
    def any_triggered(self) -> bool:
        return any(s.triggered for s in self.signals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat(),
            "hour_open_time": self.hour_open_time.isoformat(),
            "ready": self.ready,
            "skip_reason": self.skip_reason,
            "any_triggered": self.any_triggered,
            "signals": [s.to_dict() for s in self.signals],
        }


def _direction_label(direction: int) -> str:
    if direction == 1:
        return "涨"
    if direction == -1:
        return "跌"
    return "观望"


def _as_utc(ts: datetime | pd.Timestamp) -> pd.Timestamp:
    out = pd.Timestamp(ts)
    if out.tzinfo is None:
        return out.tz_localize("UTC")
    return out.tz_convert("UTC")


def utc_now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


def resolve_eval_hour(as_of: datetime | pd.Timestamp | None = None) -> pd.Timestamp:
    """:30 评估对应当前整点小时（open_time）。

    例如 as_of=10:30 → 返回 10:00 UTC 的 Timestamp。
    """
    now = _as_utc(as_of if as_of is not None else utc_now())
    return now.floor("h")


def _m5_in_hour(df_5m: pd.DataFrame, hour_open: pd.Timestamp) -> pd.DataFrame:
    bucket = _as_utc(hour_open).floor("h")
    m5 = df_5m.sort_values("open_time").reset_index(drop=True).copy()
    m5["open_time"] = pd.to_datetime(m5["open_time"], utc=True)
    return m5.loc[m5["open_time"].dt.floor("h") == bucket].reset_index(drop=True)


def _hour_bar_features(
    df_1h: pd.DataFrame,
    df_5m: pd.DataFrame,
    hour_open: pd.Timestamp,
    *,
    min_m5: int = EXPECTED_M5_PER_HOUR,
) -> pd.Series | None:
    """单小时 1H + 5m 合并特征（供 p1 使用）。"""
    hour_open = _as_utc(hour_open).floor("h")
    h1 = df_1h.sort_values("open_time").reset_index(drop=True).copy()
    h1["open_time"] = pd.to_datetime(h1["open_time"], utc=True)
    row = h1.loc[h1["open_time"] == hour_open]
    if row.empty:
        return None
    m5_g = _m5_in_hour(df_5m, hour_open)
    if len(m5_g) < min_m5:
        return None
    bar = enrich_bar_features(row).iloc[0]
    intra = compute_intra_features(m5_g)
    merged = bar.copy()
    for key, val in intra.items():
        merged[key] = val
    return merged


def build_live_p1_f6_row(
    df_1h: pd.DataFrame,
    df_5m: pd.DataFrame,
    hour_open: pd.Timestamp,
) -> pd.Series | None:
    """:30 评估行：当前小时 ≥6 根 5m + 前一小时完整 12 根 5m（p1）。"""
    hour_open = _as_utc(hour_open).floor("h")
    m5_cur = _m5_in_hour(df_5m, hour_open)
    if len(m5_cur) < F6_BARS:
        return None

    prev_open = hour_open - pd.Timedelta(hours=1)
    prev_feat = _hour_bar_features(df_1h, df_5m, prev_open, min_m5=EXPECTED_M5_PER_HOUR)
    if prev_feat is None:
        return None

    f6 = compute_first6_features(m5_cur)
    row: dict[str, Any] = {"open_time": hour_open}
    for col in P1_SHIFT_COLS:
        if col in prev_feat.index:
            row[f"p1_{col}"] = prev_feat[col]

    for col in f6.index:
        row[col] = f6[col]

    prev_close = float(prev_feat["close"])
    curr_open = float(m5_cur["open"].iloc[0])
    row["open"] = curr_open
    row["gap_hour"] = (curr_open - prev_close) / prev_close if prev_close else float("nan")
    row["signal_at"] = hour_open + pd.Timedelta(minutes=5 * F6_BARS)
    row["entry_price"] = float(f6["f6_close"])
    row["exit_at"] = hour_open + pd.Timedelta(hours=1)
    return pd.Series(row)


def _predictions_for_row(row: pd.Series) -> dict[str, int]:
    df = pd.DataFrame([row])
    preds = rule_registry.evaluate_all(df)
    return {name: int(preds[name].iloc[0]) for name in LIVE_PUSH_RULES if name in preds}


def _live_signal_from_row(row: pd.Series, rule: str, direction: int) -> LiveSignal:
    return LiveSignal(
        hour_open_time=_as_utc(row["open_time"]),
        rule=rule,
        direction=direction,
        prediction=_direction_label(direction),
        entry_at=_as_utc(row["signal_at"]),
        entry_price=float(row["entry_price"]),
        exit_at=_as_utc(row["exit_at"]),
        p1_candle_type=str(row.get("p1_candle_type", "")),
        f6_yang_cnt=int(row.get("f6_yang_cnt", 0)),
        f6_close_strength=float(row.get("f6_close_strength", float("nan"))),
        f6_ret_sum=float(row.get("f6_ret_sum", float("nan"))),
        hour_open_price=float(row.get("open", float("nan"))),
    )


def evaluate_live_at(
    df_1h: pd.DataFrame,
    df_5m: pd.DataFrame,
    *,
    as_of: datetime | pd.Timestamp | None = None,
    hour_open: datetime | pd.Timestamp | None = None,
) -> EvalResult:
    """评估指定时刻对应小时的 p1×f6 四条推送规则（做多主/严格 + 做空主/严格）。"""
    as_of_ts = _as_utc(as_of if as_of is not None else utc_now())
    hour = _as_utc(hour_open).floor("h") if hour_open is not None else resolve_eval_hour(as_of_ts)

    row = build_live_p1_f6_row(df_1h, df_5m, hour)
    if row is None:
        m5_n = len(_m5_in_hour(df_5m, hour))
        return EvalResult(
            as_of=as_of_ts,
            hour_open_time=hour,
            ready=False,
            skip_reason=f"数据不足：hour={hour.isoformat()} 当前小时 5m={m5_n}/{F6_BARS}",
            signals=[],
        )

    preds = _predictions_for_row(row)
    signals = [_live_signal_from_row(row, rule, preds[rule]) for rule in LIVE_PUSH_RULES]
    return EvalResult(
        as_of=as_of_ts,
        hour_open_time=hour,
        ready=True,
        skip_reason=None,
        signals=signals,
    )


def evaluate_from_store(
    symbol: str = "BTCUSDT",
    *,
    store: KlineStore | None = None,
    as_of: datetime | pd.Timestamp | None = None,
    hour_open: datetime | pd.Timestamp | None = None,
) -> EvalResult:
    """从 ``KlineStore`` 加载 1h/5m 并评估。实时流水线主入口。"""
    store = store or KlineStore()
    df_1h = store.load(symbol, "1h")
    df_5m = store.load(symbol, "5m")
    return evaluate_live_at(df_1h, df_5m, as_of=as_of, hour_open=hour_open)


def validate_against_enriched(
    df_1h: pd.DataFrame,
    df_5m: pd.DataFrame,
    hour_open: pd.Timestamp,
) -> bool:
    """完整小时：live 行与 enrich_p1_f6 回测行在推送规则上应一致。"""
    hour_open = _as_utc(hour_open).floor("h")
    enriched = enrich_p1_f6(df_1h, df_5m, complete_only=True)
    enriched["open_time"] = pd.to_datetime(enriched["open_time"], utc=True)
    hist = enriched.loc[enriched["open_time"] == hour_open]
    if hist.empty:
        return False
    live = build_live_p1_f6_row(df_1h, df_5m, hour_open)
    if live is None:
        return False
    live_preds = _predictions_for_row(live)
    hist_preds = _predictions_for_row(hist.iloc[0])
    return live_preds == hist_preds


def rule_tier(rule: str) -> str:
    """将规则名映射为推送层级。

    返回 ``primary`` | ``strict`` | ``primary_short`` | ``strict_short`` | ``other``。
    """
    if rule == PRIMARY_HOUR_RULE:
        return "primary"
    if rule == STRICT_HOUR_RULE:
        return "strict"
    if rule == PRIMARY_HOUR_SHORT_RULE:
        return "primary_short"
    if rule == STRICT_HOUR_SHORT_RULE:
        return "strict_short"
    return "other"
