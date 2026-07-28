"""数据管理子命令：导入、同步、验证。"""
from __future__ import annotations

import typer
from pathlib import Path
from rich.console import Console

from bnb_quant_v2.data.importers import discover_gate_files, import_gate_directory
from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.data.quality import audit_klines
from bnb_quant_v2.paths import KLINE_DIR

console = Console()
app = typer.Typer(name="data", help="数据管理（导入、同步、验证）")


@app.command()
def import_(
    dir: Path = typer.Option(
        None,
        "--dir",
        "-d",
        help="Gate CSV 目录",
    ),
    symbol: str = typer.Option("BTCUSDT", help="交易对"),
    interval: str = typer.Option("1h", help="时间间隔（1h/5m）"),
    pattern: str = typer.Option("*.csv.gz", help="文件匹配模式"),
    dry_run: bool = typer.Option(False, help="只列出文件不导入"),
):
    """导入 Gate CSV 数据"""
    data_dir = dir
    if data_dir is None:
        data_dir = (
            Path.home() / "Downloads" / "5mdata"
            if interval == "5m"
            else Path.home() / "Downloads" / "gate1hData"
        )

    console.print(f"\n📥 [bold cyan]导入 {symbol} {interval} 数据[/bold cyan]")
    console.print(f"   目录: {data_dir}")

    if dry_run:
        files = discover_gate_files(data_dir, symbol=symbol, pattern=pattern)
        console.print(f"   匹配 {len(files)} 个文件")
        for f in files:
            console.print(f"      {f.name}")
        console.print(f"\n💡 运行命令导入: bnbquant data import --dir {data_dir} --interval {interval}")
        return

    path = import_gate_directory(data_dir, symbol, interval, pattern=pattern)
    console.print(f"\n✅ [bold green]导入成功[/bold green] → {path}")


@app.command()
def sync(
    interval: str = typer.Option("5m", help="时间间隔（5m/1h）"),
    dry_run: bool = typer.Option(False, help="模拟同步"),
):
    """同步实时 K 线数据"""
    console.print(f"\n🔄 [bold cyan]同步 {interval} 数据[/bold cyan]")

    from bnb_quant_v2.data.live.config import load_live_sync_config
    from bnb_quant_v2.data.live.scheduler import run_live_sync

    config = load_live_sync_config()
    if not config.enabled:
        console.print("❌ [bold red]实时同步未启用[/bold red]")
        console.print("   请编辑 config/live_sync.yaml，设置 enabled: true")
        return

    if dry_run:
        console.print("📋 [bold yellow]模拟同步模式[/bold yellow]")
        from bnb_quant_v2.data.live.scheduler import build_sync_plan

        plan = build_sync_plan(config, interval)
        console.print(f"   计划同步: {plan}")
        return

    result = run_live_sync(config, interval)
    console.print(f"\n✅ [bold green]同步成功[/bold green]")
    console.print(f"   更新: {result.updated} 条")
    console.print(f"   新增: {result.added} 条")


@app.command()
def validate(
    symbol: str = typer.Option("BTCUSDT", help="交易对"),
):
    """验证数据质量"""
    console.print(f"\n🔍 [bold cyan]验证 {symbol} 数据质量[/bold cyan]")

    klines_1h = KlineStore(symbol, "1h")
    klines_5m = KlineStore(symbol, "5m")

    df_1h = klines_1h.load()
    df_5m = klines_5m.load()

    console.print(f"\n📊 1H 数据: {len(df_1h)} 条")
    console.print(f"📊 5m 数据: {len(df_5m)} 条")

    if not df_1h.empty:
        result_1h = audit_klines(df_1h, "1h")
        console.print(f"\n1H 审计:")
        console.print(f"   时间范围: {df_1h['open_time'].min()} → {df_1h['open_time'].max()}")
        console.print(f"   完整性: {result_1h.completeness_pct:.1f}%")
        console.print(f"   异常: {result_1h.anomalies} 条")

    if not df_5m.empty:
        result_5m = audit_klines(df_5m, "5m")
        console.print(f"\n5m 审计:")
        console.print(f"   时间范围: {df_5m['open_time'].min()} → {df_5m['open_time'].max()}")
        console.print(f"   完整性: {result_5m.completeness_pct:.1f}%")
        console.print(f"   异常: {result_5m.anomalies} 条")


@app.command(name="list")
def list_():
    """列出已导入的数据"""
    console.print("\n📁 [bold cyan]已导入的数据[/bold cyan]\n")

    if not KLINE_DIR.exists():
        console.print("❌ 数据目录不存在")
        return

    files = sorted(KLINE_DIR.glob("*.parquet"))
    if not files:
        console.print("❌ 没有数据文件")
        console.print("💡 使用 `bnbquant data import` 导入数据")
        return

    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        console.print(f"   ✅ [green]{f.name}[/green] ({size_mb:.1f} MB)")
