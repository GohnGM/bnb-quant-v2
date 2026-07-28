"""信号子命令：评估、推送。"""
from __future__ import annotations

import typer
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table

from bnb_quant_v2.analysis.evaluator import evaluate_from_store, evaluate_live_at

console = Console()
app = typer.Typer(name="signal", help="信号（评估、推送）")


@app.command()
def eval(
    telegram: bool = typer.Option(False, help="发送 Telegram 通知"),
    dry_run: bool = typer.Option(False, help="模拟推送"),
    mark_sent: bool = typer.Option(False, help="标记已发送"),
    hour_open: str = typer.Option(None, help="历史回放时间"),
):
    """评估 p1×f6 信号"""
    console.print("\n🎯 [bold cyan]评估 p1×f6 信号[/bold cyan]")

    if hour_open:
        # 历史回放模式
        ts = datetime.fromisoformat(hour_open.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)

        console.print(f"   历史回放: {ts}")
        result = evaluate_live_at(ts)
    else:
        # 实时评估模式
        console.print("   实时评估...")
        result = evaluate_from_store()

    if not result.ready:
        console.print("❌ [bold red]数据不足，无法评估[/bold red]")
        console.print(f"   原因: {result.message}")
        return

    console.print(f"\n📊 评估时间: {result.signal_at}")
    console.print(f"   小时: {result.hour_open_time}")

    # 显示信号结果
    table = Table(title="信号评估结果")
    table.add_column("规则", style="cyan")
    table.add_column("预测", style="magenta")
    table.add_column("方向", style="green")

    for signal in result.signals:
        direction_emoji = "📈" if signal.direction == 1 else "📉" if signal.direction == -1 else "➡️"
        table.add_row(
            signal.rule,
            signal.prediction,
            f"{direction_emoji} {signal.direction}",
        )

    console.print(table)

    # 显示特征详情
    if result.live_row is not None:
        row = result.live_row
        console.print("\n🔍 特征详情:")
        console.print(f"   p1 蜡烛类型: {row.get('p1_candle_type', '')}")
        console.print(f"   p1 阳线: {row.get('p1_yang', False)}")
        console.print(f"   p1 阴线: {row.get('p1_yin', False)}")
        console.print(f"   f6 阳线数: {row.get('f6_yang_cnt', 0)}/6")
        console.print(f"   f6 收盘强度: {row.get('f6_close_strength', 0):.2f}")
        console.print(f"   f6 累计涨幅: {row.get('f6_ret_sum', 0):.2%}")

    # 发送通知
    if telegram:
        console.print("\n📢 [bold yellow]发送 Telegram 通知[/bold yellow]")

        from bnb_quant_v2.runtime.pipeline import run_notify_step

        notify_result = run_notify_step(result, dry_run=dry_run, mark_sent=mark_sent)
        if notify_result.ok:
            console.print("✅ [bold green]通知发送成功[/bold green]")
        else:
            console.print(f"❌ [bold red]通知发送失败[/bold red]: {notify_result.error}")


@app.command()
def history(
    hours: int = typer.Option(24, help="回溯小时数"),
):
    """查看历史信号"""
    console.print(f"\n📜 [bold cyan]查看最近 {hours} 小时信号[/bold cyan]")

    from bnb_quant_v2.paths import ANALYSIS_DIR

    signals_file = ANALYSIS_DIR / "p1_f6_hour_signals.csv"

    if not signals_file.exists():
        console.print("❌ [bold red]信号文件不存在[/bold red]")
        console.print("   请先运行回测: bnbquant backtest run")
        return

    import pandas as pd

    df = pd.read_csv(signals_file)
    df["open_time"] = pd.to_datetime(df["open_time"])

    # 取最近 hours 小时
    recent = df.sort_values("open_time").tail(hours)

    table = Table(title="最近信号")
    table.add_column("时间", style="cyan")
    table.add_column("规则", style="magenta")
    table.add_column("预测", style="green")
    table.add_column("实际", style="yellow")
    table.add_column("正确", style="blue")

    for _, row in recent.iterrows():
        if row["direction"] == 1:
            prediction = "📈 涨"
        elif row["direction"] == -1:
            prediction = "📉 跌"
        else:
            prediction = "➡️ 观望"

        actual = "📈 涨" if row["actual_up"] else "📉 跌"
        correct = "✅" if row["correct"] else "❌"

        table.add_row(
            str(row["open_time"]),
            row["rule"],
            prediction,
            actual,
            correct,
        )

    console.print(table)
