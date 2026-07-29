#!/usr/bin/env python3
"""紫御BTC量化分析系统 - 统一命令行界面。

使用方式：
    bnbquant --help
    bnbquant data import --dir ~/Downloads/gate1hData
    bnbquant backtest run --rebuild
    bnbquant signal eval
    bnbquant status
"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from bnb_quant_v2.cli.data import app as data_app
from bnb_quant_v2.cli.backtest import app as backtest_app
from bnb_quant_v2.cli.signal import app as signal_app
from bnb_quant_v2.cli.notify import app as notify_app
from bnb_quant_v2.cli.system import app as system_app
from bnb_quant_v2.strategy.base import rule_registry, strategy_registry
from bnb_quant_v2.paths import DATA_DIR, KLINE_DIR, ANALYSIS_DIR

console = Console()
app = typer.Typer(
    name="bnbquant",
    help="紫御BTC量化分析系统",
    rich_markup_mode="rich",
)

app.add_typer(data_app, name="data", help="数据管理（导入、同步、验证）")
app.add_typer(backtest_app, name="backtest", help="回测（构建特征、运行回测）")
app.add_typer(signal_app, name="signal", help="信号（评估、推送）")
app.add_typer(notify_app, name="notify", help="通知（Telegram、心跳）")
app.add_typer(system_app, name="system", help="系统（健康检查、定时任务）")


@app.command()
def status():
    """查看系统状态"""
    console.print("\n📊 [bold cyan]紫御BTC量化分析系统 · 系统状态[/bold cyan]\n")

    # 数据状态
    table_data = Table(title="数据状态")
    table_data.add_column("类型", style="cyan")
    table_data.add_column("路径", style="magenta")
    table_data.add_column("状态", style="green")

    klines_1h = KLINE_DIR / "BTCUSDT_1h.parquet"
    klines_5m = KLINE_DIR / "BTCUSDT_5m.parquet"
    features = ANALYSIS_DIR / "BTCUSDT_1h_p1_f6_features.parquet"

    table_data.add_row("1H K线", str(klines_1h), "✅ 存在" if klines_1h.exists() else "❌ 缺失")
    table_data.add_row("5m K线", str(klines_5m), "✅ 存在" if klines_5m.exists() else "❌ 缺失")
    table_data.add_row("特征表", str(features), "✅ 存在" if features.exists() else "❌ 缺失")

    console.print(table_data)

    # 策略状态
    table_strategy = Table(title="策略状态")
    table_strategy.add_column("类型", style="cyan")
    table_strategy.add_column("数量", style="magenta")

    table_strategy.add_row("规则", str(len(rule_registry.names())))
    table_strategy.add_row("策略", str(len(strategy_registry.names())))

    console.print(table_strategy)

    # 运行状态
    table_runtime = Table(title="运行状态")
    table_runtime.add_column("类型", style="cyan")
    table_runtime.add_column("路径", style="magenta")
    table_runtime.add_column("状态", style="green")

    latest_signal = DATA_DIR / "live" / "latest_signal.json"
    signal_state = DATA_DIR / "live" / "signal_state.json"
    run_stats = DATA_DIR / "live" / "run_stats.json"

    table_runtime.add_row("最新信号", str(latest_signal), "✅ 存在" if latest_signal.exists() else "❌ 缺失")
    table_runtime.add_row("去重状态", str(signal_state), "✅ 存在" if signal_state.exists() else "❌ 缺失")
    table_runtime.add_row("运行统计", str(run_stats), "✅ 存在" if run_stats.exists() else "❌ 缺失")

    console.print(table_runtime)

    console.print("\n💡 [bold green]快速操作[/bold green]:")
    console.print("   bnbquant data import --dir ~/Downloads/gate1hData")
    console.print("   bnbquant backtest run --rebuild")
    console.print("   bnbquant signal eval")
    console.print("   bnbquant system health")


@app.command()
def version():
    """查看版本"""
    console.print("📦 紫御BTC量化分析系统 v0.1.0")


@app.command()
def web(
    port: int = typer.Option(8501, help="Web UI 端口"),
    host: str = typer.Option("localhost", help="Web UI 主机地址"),
    headless: bool = typer.Option(False, "--headless", "-h", help="无头模式运行"),
):
    """启动 Web UI 界面"""
    import subprocess
    import sys
    
    from bnb_quant_v2.paths import PROJECT_ROOT
    
    app_path = PROJECT_ROOT / "src" / "bnb_quant_v2" / "webui" / "app.py"
    
    if not app_path.exists():
        console.print("❌ [bold red]Web UI 文件不存在[/bold red]")
        return
    
    console.print(f"\n🌐 [bold cyan]启动 Web UI...[/bold cyan]")
    console.print(f"   地址: http://{host}:{port}")
    console.print(f"   文件: {app_path}")
    console.print(f"\n💡 在浏览器中打开上述地址访问\n")
    
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(app_path),
        "--server.port", str(port),
        "--server.address", host,
    ]
    
    if headless:
        cmd.extend(["--server.headless", "true"])
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        console.print("\n🛑 [bold yellow]Web UI 已停止[/bold yellow]")
    except Exception as e:
        console.print(f"❌ [bold red]启动失败: {e}[/bold red]")


if __name__ == "__main__":
    app()
