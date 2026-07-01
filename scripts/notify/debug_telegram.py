#!/usr/bin/env python3
"""Telegram 诊断：getMe + 发告警模板 + 打印结果。"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from bnb_quant_v2.notify.config import load_telegram_config
from bnb_quant_v2.notify.format import format_alert_message
from bnb_quant_v2.notify.telegram import TelegramClient

import pandas as pd


def get_me(token: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/getMe"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    cfg = load_telegram_config()
    print(f"enabled={cfg.enabled} dry_run={cfg.dry_run} can_send={cfg.can_send}")
    if not cfg.bot_token:
        print("缺少 TELEGRAM_BOT_TOKEN", file=sys.stderr)
        return 1

    me = get_me(cfg.bot_token)
    if me.get("ok"):
        u = me["result"]
        print(f"bot: @{u.get('username')} ({u.get('first_name')})")
    else:
        print(f"getMe 失败: {me}", file=sys.stderr)
        return 1

    if not cfg.chat_id:
        print("缺少 TELEGRAM_CHAT_ID", file=sys.stderr)
        return 1

    chat_tail = cfg.chat_id[-4:] if len(cfg.chat_id) >= 4 else "????"
    print(f"chat_id: ...{chat_tail} (len={len(cfg.chat_id)})")

    text = format_alert_message(
        "eval 数据不足",
        "诊断测试：若收到此条，告警通道正常",
        as_of=pd.Timestamp.now(tz="UTC"),
    )
    live = type(cfg)(**{**cfg.__dict__, "enabled": True, "dry_run": False})
    res = TelegramClient(live).send(text)
    if res.ok and not res.dry_run:
        print(f"sendMessage: OK ({res.error})")
        return 0
    print(f"sendMessage 失败: dry_run={res.dry_run} error={res.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
