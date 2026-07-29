"""通知子命令：Telegram、心跳。"""
from __future__ import annotations

import typer
from rich.console import Console

console = Console()
app = typer.Typer(name="notify", help="通知（Telegram、心跳）")


@app.command()
def test(
    dry_run: bool = typer.Option(False, help="模拟发送"),
):
    """测试 Telegram 连接"""
    console.print("\n📡 [bold cyan]测试 Telegram 连接[/bold cyan]")

    from bnb_quant_v2.notify.config import load_telegram_config
    from bnb_quant_v2.notify.telegram import TelegramClient

    cfg = load_telegram_config()

    if not cfg.can_send:
        console.print("❌ [bold red]Telegram 未配置[/bold red]")
        console.print("   请编辑 config/telegram.yaml 和 .env 文件")
        console.print("   需要: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        return

    client = TelegramClient(cfg)
    result = client.send("🏗️ bnb-quant-v2 Telegram 测试消息")

    if result.dry_run:
        console.print("✅ [bold yellow]模拟发送成功（dry_run 模式）[/bold yellow]")
    elif result.ok:
        console.print("✅ [bold green]Telegram 测试成功[/bold green]")
    else:
        console.print(f"❌ [bold red]Telegram 测试失败[/bold red]: {result.error}")


@app.command()
def heartbeat(
    dry_run: bool = typer.Option(False, help="模拟发送"),
):
    """发送日心跳"""
    console.print("\n❤️ [bold cyan]发送日心跳[/bold cyan]")

    from bnb_quant_v2.notify.format import format_heartbeat_message
    from bnb_quant_v2.notify.telegram import TelegramClient
    from bnb_quant_v2.notify.config import load_telegram_config

    cfg = load_telegram_config()
    client = TelegramClient(cfg)

    msg = format_heartbeat_message()
    result = client.send(msg)

    if result.dry_run:
        console.print("✅ [bold yellow]模拟心跳发送成功[/bold yellow]")
    elif result.ok:
        console.print("✅ [bold green]心跳发送成功[/bold green]")
    else:
        console.print(f"❌ [bold red]心跳发送失败[/bold red]: {result.error}")


@app.command()
def config():
    """查看 Telegram 配置"""
    console.print("\n⚙️ [bold cyan]Telegram 配置[/bold cyan]")

    from bnb_quant_v2.notify.config import load_telegram_config

    cfg = load_telegram_config()

    console.print(f"\n   启用: {'✅ 是' if cfg.enabled else '❌ 否'}")
    console.print(f"   模拟模式: {'✅ 是' if cfg.dry_run else '❌ 否'}")
    console.print(f"   发送信号: {'✅ 是' if cfg.send_on_signal else '❌ 否'}")
    console.print(f"   发送错误: {'✅ 是' if cfg.send_on_error else '❌ 否'}")
    console.print(f"   发送心跳: {'✅ 是' if cfg.send_daily_heartbeat else '❌ 否'}")
    console.print(f"   Bot Token: {'✅ 已配置' if cfg.bot_token else '❌ 未配置'}")
    console.print(f"   Chat ID: {'✅ 已配置' if cfg.chat_id else '❌ 未配置'}")

    if not cfg.can_send:
        console.print("\n⚠️ [bold yellow]警告：无法发送消息[/bold yellow]")
        console.print("   请检查 .env 文件中的 TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID")
