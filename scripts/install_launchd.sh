#!/usr/bin/env bash
# 安装 launchd 定时任务到 ~/Library/LaunchAgents（阶段 E）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WRAPPER="${ROOT}/scripts/launchd_task.sh"
AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
DOMAIN="gui/$UID_NUM"
PREFIX="com.bnbquant"
ZSH="/bin/zsh"

if [[ ! -x "$WRAPPER" ]]; then
  chmod +x "$WRAPPER"
fi

if [[ ! -x "${ROOT}/.venv/bin/python" ]] && ! command -v python3 >/dev/null; then
  echo "错误: 未找到 Python — 请先创建 venv 并安装依赖" >&2
  exit 1
fi

mkdir -p "$AGENTS" "$ROOT/logs"

write_plist() {
  local name="$1"
  local task="$2"
  local schedule_kind="$3"  # interval | minute | heartbeat
  local log_name="$4"
  local dest="$AGENTS/${PREFIX}.${name}.plist"

  local schedule_xml=""
  case "$schedule_kind" in
    interval)
      schedule_xml="  <key>StartInterval</key>
  <integer>300</integer>"
      ;;
    minute)
      schedule_xml="  <key>StartCalendarInterval</key>
  <dict>
    <key>Minute</key>
    <integer>2</integer>
  </dict>"
      ;;
    minute30)
      schedule_xml="  <key>StartCalendarInterval</key>
  <dict>
    <key>Minute</key>
    <integer>30</integer>
  </dict>"
      ;;
    heartbeat)
      schedule_xml="  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>4</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>"
      ;;
  esac

  cat > "$dest" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PREFIX}.${name}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${ZSH}</string>
    <string>-lc</string>
    <string>exec &quot;${WRAPPER}&quot; ${task}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>LimitLoadToSessionType</key>
  <string>Aqua</string>
${schedule_xml}
  <key>StandardOutPath</key>
  <string>${ROOT}/logs/${log_name}</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/logs/${log_name}</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
PLIST
  echo "  写入 $dest"
}

load_one() {
  local name="$1"
  local plist="$AGENTS/${PREFIX}.${name}.plist"
  launchctl bootout "$DOMAIN" "$plist" 2>/dev/null || true
  if launchctl bootstrap "$DOMAIN" "$plist" 2>/dev/null; then
    echo "  已加载 $name (bootstrap)"
  elif launchctl load "$plist" 2>/dev/null; then
    echo "  已加载 $name (load)"
  else
    echo "  加载失败: $name — 请手动: launchctl bootstrap $DOMAIN $plist" >&2
  fi
}

echo "==> 安装 launchd plist, ROOT=${ROOT}"

if [[ "$ROOT" == *"/Documents/"* ]] || [[ "$ROOT" == *"/Desktop/"* ]] || [[ "$ROOT" == *"/Downloads/"* ]]; then
  echo ""
  echo "!!! 警告: 项目位于 macOS 受保护目录，launchd 很可能无法访问 !!!"
  echo "    请先运行: ./scripts/doctor_launchd.sh"
  echo "    推荐: mv 到 ~/bnb-quant-v2 后再安装"
  echo ""
fi

write_plist "sync5m" "sync5m" "interval" "sync_5m.log"
write_plist "sync1h" "sync1h" "minute" "sync_1h.log"
write_plist "eval" "eval" "minute30" "signal.log"
write_plist "heartbeat" "heartbeat" "heartbeat" "heartbeat.log"

LOAD_SYNC="${LOAD_SYNC:-0}"
for job in eval heartbeat; do
  load_one "$job"
done

if [[ "$LOAD_SYNC" == "1" ]]; then
  load_one "sync5m"
  load_one "sync1h"
  echo "已加载 sync 任务"
else
  echo ""
  echo "跳过 sync5m / sync1h。启用后: LOAD_SYNC=1 $0"
fi

echo ""
echo "手动立即测 eval:"
echo "  /bin/zsh -lc 'exec \"${WRAPPER}\" eval'"
echo "诊断:"
echo "  ./scripts/doctor_launchd.sh"
echo ""
echo "完成。查看: launchctl list | grep bnbquant"
