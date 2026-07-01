# bnb-quant-v2

干净起点。Gate CSV 导入使用官方列顺序：`timestamp, volume, close, high, low, open`。

## 四个模块

| 模块 | 包路径 | 脚本目录 | 职责 |
|------|--------|----------|------|
| **一、获取数据** | `bnb_quant_v2.data` | `scripts/data/` | Gate CSV 导入、K 线存储、质量审计、实时同步（Gate API 占位） |
| **二、分析策略** | `bnb_quant_v2.analysis` | `scripts/analysis/` | 特征工程、回测、规则评估、`:30` 信号判定 |
| **三、Telegram** | `bnb_quant_v2.notify` | `scripts/notify/` | 配置、消息模板、Bot API |
| **四、保持运行** | `bnb_quant_v2.runtime` | `scripts/runtime/` | 流水线编排、去重、运行统计、健康检查 |

`bnb_quant_v2.signal` 为兼容层，新代码请用 `analysis` + `runtime`。

**新人上手**：见 [docs/RUN.md](RUN.md)（运行哪些脚本、怎么跑通项目）。  
**Gate API 交接配置**：见 [docs/GATE_API_SETUP.md](docs/GATE_API_SETUP.md)。

## 环境

```bash
cd bnb-quant-v2
python3 -m venv .venv
source .venv/bin/activate
pip install pandas pyyaml numpy pyarrow loguru
# 开发/测试可选: pip install pytest
```

复制并填写 Telegram 凭证：

```bash
cp .env.example .env
# 编辑 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
```

连通性测试：

```bash
PYTHONPATH=src python scripts/notify/test_telegram.py --live
```

---

## 本机部署（阶段 E · launchd）

将 **:30 信号评估** 与 **每日心跳** 挂到 macOS 计划任务（时区 **UTC**）。

### 前置

1. `.env` 已填 Telegram 凭证
2. `config/telegram.yaml`：`enabled: true`、`dry_run: false`
3. `data/klines/` 有离线 parquet（阶段 B 未通前用历史数据）
4. 本机 **接电源、关闭睡眠**（或另开终端 `caffeinate -dims &`）

### 安装

```bash
cd bnb-quant-v2
chmod +x scripts/install_launchd.sh scripts/uninstall_launchd.sh
./scripts/install_launchd.sh
```

默认只加载 **eval** + **heartbeat**；Gate sync 在阶段 B 启用后再：

```bash
# config/live_sync.yaml → enabled: true 之后
LOAD_SYNC=1 ./scripts/install_launchd.sh
```

### 查看 / 卸载

```bash
# 任务是否在跑
launchctl list | grep bnbquant

# 日志
tail -f logs/signal.log
tail -f logs/heartbeat.log

# 健康检查
PYTHONPATH=src python scripts/runtime/check_live_health.py

# 卸载全部定时任务
./scripts/uninstall_launchd.sh
```

### 定时一览（UTC）

| 任务 | 时间 | 说明 |
|------|------|------|
| eval | 每小时 :30 | p1×f6 主/严格规则 → Telegram |
| heartbeat | 每天 04:00 | 日心跳（12:00 北京） |
| sync 5m | 每 5 分钟 | 需 `LOAD_SYNC=1` + live_sync 启用 |
| sync 1h | 每小时 :02 | 同上 |

阶段 B 可用后，可编辑 `~/Library/LaunchAgents/com.bnbquant.eval.plist`，在 `eval_p1_f6_signal.py` 参数中增加 `--sync`，再 `launchctl bootout` / `bootstrap` 重载。

### 故障排查

**`:30` 没收到 Telegram / `logs/signal.log` 出现 `PermissionError: pyvenv.cfg`**

macOS 下 launchd **不能直接** 调用 `Documents` 里的 `.venv/bin/python`。已改为通过 `scripts/launchd_task.sh` + `zsh -lic` 执行。修复后请重装：

```bash
./scripts/install_launchd.sh
```

手动模拟 launchd 跑一次（应 `alerts=1` 且 Telegram 收到「数据不足」告警）：

```bash
/bin/zsh -lic scripts/launchd_task.sh eval
tail -20 logs/signal.log
```

若仍失败：系统设置 → 隐私与安全性 → **完全磁盘访问权限**，为 **/bin/zsh** 开启；或把项目移到 `~/bnb-quant-v2`（**推荐**）。

```bash
# 推荐：移出 Documents（一次性）
mv ~/Documents/BNBWork/bnb-quant-v2 ~/bnb-quant-v2
cd ~/bnb-quant-v2
rm -rf .venv && python3 -m venv .venv
.venv/bin/pip install pandas pyyaml numpy pyarrow loguru
./scripts/doctor_launchd.sh
./scripts/install_launchd.sh
```

注意：复制粘贴命令时 **不要** 把以 `#` 开头的注释行一起执行（会出现 `zsh: command not found: #`）。

---

## 导入 Gate K 线

```bash
python scripts/data/import_gate.py --dir ~/Downloads/gate1hData --interval 1h
```

输出：`data/klines/BTCUSDT_1h.parquet`

## 实时数据（计划任务，暂未接入交易所）

离线研究仍用 Gate CSV；实时增量同步见 [docs/plan_live_data.md](docs/plan_live_data.md)。

```bash
# 查看将执行的同步计划（默认 dry-run）
PYTHONPATH=src python scripts/data/sync_live_klines.py

# 建议 crontab
PYTHONPATH=src python scripts/data/sync_live_klines.py --show-cron
```

配置：`config/live_sync.yaml`（当前 `enabled: false`）

完整流水线（实时数据 → 信号 → Telegram）见 [docs/plan_live_telegram.md](docs/plan_live_telegram.md)。

**启用真实 Telegram 推送**：在 `.env` 填写 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`，并将 `config/telegram.yaml` 设为 `enabled: true`、`dry_run: false`。详见计划文档 [§8.1](docs/plan_live_telegram.md#81-启用真实-telegram-推送)。

## p1×f6 主规则回测

```bash
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --rebuild
```

## 1H 方向预测（仅前 1 根）

```bash
PYTHONPATH=src python scripts/analysis/analyze_1h_prediction.py
```
