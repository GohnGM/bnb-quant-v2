"""Telegram Bot API 客户端（stdlib urllib，无第三方依赖）。

``dry_run=True`` 或缺少 token 时：返回 ``SendResult(ok=True, dry_run=True)``，不调用 API。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from bnb_quant_v2.notify.config import TelegramConfig, load_telegram_config


@dataclass
class SendResult:
    """单次发送结果。"""

    ok: bool
    dry_run: bool
    message: str
    error: str | None = None  # 失败原因；成功时可能为 message_id 等调试信息


class TelegramClient:
    """封装 ``sendMessage`` API。"""

    def __init__(self, config: TelegramConfig | None = None) -> None:
        self.config = config or load_telegram_config()

    def send(self, text: str) -> SendResult:
        """发送纯文本消息。``parse_mode`` 为空时不设置（避免 Markdown 转义问题）。"""
        cfg = self.config
        effective_dry = cfg.dry_run or not cfg.can_send

        if effective_dry:
            reason = "dry_run" if cfg.dry_run else "disabled_or_missing_token"
            return SendResult(ok=True, dry_run=True, message=text, error=reason)

        url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
        payload: dict[str, str | bool] = {
            "chat_id": cfg.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if cfg.parse_mode:
            payload["parse_mode"] = cfg.parse_mode
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if not body.get("ok"):
                return SendResult(ok=False, dry_run=False, message=text, error=str(body))
            msg_id = body.get("result", {}).get("message_id")
            detail = f"message_id={msg_id}" if msg_id is not None else "sent"
            return SendResult(ok=True, dry_run=False, message=text, error=detail)
        except urllib.error.URLError as e:
            return SendResult(ok=False, dry_run=False, message=text, error=str(e))


def send_message(text: str, config: TelegramConfig | None = None) -> SendResult:
    """便捷函数：单次发送。"""
    return TelegramClient(config).send(text)
