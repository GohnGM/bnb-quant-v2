# bnb-quant-v2 运行流程

## 概述

本项目有两条主要工作流程：

1. **离线研究流程**（首次设置/规则优化）：数据导入 → 特征工程 → 回测验证
2. **实时运行流程**（日常运行）：定时同步 → 实时评估 → 信号推送

---

## 流程一：离线研究流程

### 步骤 1：导入历史数据

从 Gate.io 下载 CSV 数据后，导入到项目中：

```bash
# 导入 1H 数据
python scripts/data/import_gate.py --dir ~/Downloads/gate1hData --interval 1h

# 导入 5m 数据
python scripts/data/import_gate.py --dir ~/Downloads/gate5mData --interval 5m
```

**结果**：
- `data/klines/BTCUSDT_1h.parquet` — 1H K 线数据
- `data/klines/BTCUSDT_5m.parquet` — 5m K 线数据

### 步骤 2：构建特征工程

生成 p1×f6 特征表：

```bash
PYTHONPATH=src python scripts/analysis/build_intra_5m_features.py
```

**结果**：
- `data/analysis/BTCUSDT_1h_p1_f6_features.parquet` — 特征表
- 包含 p1_*（上一小时特征）和 f6_*（当前小时前6根5m特征）

### 步骤 3：回测验证

验证规则在历史数据上的表现：

```bash
# 默认回测主规则（最常用）
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --rebuild

# 回测所有规则
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --all-rules --rebuild

# 对比四条推送规则
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --push-rules --rebuild
```

**结果**：
- 准确率、覆盖度、信号数量等统计
- 生成 CSV 报告到 `data/analysis/` 目录

---

## 流程二：实时运行流程

### 步骤 1：配置 Telegram

编辑 `config/telegram.yaml`：

```yaml
enabled: true
dry_run: false
send_on_signal: true
send_on_error: true
send_daily_heartbeat: true
```

编辑 `.env` 文件，添加 Telegram 凭证：

```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 步骤 2：安装定时任务

```bash
# 安装基础定时任务（eval + heartbeat）
cd bnb-quant-v2
chmod +x scripts/install_launchd.sh
./scripts/install_launchd.sh

# 如需实时同步数据（阶段 B），先启用 live_sync
# 编辑 config/live_sync.yaml，设置 enabled: true
# 然后运行：LOAD_SYNC=1 ./scripts/install_launchd.sh
```

### 步骤 3：手动测试（可选）

在启动定时任务前，可以手动测试：

```bash
# 测试评估（不发送 Telegram）
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py

# 测试评估并发送 Telegram（dry-run 模式）
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py --telegram --dry-run

# 历史回放测试
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py --hour-open 2024-01-01T14:00:00+00:00
```

### 步骤 4：监控运行

```bash
# 查看定时任务状态
launchctl list | grep bnbquant

# 查看日志
tail -f logs/signal.log
tail -f logs/heartbeat.log

