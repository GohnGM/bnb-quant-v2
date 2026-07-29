"""邮件发送客户端。

支持 SMTP 发送邮件，配置来源：
- 环境变量 EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_USERNAME, EMAIL_PASSWORD
- config/email.yaml
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bnb_quant_v2.notify.telegram import SendResult


@dataclass
class EmailConfig:
    """邮件配置。"""

    enabled: bool = False
    dry_run: bool = True
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_secure: bool = True
    username: str = ""
    password: str = ""
    from_addr: str = ""
    from_name: str = "bnb-quant-v2"
    to_addrs: list[str] = None  # type: ignore[assignment]
    send_on_signal: bool = True
    send_on_error: bool = True
    send_daily_heartbeat: bool = True

    def __post_init__(self):
        if self.to_addrs is None:
            self.to_addrs = []

    @property
    def can_send(self) -> bool:
        """是否具备发送条件。"""
        return self.enabled and bool(self.smtp_host) and bool(self.username) and bool(self.password) and len(self.to_addrs) > 0


class EmailClient:
    """SMTP 邮件发送客户端。"""

    def __init__(self, config: EmailConfig | None = None) -> None:
        from bnb_quant_v2.notify.config import load_email_config
        self.config = config or load_email_config()

    def send(self, subject: str, body: str) -> "SendResult":
        """发送邮件。

        Returns:
            SendResult: 发送结果（复用 Telegram 的 SendResult）。
        """
        from bnb_quant_v2.notify.telegram import SendResult

        cfg = self.config
        effective_dry = cfg.dry_run or not cfg.can_send

        if effective_dry:
            reason = "dry_run" if cfg.dry_run else "disabled_or_missing_config"
            return SendResult(ok=True, dry_run=True, message=body, error=reason)

        msg = MIMEMultipart()
        msg["From"] = f"{cfg.from_name} <{cfg.from_addr or cfg.username}>"
        msg["To"] = ", ".join(cfg.to_addrs)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            if cfg.smtp_secure:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=context, timeout=30) as server:
                    server.login(cfg.username, cfg.password)
                    server.sendmail(cfg.from_addr or cfg.username, cfg.to_addrs, msg.as_string())
            else:
                with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
                    server.starttls()
                    server.login(cfg.username, cfg.password)
                    server.sendmail(cfg.from_addr or cfg.username, cfg.to_addrs, msg.as_string())

            return SendResult(ok=True, dry_run=False, message=body)
        except smtplib.SMTPAuthenticationError as e:
            return SendResult(ok=False, dry_run=False, message=body, error=f"SMTP 认证失败: {e}")
        except smtplib.SMTPConnectError as e:
            return SendResult(ok=False, dry_run=False, message=body, error=f"SMTP 连接失败: {e}")
        except Exception as e:
            return SendResult(ok=False, dry_run=False, message=body, error=f"邮件发送失败: {e}")

    def test_connection(self) -> tuple[bool, str]:
        """测试 SMTP 连接。"""
        cfg = self.config
        if not cfg.can_send:
            return False, "邮件配置不完整"

        try:
            if cfg.smtp_secure:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=context, timeout=10) as server:
                    server.login(cfg.username, cfg.password)
            else:
                with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(cfg.username, cfg.password)
            return True, "SMTP 连接测试成功"
        except Exception as e:
            return False, f"SMTP 连接测试失败: {e}"
