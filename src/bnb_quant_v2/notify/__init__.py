"""通知模块：Telegram + Email。

配置来源（优先级从高到低）::
    1. 环境变量 (``.env`` 或 launchd 注入)
    2. ``config/telegram.yaml`` / ``config/email.yaml``

消息类型
--------
- 信号消息：``format_signal_message`` — 主/严格规则触发
- 告警消息：``format_alert_message`` — 数据不足、sync 失败等
- 心跳消息：``format_heartbeat_message`` — 每日汇总

所有用户可见时间均展示 **UTC + 北京时间** 双时区。
"""

from bnb_quant_v2.notify.config import TelegramConfig, load_email_config, load_telegram_config
from bnb_quant_v2.notify.email import EmailClient, EmailConfig
from bnb_quant_v2.notify.format import format_alert_message, format_signal_message
from bnb_quant_v2.notify.telegram import TelegramClient, send_message

__all__ = [
    "TelegramClient",
    "TelegramConfig",
    "EmailClient",
    "EmailConfig",
    "format_alert_message",
    "format_signal_message",
    "load_telegram_config",
    "load_email_config",
    "send_message",
]
