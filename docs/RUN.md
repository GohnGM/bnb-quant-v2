# 运行脚本说明（新人上手）

> 所有 Python 命令均在**项目根目录**执行，且需加 `PYTHONPATH=src`。  
> 建议先：`cd bnb-quant-v2 && source .venv/bin/activate`

---

## 一、5 分钟跑起来（最小路径）

```bash
# 1. 环境（首次）
python3 -m venv .venv && source .venv/bin/activate
pip install pandas pyyaml numpy pyarrow loguru pytest

# 2. 确认代码没问题
PYTHONPATH=src pytest tests/ -q

# 3. 跑回测（需已有 data/klines/*.parquet；没有则先做第 4 步）
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --rebuild

# 4. 若没有 K 线数据：从 Gate CSV 导入
python scripts/data/import_gate.py --dir ~/Downloads/gate1hData --interval 1h
python scripts/data/import_gate.py --dir ~/Downloads/gate5mData --interval 5m

# 5. 手动跑一次 :30 评估（不发 Telegram）
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py

# 6. （可选）Telegram 真发测试
cp .env.example .env   # 填 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
# config/telegram.yaml → enabled: true, dry_run: false
PYTHONPATH=src python scripts/notify/test_telegram.py --live
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py --telegram
```

跑通标志：回测输出准确率约 **84%**；eval 生成 `data/live/latest_signal.json`。

---

## 二、脚本一览（按你要做的事选）

### 模块一：数据 `scripts/data/`

| 脚本 | 什么时候跑 | 命令示例 |
|------|------------|----------|
| `import_gate.py` | **首次**导入 Gate 历史 CSV | `python scripts/data/import_gate.py --dir <CSV目录> --interval 1h` |
| `sync_live_klines.py` | 实时增量同步（阶段 B，当前 API 未通） | `PYTHONPATH=src python scripts/data/sync_live_klines.py`（默认 dry-run） |
| `validate_intra_alignment.py` | 检查 5m 与 1H 是否对齐 | `PYTHONPATH=src python scripts/data/validate_intra_alignment.py` |

### 模块二：策略 `scripts/analysis/`

| 脚本 | 什么时候跑 | 命令示例 |
|------|------------|----------|
| `backtest_p1_f6.py` | **主回测**（必跑，验策略） | `PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --rebuild` |
| `backtest_p1_f6.py --all-rules` | 对比全部规则 | 同上加 `--all-rules` |
| `backtest_p1_f6_half2.py` | 后 30 分钟目标实验 | `PYTHONPATH=src python scripts/analysis/backtest_p1_f6_half2.py` |
| `analyze_1h_prediction.py` | 1H 单根预测研究 | `PYTHONPATH=src python scripts/analysis/analyze_1h_prediction.py` |
| `analyze_intra_5m.py` | 5m 微观特征研究 | `PYTHONPATH=src python scripts/analysis/analyze_intra_5m.py` |
| `build_intra_5m_features.py` | 导出特征 parquet | `PYTHONPATH=src python scripts/analysis/build_intra_5m_features.py` |

### 模块三：Telegram `scripts/notify/`

| 脚本 | 什么时候跑 | 命令示例 |
|------|------------|----------|
| `test_telegram.py --live` | **首次**验证 Bot 能收到消息 | `PYTHONPATH=src python scripts/notify/test_telegram.py --live` |
| `debug_telegram.py` | 排查 token / getMe | `PYTHONPATH=src python scripts/notify/debug_telegram.py` |
| `send_daily_heartbeat.py` | 手动发日心跳 | `PYTHONPATH=src python scripts/notify/send_daily_heartbeat.py` |

### 模块四：运行 `scripts/runtime/` + 根目录 shell

