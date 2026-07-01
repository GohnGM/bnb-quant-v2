#!/usr/bin/env bash
# 卸载 bnb-quant launchd 任务
set -euo pipefail

AGENTS="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
DOMAIN="gui/$UID_NUM"
PREFIX="com.bnbquant"

for job in heartbeat eval sync1h sync5m; do
  plist="$AGENTS/${PREFIX}.${job}.plist"
  if [[ -f "$plist" ]]; then
    launchctl bootout "$DOMAIN" "$plist" 2>/dev/null || launchctl unload "$plist" 2>/dev/null || true
    rm -f "$plist"
    echo "已移除 $job"
  fi
done

echo "完成"
