#!/usr/bin/env bash
# ============================================================
# 紫御BTC量化分析系统 - 统一启动脚本
# 
# 用法:
#   ./start.sh              # 启动 WebUI (默认)
#   ./start.sh web          # 仅启动 WebUI
#   ./start.sh pipeline     # 仅启动后台 Pipeline
#   ./start.sh all          # 启动 WebUI + Pipeline
#   ./start.sh doctor       # 环境诊断
#   ./start.sh status       # 查看运行状态
#   ./start.sh stop         # 停止所有服务
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# ---------- 颜色 ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║          紫御BTC量化分析系统 · 启动器                       ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()      { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_err()     { echo -e "${RED}[ERR]${NC} $*"; }
log_step()    { echo -e "${CYAN}  ➜ $*${NC}"; }

# ---------- 配置 ----------
WEBUI_PORT=8501
WEBUI_HOST="localhost"
PID_DIR="$ROOT/.pids"
LOG_DIR="$ROOT/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

WEBUI_PID_FILE="$PID_DIR/webui.pid"
PIPELINE_PID_FILE="$PID_DIR/pipeline.pid"

# ---------- 依赖检查 ----------
find_python() {
    # 按优先级查找 python，选择有 streamlit 的版本
    local candidates=()

    # 1. 项目 venv
    [[ -f "$ROOT/.venv/bin/python3" ]] && candidates+=("$ROOT/.venv/bin/python3")

    # 2. 常见 Homebrew / 本地路径
    for p in /usr/local/bin/python3 /opt/homebrew/bin/python3; do
        [[ -f "$p" ]] && candidates+=("$p")
    done

    # 3. PATH 中的 python3
    local sys_py
    sys_py="$(command -v python3 2>/dev/null || true)"
    [[ -n "$sys_py" ]] && candidates+=("$sys_py")

    # 选择第一个能 import streamlit 的
    for py in "${candidates[@]}"; do
        if "$py" -c "import streamlit" 2>/dev/null; then
            echo "$py"
            return 0
        fi
    done

    # 都不行，返回第一个候选
    if [[ ${#candidates[@]} -gt 0 ]]; then
        echo "${candidates[0]}"
    else
        echo ""
    fi
}

check_python() {
    local py
    py=$(find_python)
    if [[ -z "$py" ]]; then
        log_err "未找到 python3，请先安装 Python 3.9+"
        return 1
    fi
    log_step "Python: $($py --version)"
    PY="$py"
}

check_deps() {
    local py="$1"
    log_step "检查依赖包..."
    local missing=()
    for pkg in streamlit pandas pyarrow pyyaml numpy loguru typer rich; do
        local mod="${pkg//-/_}"
        if ! "$py" -c "import importlib; importlib.import_module('$mod')" 2>/dev/null; then
            missing+=("$pkg")
        fi
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "缺少: ${missing[*]}，正在安装..."
        "$py" -m pip install "${missing[@]}" -q
        log_ok "依赖安装完成"
    else
        log_ok "依赖检查通过"
    fi
}

# ---------- 端口检测 ----------
port_in_use() {
    local port=$1
    lsof -i ":$port" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN
}

# ---------- 进程管理 ----------
is_running() {
    local pid_file=$1
    if [[ -f "$pid_file" ]]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null)
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

stop_service() {
    local name=$1
    local pid_file=$2
    if is_running "$pid_file"; then
        local pid
        pid=$(cat "$pid_file")
        log_step "停止 $name (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pid_file"
        log_ok "$name 已停止"
    else
        log_info "$name 未运行"
    fi
}

# ---------- 启动 WebUI ----------
start_webui() {
    log_info "启动 WebUI (端口: $WEBUI_PORT)..."

    if is_running "$WEBUI_PID_FILE"; then
        local pid
        pid=$(cat "$WEBUI_PID_FILE")
        log_warn "WebUI 已在运行 (PID: $pid)"
        log_info "  访问: http://$WEBUI_HOST:$WEBUI_PORT"
        return 0
    fi

    if port_in_use "$WEBUI_PORT"; then
        log_warn "端口 $WEBUI_PORT 已被占用，尝试释放..."
        lsof -ti ":$WEBUI_PORT" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi

    local py="${PY:-python3}"
    nohup "$py" -m streamlit run src/bnb_quant_v2/webui/app.py \
        --server.port "$WEBUI_PORT" \
        --server.address "$WEBUI_HOST" \
        > "$LOG_DIR/webui.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$WEBUI_PID_FILE"
    sleep 3
    if is_running "$WEBUI_PID_FILE"; then
        log_ok "WebUI 启动成功 (PID: $pid)"
        log_info "  访问: ${BOLD}http://$WEBUI_HOST:$WEBUI_PORT${NC}"
    else
        log_err "WebUI 启动失败，查看日志: $LOG_DIR/webui.log"
        tail -5 "$LOG_DIR/webui.log"
        return 1
    fi
}

# ---------- 启动 Pipeline ----------
start_pipeline() {
    log_info "启动后台 Pipeline..."

    if is_running "$PIPELINE_PID_FILE"; then
        local pid
        pid=$(cat "$PIPELINE_PID_FILE")
        log_warn "Pipeline 已在运行 (PID: $pid)"
        return 0
    fi

    local py="${PY:-python3}"
    nohup "$py" -m bnb_quant_v2.cli.pipeline run \
        > "$LOG_DIR/pipeline.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$PIPELINE_PID_FILE"

    sleep 2
    if is_running "$PIPELINE_PID_FILE"; then
        log_ok "Pipeline 启动成功 (PID: $pid)"
    else
        log_err "Pipeline 启动失败，查看日志: $LOG_DIR/pipeline.log"
        tail -5 "$LOG_DIR/pipeline.log"
        return 1
    fi
}

# ---------- 状态查看 ----------
show_status() {
    echo ""
    log_info "运行状态:"
    echo ""

    if is_running "$WEBUI_PID_FILE"; then
        local pid
        pid=$(cat "$WEBUI_PID_FILE")
        echo -e "  ${GREEN}●${NC} WebUI     PID=$pid  →  http://$WEBUI_HOST:$WEBUI_PORT"
    else
        echo -e "  ${RED}○${NC} WebUI     未运行"
    fi

    if is_running "$PIPELINE_PID_FILE"; then
        local pid
        pid=$(cat "$PIPELINE_PID_FILE")
        echo -e "  ${GREEN}●${NC} Pipeline  PID=$pid"
    else
        echo -e "  ${RED}○${NC} Pipeline  未运行"
    fi

    echo ""
    log_info "日志文件:"
    echo "  WebUI:    $LOG_DIR/webui.log"
    echo "  Pipeline: $LOG_DIR/pipeline.log"
    echo ""
}

# ---------- 环境诊断 ----------
run_doctor() {
    echo ""
    log_info "环境诊断:"
    echo ""

    log_step "项目路径: $ROOT"
    log_step "操作系统: $(uname -s) $(uname -m)"

    local py
    py=$(find_python)
    PY="$py"
    log_step "Python 版本: $($py --version)"

    local issues=0

    # 检查 .env
    if [[ -f "$ROOT/.env" ]]; then
        log_ok ".env 文件存在"
    else
        log_warn ".env 文件不存在，复制 .env.example"
        if [[ -f "$ROOT/.env.example" ]]; then
            cp "$ROOT/.env.example" "$ROOT/.env"
            log_ok "已创建 .env"
        else
            issues=$((issues + 1))
            log_err ".env.example 也不存在"
        fi
    fi

    # 检查 config 文件
    for f in settings.yaml telegram.yaml email.yaml live_sync.yaml; do
        if [[ -f "$ROOT/config/$f" ]]; then
            log_ok "config/$f"
        else
            issues=$((issues + 1))
            log_err "config/$f 缺失"
        fi
    done

    # 检查数据
    if [[ -f "$ROOT/data/klines/BTCUSDT_1h.parquet" ]]; then
        log_ok "K线数据存在"
    else
        log_warn "K线数据不存在，请先导入数据"
        issues=$((issues + 1))
    fi

    # 检查 Streamlit
    if "$py" -c "import importlib; importlib.import_module('streamlit')" 2>/dev/null; then
        log_ok "Streamlit 已安装"
    else
        issues=$((issues + 1))
        log_err "Streamlit 未安装"
    fi

    echo ""
    if [[ $issues -eq 0 ]]; then
        log_ok "环境诊断通过 ✓"
    else
        log_warn "发现 $issues 个问题，请检查上方日志"
    fi
    echo ""
}

# ---------- 主入口 ----------
main() {
    local cmd="${1:-web}"

    print_banner

    case "$cmd" in
        web)
            check_python
            check_deps "$PY"
            start_webui
            show_status
            ;;
        pipeline)
            check_python
            start_pipeline
            show_status
            ;;
        all)
            check_python
            check_deps "$PY"
            start_webui
            start_pipeline
            show_status
            ;;
        stop)
            stop_service "WebUI" "$WEBUI_PID_FILE"
            stop_service "Pipeline" "$PIPELINE_PID_FILE"
            ;;
        status)
            show_status
            ;;
        doctor)
            run_doctor
            ;;
        restart)
            stop_service "WebUI" "$WEBUI_PID_FILE"
            stop_service "Pipeline" "$PIPELINE_PID_FILE"
            sleep 1
            check_python
            check_deps "$PY"
            start_webui
            start_pipeline
            show_status
            ;;
        *)
            echo ""
            log_err "未知命令: $cmd"
            echo ""
            echo "用法: $0 [命令]"
            echo ""
            echo "  web        仅启动 WebUI (默认)"
            echo "  pipeline   仅启动后台 Pipeline"
            echo "  all        启动 WebUI + Pipeline"
            echo "  stop       停止所有服务"
            echo "  status     查看运行状态"
            echo "  doctor     环境诊断"
            echo "  restart    重启所有服务"
            echo ""
            exit 1
            ;;
    esac
}

main "$@"
