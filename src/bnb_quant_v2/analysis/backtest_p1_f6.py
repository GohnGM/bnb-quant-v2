"""p1×f6 策略 → 当前 1H 方向准确率回测（默认 hour_up，可选 half2_up）。

术语
----
- **p1**：上一根 1H（t-1）及其 12 根 5m 特征（``p1_*`` 列）
- **f6**：当前 1H（t）前 6 根 5m，信号在 :30 发出（``f6_*`` 列）
- **hour_up**：当前整根 1H 收阳（close > open）
- **half2_up**：当前 1H 后 30 分钟收阳（实验用）

推送规则（与实时 eval 一致）
--------------------------
- ``PRIMARY_HOUR_RULE`` — 主规则做多，约 84% / ~30 笔·月
- ``STRICT_HOUR_RULE``  — 严格规则做多，约 91.5% / 覆盖较低
- ``PRIMARY_HOUR_SHORT_RULE`` / ``STRICT_HOUR_SHORT_RULE`` — 镜像做空，约 83% / ~31 笔·月

规则定义与 ``build_p1_f6_hour_predictions`` 保持单一来源，实时 ``evaluator`` 复用同一函数。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from bnb_quant_v2.analysis.intra_5m import (
    F6_CLOSE_STRENGTH_MIN,
    F6_RANGE_HL_MIN,
    F6_RET_STRONG,
)
from bnb_quant_v2.analysis.prediction_1h import _eval_rule

TargetCol = Literal["hour_up", "half2_up"]
DEFAULT_TARGET: TargetCol = "hour_up"

# 默认采用规则：准确率与覆盖率平衡（约 84% / ~30 笔·月）
PRIMARY_HOUR_RULE = "p1大阴 & f6阳>=4 & f6收盘强>=67% → 1H涨"

# 严格规则（约 91.5% / ~2.4% 覆盖）— 实时推送与主规则并列
STRICT_HOUR_RULE = "p1大阴 & f6阳>=4 & f6涨>0.2% & f6收盘强 → 1H涨"

# 镜像做空（约 83% / ~31 笔·月；严格约 92% / ~16 笔·月）
PRIMARY_HOUR_SHORT_RULE = "p1大阳 & f6阴>=4 & f6收盘弱<=33% → 1H跌"
STRICT_HOUR_SHORT_RULE = "p1大阳 & f6阴>=4 & f6跌>0.2% & f6收盘弱 → 1H跌"

LIVE_PUSH_RULES: tuple[str, ...] = (
    PRIMARY_HOUR_RULE,
    STRICT_HOUR_RULE,
    PRIMARY_HOUR_SHORT_RULE,
    STRICT_HOUR_SHORT_RULE,
)

# 做多 + 做空四条规则并排对比（``compare_push_rules_backtest`` / ``--push-rules``）
BACKTEST_COMPARE_RULES: tuple[str, ...] = LIVE_PUSH_RULES


@dataclass
class P1F6Signal:
    """单条可交易信号（:30 入场 → 1H 收盘出场）。"""

    hour_open_time: pd.Timestamp
    rule: str
    direction: int
    prediction: str
    entry_at: pd.Timestamp
    entry_price: float
    exit_at: pd.Timestamp
    exit_price: float
    actual: str
    actual_up: bool
    correct: bool
    ret_pct: float


def _direction_label(direction: int) -> str:
    if direction == 1:
        return "涨"
    if direction == -1:
        return "跌"
    return "观望"


def _bool_up_label(up: bool) -> str:
    return "涨" if up else "跌"


def _trade_ret_pct(direction: int, entry_price: float, exit_price: float) -> float:
    if not entry_price:
        return 0.0
    raw = (exit_price - entry_price) / entry_price
    return raw if direction == 1 else -raw


def _build_signal(row: pd.Series, name: str, direction: int, target_col: TargetCol) -> P1F6Signal:
    actual_up = bool(row[target_col])
    entry_price = float(row["entry_price"])
    exit_price = float(row["exit_price"])
    if target_col == "half2_up":
        exit_at = row["signal_at"] + pd.Timedelta(minutes=5 * 6)
    else:
        exit_at = row["exit_at"] if "exit_at" in row.index else row["open_time"] + pd.Timedelta(hours=1)
    return P1F6Signal(
        hour_open_time=row["open_time"],
        rule=name,
        direction=direction,
        prediction=_direction_label(direction),
        entry_at=row["signal_at"],
        entry_price=entry_price,
        exit_at=exit_at,
        exit_price=exit_price,
        actual=_bool_up_label(actual_up),
        actual_up=actual_up,
        correct=(direction == 1 and actual_up) or (direction == -1 and not actual_up),
        ret_pct=_trade_ret_pct(direction, entry_price, exit_price),
    )


@dataclass
class P1F6BacktestReport:
    rule_name: str
    target_col: str
    baseline_up_rate: float
    total_bars: int
    signals: int
    correct: int
    wrong: int
    accuracy: float
    coverage_pct: float
    predict_up: int
    predict_down: int
    vs_baseline_pp: float
    signals_detail: list[P1F6Signal]


def _labeled(df: pd.DataFrame, target_col: TargetCol) -> pd.DataFrame:
    cols = [target_col, "entry_price", "exit_price", "signal_at"]
    if target_col == "hour_up" and "exit_at" in df.columns:
        cols.append("exit_at")
    return df.dropna(subset=cols).copy()


def build_p1_f6_hour_predictions(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """p1×f6 → 预测当前整根 1H 涨跌（+1 涨 / -1 跌 / 0 无信号）。"""
    z = pd.Series(0, index=df.index, dtype=int)
    rules: list[tuple[str, pd.Series]] = []

    # 默认主规则（f6 收盘强度 >= 67%）
    p = z.copy()
    p.loc[
        (df["p1_candle_type"] == "大阴线")
        & (df["f6_yang_cnt"] >= 4)
        & (df["f6_close_strength"] >= F6_CLOSE_STRENGTH_MIN)
    ] = 1
    rules.append((PRIMARY_HOUR_RULE, p.copy()))

    p = z.copy()
    p.loc[(df["p1_candle_type"] == "大阴线") & (df["f6_yang_cnt"] >= 4)] = 1
    rules.append(("p1大阴 & f6阳>=4 → 1H涨", p.copy()))

    p = z.copy()
    p.loc[df["f6_yang_cnt"] >= 4] = 1
    p.loc[df["f6_yang_cnt"] <= 2] = -1
    rules.append(("f6阳>=4→1H涨 / f6阳<=2→1H跌", p.copy()))

    p = z.copy()
    p.loc[df["f6_all_yang"]] = 1
    p.loc[df["f6_all_yin"]] = -1
    rules.append(("f6皆阳→1H涨 / f6皆阴→1H跌", p.copy()))

    p = z.copy()
    p.loc[df["p1_yin"] & (df["f6_yang_cnt"] >= 4)] = 1
    p.loc[df["p1_yang"] & (df["f6_yang_cnt"] <= 2)] = -1
    rules.append(("p1阴&f6阳>=4涨 / p1阳&f6阳<=2跌", p.copy()))

    p = z.copy()
    p.loc[(df["p1_candle_type"] == "大阴线") & (df["f6_ret_sum"] > 0)] = 1
    rules.append(("p1大阴 & f6前30分累计涨 → 1H涨", p.copy()))

    p = z.copy()
    p.loc[df["p1_yin"] & df["f6_last2_yang"]] = 1
    rules.append(("p1阴 & f6最后2根皆阳 → 1H涨", p.copy()))

    p = z.copy()
    p.loc[(df["p1_m5_pattern_last3"] == "阴阴阴") & ~df["f6_all_yin"]] = 1
    rules.append(("p1尾盘阴阴阴 & f6非皆阴 → 1H涨", p.copy()))

    # --- 加严规则（实验对比用）---
    p = z.copy()
    p.loc[
        (df["p1_candle_type"] == "大阴线")
        & (df["f6_yang_cnt"] >= 4)
        & (df["f6_ret_sum"] > F6_RET_STRONG)
    ] = 1
    rules.append(("p1大阴 & f6阳>=4 & f6涨>0.2% → 1H涨", p.copy()))

    p = z.copy()
    p.loc[(df["p1_candle_type"] == "大阴线") & df["f6_yang_cnt"].isin([5, 6])] = 1
    rules.append(("p1大阴 & f6阳5-6 → 1H涨", p.copy()))

    p = z.copy()
    p.loc[
        (df["p1_candle_type"] == "大阴线")
        & df["f6_yang_cnt"].isin([5, 6])
        & (df["f6_close_strength"] >= F6_CLOSE_STRENGTH_MIN)
    ] = 1
    rules.append(("p1大阴 & f6阳5-6 & f6收盘强>=67% → 1H涨", p.copy()))

    p = z.copy()
    p.loc[
        (df["p1_candle_type"] == "大阴线")
        & (df["f6_yang_cnt"] >= 4)
        & (df["f6_range_hl"] >= F6_RANGE_HL_MIN)
    ] = 1
    rules.append(("p1大阴 & f6阳>=4 & f6振幅>=0.4% → 1H涨", p.copy()))

    p = z.copy()
    p.loc[
        (df["p1_candle_type"] == "大阴线")
        & (df["f6_yang_cnt"] >= 4)
        & (df["f6_ret_sum"] > F6_RET_STRONG)
        & (df["f6_close_strength"] >= F6_CLOSE_STRENGTH_MIN)
    ] = 1
    rules.append((STRICT_HOUR_RULE, p.copy()))

    # --- 做空规则（镜像主/严格做多）---
    p = z.copy()
    p.loc[
        (df["p1_candle_type"] == "大阳线")
        & (df["f6_yin_cnt"] >= 4)
        & (df["f6_close_strength"] <= (1 - F6_CLOSE_STRENGTH_MIN))
    ] = -1
    rules.append((PRIMARY_HOUR_SHORT_RULE, p.copy()))

    p = z.copy()
    p.loc[
        (df["p1_candle_type"] == "大阳线")
        & (df["f6_yin_cnt"] >= 4)
        & (df["f6_ret_sum"] < -F6_RET_STRONG)
        & (df["f6_close_strength"] <= (1 - F6_CLOSE_STRENGTH_MIN))
    ] = -1
    rules.append((STRICT_HOUR_SHORT_RULE, p.copy()))

    return rules


def build_p1_f6_half2_predictions(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    """p1×f6 → 预测后 30 分钟涨跌（half2_up）。"""
    z = pd.Series(0, index=df.index, dtype=int)
    rules: list[tuple[str, pd.Series]] = []

    p = z.copy()
    p.loc[(df["p1_candle_type"] == "大阴线") & (df["f6_yang_cnt"] >= 4)] = 1
    rules.append(("p1大阴 & f6阳>=4 → 后半涨", p.copy()))

    p = z.copy()
    p.loc[df["f6_all_yang"]] = 1
    p.loc[df["f6_all_yin"]] = -1
    rules.append(("f6皆阳→后半涨 / f6皆阴→后半跌", p.copy()))

    p = z.copy()
    p.loc[df["p1_yin"] & (df["f6_yang_cnt"] >= 4)] = 1
    p.loc[df["p1_yang"] & (df["f6_yang_cnt"] <= 2)] = -1
    rules.append(("p1阴&f6阳>=4涨 / p1阳&f6阳<=2跌", p.copy()))

    p = z.copy()
    p.loc[(df["p1_candle_type"] == "大阴线") & (df["f6_ret_sum"] > 0)] = 1
    rules.append(("p1大阴 & f6前30分累计涨 → 后半涨", p.copy()))

    p = z.copy()
    p.loc[df["p1_yin"] & df["f6_last2_yang"]] = 1
    rules.append(("p1阴 & f6最后2根皆阳 → 后半涨", p.copy()))

    p = z.copy()
    p.loc[(df["p1_m5_pattern_last3"] == "阴阴阴") & ~df["f6_all_yin"]] = 1
    rules.append(("p1尾盘阴阴阴 & f6非皆阴 → 后半涨", p.copy()))

    return rules


def _prediction_builders(target_col: TargetCol):
    if target_col == "hour_up":
        return build_p1_f6_hour_predictions
    return build_p1_f6_half2_predictions


def run_p1_f6_backtest(
    df: pd.DataFrame,
    *,
    target_col: TargetCol = DEFAULT_TARGET,
    rule_name: str | None = None,
) -> P1F6BacktestReport | list[P1F6BacktestReport]:
    """单条或全部 p1×f6 规则的方向准确率回测。"""
    labeled = _labeled(df, target_col)
    n_bars = len(labeled)
    baseline = float(labeled[target_col].mean()) if n_bars else 0.0
    rules = _prediction_builders(target_col)(labeled)

    if rule_name:
        rules = [(n, p) for n, p in rules if n == rule_name]
        if not rules:
            raise ValueError(f"未知规则: {rule_name}")

    reports: list[P1F6BacktestReport] = []
    for name, pred in rules:
        reports.append(
            _backtest_one_rule(
                labeled, name, pred, n_bars=n_bars, baseline=baseline, target_col=target_col
            )
        )

    if rule_name:
        return reports[0]
    return reports


def _backtest_one_rule(
    labeled: pd.DataFrame,
    name: str,
    pred: pd.Series,
    *,
    n_bars: int,
    baseline: float,
    target_col: TargetCol,
) -> P1F6BacktestReport:
    rule_eval = _eval_rule(labeled, name, pred, n_bars=n_bars, target_col=target_col)
    if rule_eval is None:
        return P1F6BacktestReport(
            rule_name=name,
            target_col=target_col,
            baseline_up_rate=baseline,
            total_bars=n_bars,
            signals=0,
            correct=0,
            wrong=0,
            accuracy=0.0,
            coverage_pct=0.0,
            predict_up=0,
            predict_down=0,
            vs_baseline_pp=0.0,
            signals_detail=[],
        )

    details: list[P1F6Signal] = []
    mask = pred != 0
    for idx, row in labeled.loc[mask].iterrows():
        direction = int(pred.loc[idx])
        details.append(_build_signal(row, name, direction, target_col))

    return P1F6BacktestReport(
        rule_name=name,
        target_col=target_col,
        baseline_up_rate=baseline,
        total_bars=n_bars,
        signals=rule_eval.signals,
        correct=rule_eval.correct,
        wrong=rule_eval.wrong,
        accuracy=rule_eval.accuracy,
        coverage_pct=rule_eval.coverage_pct,
        predict_up=rule_eval.predict_up,
        predict_down=rule_eval.predict_down,
        vs_baseline_pp=(rule_eval.accuracy - baseline) * 100,
        signals_detail=details,
    )


def compare_p1_f6_backtests(
    df: pd.DataFrame,
    *,
    target_col: TargetCol = DEFAULT_TARGET,
    verbose: bool = True,
) -> list[P1F6BacktestReport]:
    reports = run_p1_f6_backtest(df, target_col=target_col)
    assert isinstance(reports, list)
    reports.sort(key=lambda r: (r.accuracy, r.vs_baseline_pp), reverse=True)
    if verbose:
        print_p1_f6_backtest_compare(reports)
    return reports


def compare_push_rules_backtest(
    df: pd.DataFrame,
    *,
    target_col: TargetCol = DEFAULT_TARGET,
    verbose: bool = True,
) -> list[P1F6BacktestReport]:
    """做多 + 做空四条推送规则并排回测（顺序固定，不排序）。"""
    reports: list[P1F6BacktestReport] = []
    for name in BACKTEST_COMPARE_RULES:
        report = run_p1_f6_backtest(df, target_col=target_col, rule_name=name)
        assert isinstance(report, P1F6BacktestReport)
        reports.append(report)
    if verbose:
        print_p1_f6_backtest_compare(reports)
    return reports


def export_p1_f6_signals_csv(report: P1F6BacktestReport, path: Path | str) -> Path:
    rows = [
        {
            "hour_open_time": s.hour_open_time,
            "entry_at": s.entry_at,
            "entry_price": s.entry_price,
            "prediction": s.prediction,
            "direction": s.direction,
            "exit_at": s.exit_at,
            "exit_price": s.exit_price,
            "actual": s.actual,
            "correct": s.correct,
            "ret_pct": s.ret_pct,
            "rule": s.rule,
        }
        for s in report.signals_detail
    ]
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def signals_to_dataframe(signals: list[P1F6Signal]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "hour_open_time": s.hour_open_time,
                "entry_at": s.entry_at,
                "entry_price": s.entry_price,
                "prediction": s.prediction,
                "direction": s.direction,
                "exit_at": s.exit_at,
                "exit_price": s.exit_price,
                "actual": s.actual,
                "correct": s.correct,
                "ret_pct": s.ret_pct,
                "rule": s.rule,
            }
            for s in signals
        ]
    )


def export_p1_f6_summary_csv(reports: list[P1F6BacktestReport], path: Path | str) -> Path:
    rows = [
        {
            "target": r.target_col,
            "rule": r.rule_name,
            "signals": r.signals,
            "correct": r.correct,
            "wrong": r.wrong,
            "accuracy": r.accuracy,
            "coverage_pct": r.coverage_pct,
            "predict_up": r.predict_up,
            "predict_down": r.predict_down,
            "vs_baseline_pp": r.vs_baseline_pp,
        }
        for r in reports
    ]
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    return out


def print_p1_f6_backtest_report(report: P1F6BacktestReport) -> None:
    target_label = "整根1H涨 (hour_up)" if report.target_col == "hour_up" else "后30分钟涨 (half2_up)"
    baseline_label = "基准1H收涨" if report.target_col == "hour_up" else "基准后半涨"
    print(f"================== 准确率: {report.rule_name} ==================")
    print(f"目标: {target_label}  |  入场: :30 f6收盘  |  出场: 1H收盘")
    print(
        f"样本池: {report.total_bars}  |  {baseline_label} {report.baseline_up_rate*100:.2f}%  |  "
        f"信号 {report.signals} ({report.coverage_pct:.1f}%)"
    )
    print(
        f"准确率: {report.accuracy*100:.2f}%  ({report.correct}/{report.signals})  |  "
        f"vs基准 {report.vs_baseline_pp:+.1f}pp  |  "
        f"多 {report.predict_up} / 空 {report.predict_down}"
    )
    if report.signals_detail:
        print("\n--- 最近 5 笔信号 ---")
        print(
            f"{'入场时间':<22} {'预测':>4} {'入场价':>10} {'出场时间':<22} {'出场价':>10} {'实际':>4} {'对':>3}"
        )
        for s in report.signals_detail[-5:]:
            print(
                f"{str(s.entry_at):<22} {s.prediction:>4} {s.entry_price:>10.2f} "
                f"{str(s.exit_at):<22} {s.exit_price:>10.2f} {s.actual:>4} {'Y' if s.correct else 'N':>3}"
            )
    print("=" * 72)


def print_p1_f6_backtest_compare(reports: list[P1F6BacktestReport]) -> None:
    if not reports:
        print("无回测结果")
        return
    target_col = reports[0].target_col
    title = "整根 1H" if target_col == "hour_up" else "后30分钟"
    baseline_label = "基准1H收涨" if target_col == "hour_up" else "基准后半涨"
    baseline = reports[0].baseline_up_rate
    print(f"================== p1×f6 → {title}方向准确率 ==================")
    print(f"{baseline_label}: {baseline*100:.2f}%  |  信号时点: :30")
    print(
        f"{'规则':<36} {'信号':>6} {'准确':>7} {'正确':>6} {'错误':>6} "
        f"{'覆盖率':>7} {'vs基准':>8} {'多':>5} {'空':>5}"
    )
    for r in reports:
        print(
            f"{r.rule_name:<36} {r.signals:>6} {r.accuracy*100:>6.1f}% "
            f"{r.correct:>6} {r.wrong:>6} {r.coverage_pct:>6.1f}% "
            f"{r.vs_baseline_pp:>+7.1f}pp {r.predict_up:>5} {r.predict_down:>5}"
        )
    print("=" * 72)


def print_p1_f6_yearly_accuracy(
    df: pd.DataFrame,
    rule_name: str,
    *,
    target_col: TargetCol = DEFAULT_TARGET,
) -> None:
    """按年打印单条规则的准确率。"""
    _print_p1_f6_period_accuracy(df, rule_name, "year", target_col=target_col)


def print_p1_f6_monthly_accuracy(
    df: pd.DataFrame,
    rule_name: str,
    *,
    target_col: TargetCol = DEFAULT_TARGET,
) -> pd.DataFrame:
    """按月打印单条规则的准确率，并返回汇总表。"""
    return _print_p1_f6_period_accuracy(df, rule_name, "month", target_col=target_col)


def _print_p1_f6_period_accuracy(
    df: pd.DataFrame,
    rule_name: str,
    period: Literal["year", "month"],
    *,
    target_col: TargetCol,
) -> pd.DataFrame:
    labeled = _labeled(df, target_col)
    rules = dict(_prediction_builders(target_col)(labeled))
    if rule_name not in rules:
        raise ValueError(f"未知规则: {rule_name}")
    pred = rules[rule_name]
    mask = pred != 0
    sub = labeled.loc[mask].copy()
    sub["pred"] = pred.loc[mask]
    sub["correct"] = sub.apply(
        lambda r: (r["pred"] == 1 and bool(r[target_col])) or (r["pred"] == -1 and not bool(r[target_col])),
        axis=1,
    )
    if period == "year":
        sub["period"] = sub["open_time"].dt.year.astype(str)
        title = "按年"
    else:
        sub["period"] = sub["open_time"].dt.to_period("M").astype(str)
        title = "按月"

    rows = []
    print(f"\n--- {title}: {rule_name} ---")
    print(f"{'期间':<10} {'信号':>5} {'准确':>7} {'收涨':>7}")
    for key, grp in sub.groupby("period", sort=True):
        acc = grp["correct"].mean()
        up = grp[target_col].mean()
        rows.append({"period": key, "signals": len(grp), "accuracy": acc, "up_rate": up})
        print(f"{key:<10} {len(grp):>5} {acc*100:>6.1f}% {up*100:>6.1f}%")

    summary = pd.DataFrame(rows)
    if len(summary):
        print(f"\n{title}均值: {summary['signals'].mean():.1f} 笔  |  准确 {summary['accuracy'].mean()*100:.1f}%")
    return summary


def export_p1_f6_monthly_csv(summary: pd.DataFrame, path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out, index=False)
    return out


def run_primary_hour_backtest(
    df: pd.DataFrame,
    *,
    verbose: bool = True,
) -> tuple[P1F6BacktestReport, pd.DataFrame]:
    """默认主规则回测 + 按年/按月统计。"""
    report = run_p1_f6_backtest(df, rule_name=PRIMARY_HOUR_RULE)
    assert isinstance(report, P1F6BacktestReport)
    if verbose:
        print_p1_f6_backtest_report(report)
        print_p1_f6_yearly_accuracy(df, PRIMARY_HOUR_RULE)
        monthly = print_p1_f6_monthly_accuracy(df, PRIMARY_HOUR_RULE)
        if len(monthly):
            print(
                f"\n月均 {monthly['signals'].mean():.1f} 笔  |  "
                f"中位 {monthly['signals'].median():.0f} 笔  |  "
                f"最少/最多 {int(monthly['signals'].min())}/{int(monthly['signals'].max())} 笔"
            )
    else:
        monthly = _monthly_summary_df(df, PRIMARY_HOUR_RULE)
    return report, monthly


def _monthly_summary_df(df: pd.DataFrame, rule_name: str) -> pd.DataFrame:
    labeled = _labeled(df, DEFAULT_TARGET)
    rules = dict(build_p1_f6_hour_predictions(labeled))
    pred = rules[rule_name]
    mask = pred != 0
    sub = labeled.loc[mask].copy()
    sub["pred"] = pred.loc[mask]
    sub["correct"] = sub.apply(
        lambda r: (r["pred"] == 1 and bool(r["hour_up"])) or (r["pred"] == -1 and not bool(r["hour_up"])),
        axis=1,
    )
    sub["period"] = sub["open_time"].dt.to_period("M").astype(str)
    return (
        sub.groupby("period", sort=True)
        .agg(signals=("hour_up", "count"), accuracy=("correct", "mean"), up_rate=("hour_up", "mean"))
        .reset_index()
    )


# --- half2 兼容别名 ---
Half2Signal = P1F6Signal
Half2BacktestReport = P1F6BacktestReport
run_p1_f6_half2_backtest = lambda df, **kw: run_p1_f6_backtest(df, target_col="half2_up", **kw)
compare_p1_f6_half2_backtests = lambda df, **kw: compare_p1_f6_backtests(df, target_col="half2_up", **kw)
export_half2_signals_csv = export_p1_f6_signals_csv
export_half2_summary_csv = export_p1_f6_summary_csv
print_half2_backtest_report = print_p1_f6_backtest_report
print_half2_backtest_compare = print_p1_f6_backtest_compare
export_half2_trades_csv = export_p1_f6_signals_csv
