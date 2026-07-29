"""回测子命令：构建特征、运行回测。"""
from __future__ import annotations

import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table

from bnb_quant_v2.analysis.backtest_p1_f6 import (
    PRIMARY_HOUR_RULE,
    compare_push_rules_backtest,
    print_p1_f6_backtest_report,
    run_primary_hour_backtest,
    run_p1_f6_backtest,
)
from bnb_quant_v2.analysis.intra_5m import enrich_p1_f6
from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.paths import ANALYSIS_DIR
from bnb_quant_v2.strategy.base import rule_registry

console = Console()
app = typer.Typer(name="backtest", help="回测（构建特征、运行回测）")

DEFAULT_FEATURES = ANALYSIS_DIR / "BTCUSDT_1h_p1_f6_features.parquet"


@app.command()
def build(
    force: bool = typer.Option(False, "--force", "-f", help="强制重建"),
):
    """构建 p1×f6 特征表"""
    console.print("\n🔨 [bold cyan]构建 p1×f6 特征表[/bold cyan]")

    if DEFAULT_FEATURES.exists() and not force:
        console.print(f"✅ [green]特征表已存在[/green] → {DEFAULT_FEATURES}")
        console.print("💡 使用 --force 强制重建")
        return

    console.print("   加载 K 线数据...")
    store = KlineStore()
    df_1h = store.load("BTCUSDT", "1h")
    df_5m = store.load("BTCUSDT", "5m")

    if df_1h.empty:
        console.print("❌ [bold red]1H 数据为空[/bold red]")
        console.print("   请先导入数据: bnbquant data import --interval 1h")
        return

    if df_5m.empty:
        console.print("❌ [bold red]5m 数据为空[/bold red]")
        console.print("   请先导入数据: bnbquant data import --interval 5m")
        return

    console.print(f"   1H: {len(df_1h)} 条, 5m: {len(df_5m)} 条")
    console.print("   构建特征...")

    df_enriched = enrich_p1_f6(df_1h, df_5m)

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    df_enriched.to_parquet(DEFAULT_FEATURES, index=False)

    console.print(f"\n✅ [bold green]特征表构建成功[/bold green]")
    console.print(f"   输出: {DEFAULT_FEATURES}")
    console.print(f"   行数: {len(df_enriched)}")


@app.command()
def run(
    rebuild: bool = typer.Option(False, help="重建特征表"),
    all_rules: bool = typer.Option(False, help="回测所有规则"),
    push_rules: bool = typer.Option(False, help="回测推送规则"),
    rule_name: str = typer.Option(None, help="指定规则名称"),
):
    """运行回测"""
    console.print("\n📈 [bold cyan]运行回测[/bold cyan]")

    # 确保特征表存在
    if not DEFAULT_FEATURES.exists() or rebuild:
        console.print("   先构建特征表...")
        build(force=True)

    if not DEFAULT_FEATURES.exists():
        console.print("❌ [bold red]特征表构建失败[/bold red]")
        return

    import pandas as pd

    df = pd.read_parquet(DEFAULT_FEATURES)
    console.print(f"   特征表: {len(df)} 行")

    if all_rules:
        console.print("\n   回测所有规则...")
        rules = list(rule_registry.get_enabled())
        results = []

        for rule in rules:
            result = run_p1_f6_backtest(df, rule.metadata.name)
            results.append((rule.metadata.name, result))

        table = Table(title="所有规则回测结果")
        table.add_column("规则", style="cyan")
        table.add_column("信号数", style="magenta")
        table.add_column("准确率", style="green")
        table.add_column("覆盖度", style="yellow")

        for name, result in results:
            table.add_row(
                name,
                str(result.signals),
                f"{result.accuracy:.1%}",
                f"{result.coverage_pct:.1f}%",
            )

        console.print(table)

    elif push_rules:
        console.print("\n   回测推送规则...")
        compare_push_rules_backtest(df)

    elif rule_name:
        console.print(f"\n   回测规则: {rule_name}")
        result = run_p1_f6_backtest(df, rule_name)
        print_p1_f6_backtest_report(result)

    else:
        console.print("\n   回测主规则...")
        run_primary_hour_backtest(df)


@app.command()
def rules():
    """列出所有规则"""
    console.print("\n📋 [bold cyan]已注册规则[/bold cyan]\n")

    rules = list(rule_registry.get_enabled())

    table = Table()
    table.add_column("名称", style="cyan")
    table.add_column("层级", style="magenta")
    table.add_column("风险", style="yellow")
    table.add_column("描述", style="green")

    for rule in rules:
        table.add_row(
            rule.metadata.name,
            rule.metadata.tier,
            rule.metadata.risk,
            rule.metadata.description,
        )

    console.print(table)
