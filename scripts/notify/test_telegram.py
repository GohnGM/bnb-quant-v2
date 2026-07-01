#!/usr/bin/env python3
"""Telegram 真发连通性测试。"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.notify.config import DEFAULT_ENV_PATH, load_telegram_config
from bnb_quant_v2.notify.telegram import TelegramClient

BEIJING = timezone(timedelta(hours=8))


def _format_dual_time(now: datetime) -> tuple[str, str]:
    utc = now.astimezone(timezone.utc)
    bj = now.astimezone(BEIJING)
    fmt = "%Y-%m-%d %H:%M"
    return utc.strftime(fmt), bj.strftime(fmt)


def _build_test_message() -> str:
    now = datetime.now(timezone.utc)
    utc_s, bj_s = _format_dual_time(now)
    return (
        "🧪 bnb-quant-v2 Telegram 连接测试\n\n"
        "若收到此消息，Bot 配置正确。\n"
        f"UTC: {utc_s}\n"
        f"北京: {bj_s}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a real Telegram test message")
    parser.add_argument(
        "--live",
        action="store_true",
        help="真发（enabled=true, dry_run=false；需 .env 凭证）",
    )
    parser.add_argument("--telegram-config", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_telegram_config(args.telegram_config)
    if args.live:
        cfg = replace(cfg, enabled=True, dry_run=False)

    missing = []
    if not cfg.bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not cfg.chat_id:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        print("缺少凭证，请先配置：", ", ".join(missing), file=sys.stderr)
        print(f"  1. cp .env.example {DEFAULT_ENV_PATH}", file=sys.stderr)
        print("  2. 编辑 .env 填入 Bot Token 与 Chat ID", file=sys.stderr)
        print("  3. 重跑: PYTHONPATH=src python3 scripts/test_telegram.py --live", file=sys.stderr)
        return 1

    if not cfg.enabled or cfg.dry_run:
        print("当前为 dry-run / 未启用。真发请加 --live", file=sys.stderr)
        print("  或改 config/telegram.yaml: enabled=true, dry_run=false", file=sys.stderr)

    text = _build_test_message()
    print("--- 将发送 ---")
    print(text)
    print("--------------")

    res = TelegramClient(cfg).send(text)
    if res.dry_run:
        print("结果: dry-run（未调用 API）")
        return 0
    if res.ok:
        print("结果: ✅ 发送成功，请在 Telegram 查看")
        return 0
    print(f"结果: ❌ 发送失败 — {res.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
