"""Telegram 推送去重状态。

持久化：``data/live/signal_state.json``

键为 ``hour_open_time``（ISO），值为已推送的规则名列表。
同一 (小时, 规则) 在 launchd 重试或手动重跑时不会二次推送。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from bnb_quant_v2.paths import PROJECT_ROOT

DEFAULT_STATE_PATH = PROJECT_ROOT / "data" / "live" / "signal_state.json"


def _hour_key(hour_open: pd.Timestamp) -> str:
    """将小时开盘时间规范为 UTC ISO 字符串（整点）。"""
    ts = pd.Timestamp(hour_open)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.floor("h").isoformat()


@dataclass
class SignalDedup:
    """按 (hour_open_time, rule_name) 去重，防止 cron 重复推送。"""

    path: Path = DEFAULT_STATE_PATH
    sent: dict[str, list[str]] = field(default_factory=dict)

    def load(self) -> None:
        """从 JSON 加载；文件不存在时初始化为空。"""
        if not self.path.exists():
            self.sent = {}
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.sent = {str(k): list(v) for k, v in data.get("sent", {}).items()}

    def save(self) -> None:
        """写回 JSON，附带 ``updated_at`` 时间戳。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "sent": self.sent,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_sent(self, hour_open: pd.Timestamp, rule_name: str) -> bool:
        return rule_name in self.sent.get(_hour_key(hour_open), [])

    def mark_sent(self, hour_open: pd.Timestamp, rule_name: str) -> None:
        key = _hour_key(hour_open)
        rules = self.sent.setdefault(key, [])
        if rule_name not in rules:
            rules.append(rule_name)

    def filter_unsent(self, hour_open: pd.Timestamp, rule_names: list[str]) -> list[str]:
        return [name for name in rule_names if not self.is_sent(hour_open, name)]
