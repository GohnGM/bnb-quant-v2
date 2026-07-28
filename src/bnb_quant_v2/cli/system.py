"""系统子命令：健康检查、定时任务。"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(name="system", help="系统（健康检查、定时任务）")


@app.command()
def health():
    """运行健康检查"""
    console.print("\n🏥 [bold cyan]健康检查[/bold cyan]")

    from bnb_quant_v2.paths import DATA_DIR, KLINE_DIR, ANALYSIS_DIR

    # 目录检查
    table_dir = Table(title="目录检查")
    table_dir.add_column("目录", style="cyan")
    table_dir.add_column("状态", style="green")

    dirs = [
        ("数据目录", DATA_DIR),
        ("K线目录", KLINE_DIR),
        ("分析目录", ANALYSIS_DIR),
    ]

    for name, path in dirs:
        exists = path.exists()
        table_dir.add_row(str(path), "✅ 存在" if exists else "❌ 缺失")

    console.print(table_dir)

    # 数据文件检查
    table_data = Table(title="数据文件")
    table_data.add_column("文件", style="cyan")
    table_data.add_column("状态", style="green")

    files = [
        ("1H K线", KLINE_DIR / "BTCUSDT_1h.parquet"),
        ("5m K线", KLINE_DIR / "BTCUSDT_5m.parquet"),
        ("特征表", ANALYSIS_DIR / "BTCUSDT_1h_p1_f6_features.parquet"),
    ]

    for name, path in files:
        exists = path.exists()
        size = ""
        if exists:
            size_mb = path.stat().st_size / (1024 * 1024)
            size = f" ({size_mb:.1f} MB)"
        table_data.add_row(name + size, "✅ 存在" if exists else "❌ 缺失")

    console.print(table_data)

    # 运行统计
    stats_file = DATA_DIR / "live" / "run_stats.json"
    if stats_file.exists():
        console.print(f"\n📊 运行统计:")
        console.print(f"   文件: {stats_file}")
        size_kb = stats_file.stat().st_size / 1024
        console.print(f"   大小: {size_kb:.1f} KB")
    else:
        console.print("\n📊 运行统计: 暂无数据")


@app.command()
def tasks():
    """查看定时任务状态"""
    console.print("\n⏰ [bold cyan]定时任务状态[/bold cyan]")

    import subprocess

    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
        )

        lines = result.stdout.strip().split("\n")
        bnb_tasks = [line for line in lines if "bnbquant" in line.lower()]

        if bnb_tasks:
            table = Table(title="已安装的任务")
            table.add_column("PID", style="cyan")
            table.add_column("状态", style="magenta")
            table.add_column("名称", style="green")

            for line in bnb_tasks:
                parts = line.split("\t")
                if len(parts) >= 3:
                    pid = parts[0]
                    status = parts[1]
                    name = parts[2]
                    table.add_row(
                        pid if pid else "-",
                        "✅ 运行中" if pid else "❌ 未运行",
                        name,
                    )

            console.print(table)
        else:
            console.print("❌ [bold red]未安装定时任务[/bold red]")
            console.print("   安装命令: ./scripts/install_launchd.sh")

    except Exception as e:
        console.print(f"❌ [bold red]获取任务状态失败[/bold red]: {e}")


@app.command()
def logs(
    tail: int = typer.Option(20, help="显示最后几行"),
):
    """查看日志"""
    console.print(f"\n📝 [bold cyan]最近 {tail} 行日志[/bold cyan]")

    from bnb_quant_v2.paths import LOG_DIR

    log_files = sorted(LOG_DIR.glob("*.log")) if LOG_DIR.exists() else []

    if not log_files:
        console.print("❌ [bold red]日志目录为空[/bold red]")
        return

    for log_file in log_files:
        console.print(f"\n[bold magenta]{log_file.name}[/bold magenta]")

        try:
            with open(log_file, "r") as f:
                lines = f.readlines()
                for line in lines[-tail:]:
                    console.print(line.rstrip())
        except Exception as e:
            console.print(f"❌ 读取失败: {e}")