# 运行健康检查
PYTHONPATH=src python scripts/runtime/check_live_health.py
```

---

## 完整流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        离线研究流程（一次性）                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Gate.io CSV ──► import_gate.py ──► KlineStore (parquet)              │
│                                          │                             │
│                                          ▼                             │
│                                   build_intra_5m_features.py           │
│                                          │                             │
│                                          ▼                             │
│                                   backtest_p1_f6.py                    │
│                                          │                             │
│                                          ▼                             │
│                                   回测报告（准确率、覆盖度）            │
│                                                                        │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                        实时运行流程（持续运行）                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐               │
│  │   定时任务   │    │   实时评估   │    │   信号推送   │               │
│  │  launchd    │───►│ evaluator   │───►│ Telegram    │               │
│  │ :30 UTC     │    │             │    │             │               │
│  └─────────────┘    └─────────────┘    └─────────────┘               │
│         │                │                    │                        │
│         │                ▼                    │                        │
│         │         ┌─────────────┐             │                        │
│         │         │   去重检查   │◄────────────┘                        │
│         │         │  SignalDedup│                                      │
│         │         └─────────────┘                                      │
│         │                │                                             │
│         │                ▼                                             │
│         │         ┌─────────────┐                                      │
│         │         │  运行统计    │                                      │
│         │         │  run_stats  │                                      │
│         │         └─────────────┘                                      │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────┐                                                       │
│  │  日心跳     │                                                       │
│  │ 04:00 UTC   │                                                       │
│  └─────────────┘                                                       │
│                                                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 命令速查表

| 用途 | 命令 |
|------|------|
| 导入 1H 数据 | `python scripts/data/import_gate.py --dir ~/Downloads/gate1hData --interval 1h` |
| 导入 5m 数据 | `python scripts/data/import_gate.py --dir ~/Downloads/gate5mData --interval 5m` |
| 构建特征 | `PYTHONPATH=src python scripts/analysis/build_intra_5m_features.py` |
| 回测主规则 | `PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --rebuild` |
| 回测所有规则 | `PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --all-rules --rebuild` |
| 手动评估 | `PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py` |
| 测试推送 | `PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py --telegram --dry-run` |
| 安装定时任务 | `./scripts/install_launchd.sh` |
| 查看日志 | `tail -f logs/signal.log` |
| 健康检查 | `PYTHONPATH=src python scripts/runtime/check_live_health.py` |

---

## 数据文件位置

| 数据类型 | 路径 |
|----------|------|
| 1H K 线 | `data/klines/BTCUSDT_1h.parquet` |
| 5m K 线 | `data/klines/BTCUSDT_5m.parquet` |
| 特征表 | `data/analysis/BTCUSDT_1h_p1_f6_features.parquet` |
| 回测报告 | `data/analysis/p1_f6_hour_backtest_summary.csv` |
| 推送规则对比 | `data/analysis/p1_f6_push_rules_compare.csv` |
| 信号记录 | `data/analysis/p1_f6_hour_signals.csv` |
| 运行时状态 | `data/live/latest_signal.json` |
| 去重状态 | `data/live/signal_state.json` |

---

## 常见问题

### Q1：如何更新历史数据？

重新导入即可，`import_gate.py` 会合并新数据：

```bash
python scripts/data/import_gate.py --dir ~/Downloads/gate1hData --interval 1h
python scripts/data/import_gate.py --dir ~/Downloads/gate5mData --interval 5m
PYTHONPATH=src python scripts/analysis/build_intra_5m_features.py
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --rebuild
```

### Q2：如何添加新规则？

在 `src/bnb_quant_v2/strategy/p1f6_rules.py` 中添加新规则类：

```python
@register(
    name="你的规则名称",
    tier="primary",  # primary/strict/primary_short/strict_short/other/half2
    risk="medium",   # low/medium/high
    description="规则描述",
)
class YourRule(BaseRule):
    def evaluate(self, row: pd.Series) -> int:
        if row["特征1"] == "条件1" and row["特征2"] >= 阈值:
            return 1  # 涨
        return 0
```

然后运行回测验证：

```bash
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --all-rules --rebuild
```

### Q3：如何关闭 Telegram 推送？

编辑 `config/telegram.yaml`：

```yaml
enabled: false
```

或者运行时使用 `--dry-run` 参数：

```bash
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py --telegram --dry-run
```

### Q4：如何检查数据质量？

```bash
PYTHONPATH=src python scripts/data/validate_intra_alignment.py
```

---

## 开发阶段状态

| 阶段 | 名称 | 状态 | 说明 |
|------|------|------|------|
| A | 基础数据 | ✅ 完成 | Gate CSV 导入、KlineStore、质量审计 |
| B | 实时同步 | ⏳ 待启用 | Gate REST API 增量同步 |
| C | 特征工程 | ✅ 完成 | p1×f6 特征表、5m 对齐校验 |
| D | Telegram | ✅ 完成 | 配置、消息模板、Bot API、日心跳 |
| E | 部署运行 | ✅ 完成 | launchd 定时任务、健康检查 |
| F | Binance 备选 | ⏳ 未实现 | Binance REST K 线 |
