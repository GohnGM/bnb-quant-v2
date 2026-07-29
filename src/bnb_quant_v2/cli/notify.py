"""通知子命令：Telegram、Email、心跳。"""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

console = Console()
app = typer.Typer(name="notify", help="通知（Telegram、Email、心跳）")


@app.command()
def test(
    dry_run: bool = typer.Option(False, help="模拟发送"),
    channel: str = typer.Option("telegram", "--channel", "-c", help="通知渠道: telegram/email/all"),
):
    """测试通知连接"""
    console.print("\n📡 [bold cyan]测试通知连接[/bold cyan]")

    if channel in ("telegram", "all"):
        _test_telegram(dry_run)

    if channel in ("email", "all"):
        _test_email(dry_run)


def _test_telegram(dry_run: bool = False):
    """测试 Telegram 连接"""
    console.print("\n   [bold]Telegram:[/bold]")

    from bnb_quant_v2.notify.config import load_telegram_config
    from bnb_quant_v2.notify.telegram import TelegramClient

    cfg = load_telegram_config()

    if not cfg.can_send:
        console.print("   ❌ Telegram 未配置")
        console.print("      请编辑 config/telegram.yaml 和 .env 文件")
        console.print("      需要: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        return

    client = TelegramClient(cfg)
    msg = "🏗️ 紫御BTC量化分析系统 Telegram 测试消息"
    if dry_run:
        cfg.dry_run = True
        cfg.enabled = True
    result = client.send(msg)

    if result.dry_run:
        console.print("   ✅ 模拟发送成功（dry_run 模式）")
    elif result.ok:
        console.print("   ✅ Telegram 测试成功")
    else:
        console.print(f"   ❌ Telegram 测试失败: {result.error}")


def _test_email(dry_run: bool = False):
    """测试 Email 连接"""
    console.print("\n   [bold]Email:[/bold]")

    from bnb_quant_v2.notify.config import load_email_config
    from bnb_quant_v2.notify.email import EmailClient

    cfg = load_email_config()

    if not cfg.can_send and not dry_run:
        console.print("   ❌ Email 未配置")
        console.print("      请编辑 config/email.yaml 和 .env 文件")
        console.print("      需要: EMAIL_PASSWORD (SMTP 授权码)")
        return

    if dry_run:
        cfg.dry_run = True
        cfg.enabled = True

    client = EmailClient(cfg)

    if not dry_run:
        # 先测试连接
        ok, msg = client.test_connection()
        if not ok:
            console.print(f"   ❌ SMTP 连接失败: {msg}")
            return
        console.print(f"   ✅ SMTP 连接成功: {msg}")

    # 发送测试邮件
    result = client.send(
        "🏗️ 紫御BTC量化分析系统 邮件测试",
        "这是一封来自紫御BTC量化分析系统的测试邮件。"
    )

    if result.dry_run:
        console.print("   ✅ 模拟发送成功（dry_run 模式）")
    elif result.ok:
        console.print("   ✅ Email 测试成功")
    else:
        console.print(f"   ❌ Email 测试失败: {result.error}")


@app.command()
def heartbeat(
    dry_run: bool = typer.Option(False, help="模拟发送"),
    channel: str = typer.Option("telegram", "--channel", "-c", help="通知渠道: telegram/email/all"),
):
    """发送日心跳"""
    console.print("\n❤️ [bold cyan]发送日心跳[/bold cyan]")

    from bnb_quant_v2.notify.format import format_heartbeat_message
    from bnb_quant_v2.notify.config import load_telegram_config, load_email_config
    from bnb_quant_v2.notify.telegram import TelegramClient
    from bnb_quant_v2.notify.email import EmailClient

    # 生成心跳消息（简化版）
    from bnb_quant_v2.notify.config import load_email_config as _load_email
    from datetime import timedelta
    import pandas as pd

    end = pd.Timestamp.utcnow()
    start = end - timedelta(hours=24)
    msg = format_heartbeat_message(
        period_start=start,
        period_end=end,
        sync_5m_ok=0,
        sync_5m_total=0,
        sync_1h_ok=0,
        sync_1h_total=0,
        eval_count=0,
        primary_triggers=0,
        strict_triggers=0,
        primary_short_triggers=0,
        strict_short_triggers=0,
        latest_5m=None,
        status="正常",
    )

    if channel in ("telegram", "all"):
        tg_cfg = load_telegram_config()
        tg_client = TelegramClient(tg_cfg)
        result = tg_client.send(msg)
        if result.dry_run:
            console.print("   ✅ Telegram 模拟心跳发送成功")
        elif result.ok:
            console.print("   ✅ Telegram 心跳发送成功")
        else:
            console.print(f"   ❌ Telegram 心跳发送失败: {result.error}")

    if channel in ("email", "all"):
        email_cfg = load_email_config()
        email_client = EmailClient(email_cfg)
        result = email_client.send("💓 紫御BTC量化分析系统 日心跳", msg)
        if result.dry_run:
            console.print("   ✅ Email 模拟心跳发送成功")
        elif result.ok:
            console.print("   ✅ Email 心跳发送成功")
        else:
            console.print(f"   ❌ Email 心跳发送失败: {result.error}")


@app.command()
def config():
    """查看通知配置"""
    console.print("\n⚙️ [bold cyan]通知配置[/bold cyan]")

    from bnb_quant_v2.notify.config import load_telegram_config, load_email_config

    # Telegram 配置
    tg_cfg = load_telegram_config()

    table_tg = Table(title="Telegram")
    table_tg.add_column("配置项", style="cyan")
    table_tg.add_column("值", style="green")

    table_tg.add_row("启用", "✅ 是" if tg_cfg.enabled else "❌ 否")
    table_tg.add_row("模拟模式", "✅ 是" if tg_cfg.dry_run else "❌ 否")
    table_tg.add_row("发送信号", "✅ 是" if tg_cfg.send_on_signal else "❌ 否")
    table_tg.add_row("发送错误告警", "✅ 是" if tg_cfg.send_on_error else "❌ 否")
    table_tg.add_row("发送心跳", "✅ 是" if tg_cfg.send_daily_heartbeat else "❌ 否")
    table_tg.add_row("Bot Token", "✅ 已配置" if tg_cfg.bot_token else "❌ 未配置")
    table_tg.add_row("Chat ID", "✅ 已配置" if tg_cfg.chat_id else "❌ 未配置")
    table_tg.add_row("发送能力", "✅ 可用" if tg_cfg.can_send else "❌ 不可用")

    console.print(table_tg)

    # Email 配置
    email_cfg = load_email_config()

    table_email = Table(title="Email")
    table_email.add_column("配置项", style="cyan")
    table_email.add_column("值", style="green")

    table_email.add_row("启用", "✅ 是" if email_cfg.enabled else "❌ 否")
    table_email.add_row("模拟模式", "✅ 是" if email_cfg.dry_run else "❌ 否")
    table_email.add_row("SMTP 服务器", f"{email_cfg.smtp_host}:{email_cfg.smtp_port}")
    table_email.add_row("SSL/TLS", "✅ SSL" if email_cfg.smtp_secure else "✅ STARTTLS")
    table_email.add_row("发送信号", "✅ 是" if email_cfg.send_on_signal else "❌ 否")
    table_email.add_row("发送错误告警", "✅ 是" if email_cfg.send_on_error else "❌ 否")
    table_email.add_row("发送心跳", "✅ 是" if email_cfg.send_daily_heartbeat else "❌ 否")
    table_email.add_row("发件人", f"{email_cfg.from_name} <{email_cfg.from_addr or email_cfg.username}>")
    table_email.add_row("收件人", f"{len(email_cfg.to_addrs)} 个")
    table_email.add_row("密码", "✅ 已配置" if email_cfg.password else "❌ 未配置")
    table_email.add_row("发送能力", "✅ 可用" if email_cfg.can_send else "❌ 不可用")

    console.print(table_email)

    if not tg_cfg.can_send and not email_cfg.can_send:
        console.print("\n⚠️ [bold yellow]警告：没有可用的通知渠道[/bold yellow]")
        console.print("   请至少配置一个通知渠道")
        console.print("   Telegram: 编辑 config/telegram.yaml 和 .env")
        console.print("   Email: 编辑 config/email.yaml 和 .env")
