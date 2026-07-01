#!/usr/bin/env bash
# 诊断 launchd 能否访问项目目录（Documents 隐私限制）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "项目路径: $ROOT"
echo ""

fail=0

if [[ "$ROOT" == *"/Documents/"* ]] || [[ "$ROOT" == *"/Desktop/"* ]] || [[ "$ROOT" == *"/Downloads/"* ]]; then
  echo "⚠ 项目在受保护目录（Documents/Desktop/Downloads）"
  echo "  launchd 后台任务通常无法读取，会导致 PermissionError / exit 127"
  echo ""
  echo "  方案 A（推荐）: 移出 Documents"
  echo "    mv \"$ROOT\" \"\$HOME/bnb-quant-v2\""
  echo "    cd \"\$HOME/bnb-quant-v2\" && rm -rf .venv && python3 -m venv .venv"
  echo "    .venv/bin/pip install pandas pyyaml numpy pyarrow loguru"
  echo "    ./scripts/install_launchd.sh"
  echo ""
  echo "  方案 B: 系统设置 → 隐私与安全性 → 完全磁盘访问 → 添加 /bin/zsh"
  echo "    然后重新: ./scripts/install_launchd.sh"
  echo ""
  fail=1
fi

check_read() {
  local label="$1"
  local path="$2"
  if /bin/zsh -lc "test -r '$path'" 2>/dev/null; then
    echo "✓ $label 可读"
  else
    echo "✗ $label 不可读（launchd 会失败）"
    fail=1
  fi
}

check_read "launchd_task.sh" "${ROOT}/scripts/launchd_task.sh"
check_read ".venv/pyvenv.cfg" "${ROOT}/.venv/pyvenv.cfg"
check_read ".env" "${ROOT}/.env"

echo ""
echo "模拟 launchd 执行:"
if /bin/zsh -lc "exec '${ROOT}/scripts/launchd_task.sh' eval" 2>&1 | tail -5; then
  echo ""
  echo "✓ 模拟执行成功"
else
  echo ""
  echo "✗ 模拟执行失败"
  fail=1
fi

echo ""
if [[ "$fail" -eq 0 ]]; then
  echo "结论: 环境 OK，可 install_launchd.sh"
  exit 0
fi
echo "结论: 需先处理上述问题再装 launchd"
exit 1