| 脚本 | 什么时候跑 | 命令示例 |
|------|------------|----------|
| `eval_p1_f6_signal.py` | **核心**：每小时 :30 评估逻辑 | `PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py --telegram --mark-sent` |
| `check_live_health.py` | 检查数据新鲜度、定时任务记录 | `PYTHONPATH=src python scripts/runtime/check_live_health.py` |
| `doctor_launchd.sh` | macOS 部署前诊断 | `./scripts/doctor_launchd.sh` |
| `install_launchd.sh` | 安装定时任务（eval + 心跳） | `./scripts/install_launchd.sh` |
| `uninstall_launchd.sh` | 卸载定时任务 | `./scripts/uninstall_launchd.sh` |
| `launchd_task.sh` | 模拟 launchd 单次执行 | `/bin/zsh -lc scripts/launchd_task.sh eval` |

---

## 三、本机自动跑（macOS launchd）

**前置**：`.env` + `config/telegram.yaml` 已配置；`data/klines/` 有数据；项目不在 Documents 目录。

```bash
./scripts/doctor_launchd.sh          # 先诊断
./scripts/install_launchd.sh         # 安装 eval(:30) + heartbeat(04:00 UTC)

launchctl list | grep bnbquant       # 确认已加载
tail -f logs/signal.log              # 看 :30 输出
```

| 定时 (UTC) | 任务 | 实际执行的脚本 |
|------------|------|----------------|
| 每小时 :30 | eval | `eval_p1_f6_signal.py --telegram --mark-sent` |
| 每天 04:00 | 心跳 | `send_daily_heartbeat.py` |
| 每 5 分钟 | sync 5m | 需 `LOAD_SYNC=1` 且 `live_sync.enabled=true` |
| 每小时 :02 | sync 1h | 同上 |

重启电脑或怀疑任务丢了：

```bash
./scripts/install_launchd.sh
```

---

## 四、开发自测

```bash
PYTHONPATH=src pytest tests/ -q
```

---

## 五、关键输出文件

| 路径 | 含义 |
|------|------|
| `data/klines/BTCUSDT_1h.parquet` | 1H K 线 |
| `data/klines/BTCUSDT_5m.parquet` | 5m K 线 |
| `data/live/latest_signal.json` | 最近一次 eval 结果 |
| `data/live/run_stats.json` | eval / sync 事件日志 |
| `logs/signal.log` | launchd eval 日志 |

---

## 六、常见问题

**`ModuleNotFoundError: bnb_quant_v2`**  
→ 命令前加 `PYTHONPATH=src`

**eval 报「数据不足 5m=0/6」**  
→ K 线太旧；阶段 B 前需手动更新 parquet，或启用 `live_sync`（API 未通前仍会失败）

**:30 没收到 Telegram**  
→ `./scripts/doctor_launchd.sh` → `./scripts/install_launchd.sh` → 看 `logs/signal.log`

---

## 七、实时数据（Gate API）

**接手指南（配置 Gate、验证、排障）** → [docs/GATE_API_SETUP.md](GATE_API_SETUP.md)

**Spot K 线为公开接口，通常不需要 API Key**；配置 Key 可提高限额。Secret 当前未用于 K 线拉取。

### 1. 配置

```bash
cp .env.example .env
# 可选填写 GATE_API_KEY / GATE_API_SECRET

# config/live_sync.yaml → enabled: true
```

### 2. 连通性测试（交接第一步）

```bash
PYTHONPATH=src python scripts/data/test_gate_api.py
```

### 3. 手动同步

```bash
# 看计划（不写盘）
PYTHONPATH=src python scripts/data/sync_live_klines.py

# 真拉取并合并 parquet
PYTHONPATH=src python scripts/data/sync_live_klines.py --interval 5m --execute
PYTHONPATH=src python scripts/data/sync_live_klines.py --interval 1h --execute

# 健康检查（5m 数据应变新）
PYTHONPATH=src python scripts/runtime/check_live_health.py
```

### 3. 挂定时任务（与 eval 联动）

```bash
LOAD_SYNC=1 ./scripts/install_launchd.sh
```

| 定时 (UTC) | 作用 |
|------------|------|
| */5 | 增量 5m |
| :02 | 增量 1h |
| :30 | eval（需当前小时已有 6 根 5m） |

eval 前自动 sync（可选）：在 launchd eval 参数加 `--sync`，或依赖上面的 5m 定时任务。

---
