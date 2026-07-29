"""通知配置加载（Telegram + Email）。

凭证请勿写入 yaml 提交到仓库；使用 ``.env`` 或环境变量。

真发条件
--------
- Telegram: ``config/telegram.yaml``: ``enabled: true``, ``dry_run: false`` + `.env` tokens
- Email: ``config/email.yaml``: ``enabled: true``, ``dry_run: false`` + `.env` password
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from bnb_quant_v2.paths import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "telegram.yaml"
DEFAULT_EMAIL_CONFIG_PATH = PROJECT_ROOT / "config" / "email.yaml"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass
class TelegramConfig:
    """Telegram 推送开关与凭证。"""

    enabled: bool = False
    dry_run: bool = True
    parse_mode: str = "HTML"
    send_on_signal: bool = True  # 规则触发时发信号
    send_on_error: bool = True  # 数据不足 / sync 失败时发告警
    send_daily_heartbeat: bool = True
    bot_token: str = ""
    chat_id: str = ""

    @property
    def can_send(self) -> bool:
        """是否具备真发条件（enabled 且 token/chat_id 非空）。"""
        return self.enabled and bool(self.bot_token) and bool(self.chat_id)


def load_env_file(path: Path | str | None = None) -> None:
    """加载项目根 ``.env``（不覆盖已有环境变量）。

    launchd 通过 ``launchd_task.sh`` 也会加载同一文件。
    """
    env_path = Path(path) if path else DEFAULT_ENV_PATH
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def load_telegram_config(path: Path | str | None = None) -> TelegramConfig:
    """合并 ``.env`` 与 ``telegram.yaml`` 为运行时配置。"""
    load_env_file()
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw: dict = {}
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text()) or {}

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "") or raw.get("bot_token", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "") or raw.get("chat_id", "")

    return TelegramConfig(
        enabled=bool(raw.get("enabled", False)),
        dry_run=bool(raw.get("dry_run", True)),
        parse_mode=str(raw.get("parse_mode", "HTML")),
        send_on_signal=bool(raw.get("send_on_signal", True)),
        send_on_error=bool(raw.get("send_on_error", True)),
        send_daily_heartbeat=bool(raw.get("send_daily_heartbeat", True)),
        bot_token=str(token),
        chat_id=str(chat_id),
    )


def load_email_config(path: Path | str | None = None):
    """合并 ``.env`` 与 ``email.yaml`` 为运行时配置。"""
    from bnb_quant_v2.notify.email import EmailConfig

    load_env_file()
    cfg_path = Path(path) if path else DEFAULT_EMAIL_CONFIG_PATH
    raw: dict = {}
    if cfg_path.exists():
        raw = yaml.safe_load(cfg_path.read_text()) or {}

    password = os.environ.get("EMAIL_PASSWORD", "") or raw.get("password", "")
    smtp_host = os.environ.get("EMAIL_SMTP_HOST", "") or raw.get("smtp_host", "")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "") or raw.get("smtp_port", 465))
    username = os.environ.get("EMAIL_USERNAME", "") or raw.get("username", "")

    to_addrs = raw.get("to_addrs", [])
    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]

    return EmailConfig(
        enabled=bool(raw.get("enabled", False)),
        dry_run=bool(raw.get("dry_run", True)),
        smtp_host=str(smtp_host),
        smtp_port=smtp_port,
        smtp_secure=bool(raw.get("smtp_secure", True)),
        username=str(username),
        password=str(password),
        from_addr=str(raw.get("from_addr", "")),
        from_name=str(raw.get("from_name", "bnb-quant-v2")),
        to_addrs=list(to_addrs),
    )
