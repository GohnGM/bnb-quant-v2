"""运行时事件日志（供健康检查与日心跳统计）。

持久化：``data/live/run_stats.json``

事件类型
--------
- ``eval``    — 每次 :30 评估（ready / skip_reason / triggers）
- ``sync_5m`` — 5m 增量同步结果

最多保留 ``MAX_EVENTS`` 条，超出时截断最旧记录。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bnb_quant_v2.paths import PROJECT_ROOT

DEFAULT_STATS_PATH = PROJECT_ROOT / "data" / "live" / "run_stats.json"
MAX_EVENTS = 2000


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("events", []))


def append_run_event(
    event_type: str,
    *,
    path: Path = DEFAULT_STATS_PATH,
    **fields: Any,
) -> None:
    """追加一条事件（自动附加 UTC ``at`` 时间戳）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    events = _load_events(path)
    events.append(
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **fields,
        }
    )
    if len(events) > MAX_EVENTS:
        events = events[-MAX_EVENTS:]
    path.write_text(
        json.dumps({"events": events}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def events_in_window(
    start: datetime,
    end: datetime,
    *,
    path: Path = DEFAULT_STATS_PATH,
) -> list[dict[str, Any]]:
    """返回 ``[start, end)`` 时间窗口内的事件（半开区间）。"""
    events = _load_events(path)
    out: list[dict[str, Any]] = []
    for ev in events:
        at = datetime.fromisoformat(ev["at"])
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if start <= at < end:
            out.append(ev)
    return out
