#!/bin/zsh
# launchd 任务入口：加载 .env → 调用各模块脚本。
#
# 任务映射（UTC）:
#   eval      → scripts/runtime/eval_p1_f6_signal.py --telegram --mark-sent
#   heartbeat → scripts/notify/send_daily_heartbeat.py
#   sync5m/1h → scripts/data/sync_live_klines.py
#
# macOS: 须通过 zsh -lc 调用（见 install_launchd.sh），
# 避免 Documents 下直接调 .venv 触发 PermissionError。
set -euo pipefail

TASK="${1:?usage: launchd_task.sh eval|heartbeat|sync5m|sync1h}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export TZ=UTC
export PYTHONPATH="${ROOT}/src"

# 加载 .env（不覆盖已有环境变量）
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" != *"="* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"
    val="${val%\"}"; val="${val#\"}"
    val="${val%\'}"; val="${val#\'}"
    [[ -z "${(P)key:-}" ]] && export "${key}=${val}"
  done < "${ROOT}/.env"
  set +a
fi

PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

case "$TASK" in
  eval)
    exec "$PY" "${ROOT}/scripts/runtime/eval_p1_f6_signal.py" --telegram --mark-sent
    ;;
  heartbeat)
    exec "$PY" "${ROOT}/scripts/notify/send_daily_heartbeat.py"
    ;;
  sync5m)
    exec "$PY" "${ROOT}/scripts/data/sync_live_klines.py" --interval 5m --execute
    ;;
  sync1h)
    exec "$PY" "${ROOT}/scripts/data/sync_live_klines.py" --interval 1h --execute
    ;;
  *)
    echo "unknown task: $TASK" >&2
    exit 1
    ;;
esac
