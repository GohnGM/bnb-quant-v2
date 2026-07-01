# bnb-quant-v2 项目深度分析

## 1. 项目概述

### 1.1 基本信息

| 属性 | 内容 |
|------|------|
| **项目名称** | bnb-quant-v2 |
| **版本** | 0.1.0 |
| **核心功能** | BTC p1×f6 量化信号系统 |
| **交易对** | BTCUSDT |
| **数据源** | Gate.io（REST API + CSV） |
| **信号推送** | Telegram Bot |
| **部署方式** | macOS launchd / cron |

### 1.2 项目定位

本项目是一个**短线量化交易信号生成系统**，核心目标是基于历史数据和实时数据，在每小时 **:30 UTC** 时刻生成 BTCUSDT 的交易方向预测信号，并通过 Telegram 推送。

### 1.3 设计理念

- **规则单一来源**：回测与实盘共用同一规则定义，避免策略漂移
- **数据质量优先**：导入时自动运行质量审计
- **环境隔离**：使用 `.venv` + `.env` 管理依赖和凭证
- **阶段化开发**：明确标记各功能的开发阶段

---

## 2. 架构设计

### 2.1 四模块架构

```
┌─────────────────────────────────────────────────────────────┐
│                     bnb-quant-v2                            │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│   Module 1  │   Module 2  │   Module 3  │      Module 4     │
│    Data     │  Analysis   │   Notify    │     Runtime       │
│  获取数据   │  分析策略   │  Telegram   │    保持运行       │
├─────────────┼─────────────┼─────────────┼───────────────────┤
│ Gate CSV    │ 特征工程    │ 配置管理    │ 流水线编排        │
│ REST API    │ 规则回测    │ 消息模板    │ 信号去重          │
│ K线存储     │ 实时评估    │ Bot API     │ 运行统计          │
│ 质量审计    │ :30信号判定 │             │ 健康检查          │
└─────────────┴─────────────┴─────────────┴───────────────────┘
```

### 2.2 模块职责表

| 模块 | 包路径 | 脚本目录 | 核心文件 | 职责 |
|------|--------|----------|----------|------|
| **一、获取数据** | `bnb_quant_v2.data` | `scripts/data/` | [importers.py](src/bnb_quant_v2/data/importers.py), [kline_store.py](src/bnb_quant_v2/data/kline_store.py), [gate_rest.py](src/bnb_quant_v2/data/live/gate_rest.py) | Gate CSV 导入、K 线存储、质量审计、实时同步 |
| **二、分析策略** | `bnb_quant_v2.analysis` | `scripts/analysis/` | [intra_5m.py](src/bnb_quant_v2/analysis/intra_5m.py), [backtest_p1_f6.py](src/bnb_quant_v2/analysis/backtest_p1_f6.py), [evaluator.py](src/bnb_quant_v2/analysis/evaluator.py) | 特征工程、回测、规则评估、:30 信号判定 |
| **三、Telegram** | `bnb_quant_v2.notify` | `scripts/notify/` | [config.py](src/bnb_quant_v2/notify/config.py), [format.py](src/bnb_quant_v2/notify/format.py), [telegram.py](src/bnb_quant_v2/notify/telegram.py) | 配置、消息模板、Bot API |
| **四、保持运行** | `bnb_quant_v2.runtime` | `scripts/runtime/` | [pipeline.py](src/bnb_quant_v2/runtime/pipeline.py), [dedup.py](src/bnb_quant_v2/runtime/dedup.py), [run_stats.py](src/bnb_quant_v2/runtime/run_stats.py) | 流水线编排、去重、运行统计、健康检查 |

---

## 3. 核心策略：p1×f6

### 3.1 策略原理

```
时间线（第 t 根 1H）:
┌─────────────────────────────────────────────────────────────────┐
│  第 t-1 根 1H（已收盘）                    │  第 t 根 1H（进行中）  │
│  ┌──────────────────────────────────────┐  │  ┌─────────────────┐ │
│  │  00:00  05:00  10:00  ...  55:00    │  │  │ 00  05  10  ... │ │
│  │  m5(1)  m5(2)  m5(3)  ...  m5(12)   │  │  │ 1   2   3   ... │ │
│  │                                      │  │  │                 │ │
│  │       p1 特征（上一根 1H + 12 根 5m） │  │  │ f6 特征         │ │
│  │       p1_candle_type, p1_yin,        │  │  │ f6_yang_cnt,    │ │
│  │       p1_m5_yang_cnt, p1_body_pct... │  │  │ f6_close_strength│ │
│  └──────────────────────────────────────┘  │  │ f6_ret_sum...   │ │
│                                            │  │                 │ │
│                                            │  │ 信号评估时点:30  │ │
│                                            │  │ （第 6 根 5m 后）│ │
│                                            │  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 核心概念

| 概念 | 定义 | 说明 |
|------|------|------|
| **p1** | 上一根 1H（t-1）及其 12 根 5m 特征 | 前缀 `p1_*`，如 `p1_candle_type`, `p1_yang_cnt` |
| **f6** | 当前 1H（t）前 6 根 5m | 前缀 `f6_*`，如 `f6_yang_cnt`, `f6_close_strength` |
| **hour_up** | 当前整根 1H 收阳（close > open） | 默认预测目标 |
| **half2_up** | 当前 1H 后 30 分钟收阳 | 实验用，非默认 |
| **EXPECTED_M5_PER_HOUR** | 12 | 每小时应有 12 根 5m |
| **F6_BARS** | 6 | 信号在第 30 分钟评估（前 6 根 5m） |

### 3.3 推送规则

#### 主规则（PRIMARY）

| 规则名 | 条件 | 预测方向 | 回测准确率 | 月信号量 |
|--------|------|----------|------------|----------|
| `PRIMARY_HOUR_RULE` | p1大阴 & f6阳≥4 & f6收盘强≥67% | 涨（+1） | ~84% | ~30笔 |
| `PRIMARY_HOUR_SHORT_RULE` | p1大阳 & f6阴≥4 & f6收盘弱≤33% | 跌（-1） | ~83% | ~31笔 |

#### 严格规则（STRICT）

| 规则名 | 条件 | 预测方向 | 回测准确率 | 覆盖率 |
|--------|------|----------|------------|--------|
| `STRICT_HOUR_RULE` | p1大阴 & f6阳≥4 & f6涨>0.2% & f6收盘强 | 涨（+1） | ~91.5% | ~2.4% |
| `STRICT_HOUR_SHORT_RULE` | p1大阳 & f6阴≥4 & f6跌>0.2% & f6收盘弱 | 跌（-1） | ~92% | ~16笔/月 |

### 3.4 规则定义位置

所有规则定义集中在 [backtest_p1_f6.py](src/bnb_quant_v2/analysis/backtest_p1_f6.py)，通过 `build_p1_f6_hour_predictions()` 函数实现。实时评估 [evaluator.py](src/bnb_quant_v2/analysis/evaluator.py) 复用同一函数，确保回测与实盘一致性。

---

## 4. 数据流程

### 4.1 离线流程（研究阶段）

```
Gate CSV → import_gate.py → KlineStore (parquet) → build_intra_5m_features.py → backtest_p1_f6.py
    ↓                           ↓                                ↓                      ↓
  扫描目录                    写入 parquet                    生成 p1×f6 特征表       回测分析
```

### 4.2 实时流程（运行阶段）

```
Gate API → sync_live_klines.py → KlineStore → eval_p1_f6_signal.py → Telegram
              ↑                                ↑                         ↑
         (每5分钟)                       (:30评估)                  (推送信号)
```

### 4.3 数据存储规范

**Parquet 文件结构**：

- **路径**: `data/klines/{symbol}_{interval}.parquet`
- **标准列**: `open_time, open, high, low, close, volume, closed`
- **时间**: 统一 UTC timezone-aware

**核心存储类 [KlineStore](src/bnb_quant_v2/data/kline_store.py)**：

| 方法 | 功能 |
|------|------|
| `load()` | 加载并按 `open_time` 升序返回 |
| `save_dataframe()` | 覆盖写入（全量替换） |
| `merge_append()` | 增量合并（按 `open_time` 去重） |

---

## 5. 目录结构详解

```
bnb-quant-v2/
├── config/                    # 配置文件（YAML）
│   ├── live_sync.yaml         # 实时同步配置
│   ├── settings.yaml          # 全局设置（symbol, kline_dir）
│   └── telegram.yaml          # Telegram 通知配置
├── data/                      # 数据目录（gitignore 部分）
│   ├── analysis/              # 分析结果（CSV/Parquet）
│   ├── klines/                # K 线存储（Parquet）
│   └── live/                  # 运行时状态（JSON，已排除）
├── deploy/                    # 部署脚本
│   └── launchd/               # macOS launchd 配置
├── docs/                      # 项目文档
│   ├── GATE_API_SETUP.md      # Gate API 交接配置
│   ├── RUN.md                 # 运行指南
│   ├── plan_intra_5m.md       # 5m 特征工程计划
│   ├── plan_live_data.md      # 实时数据计划
│   └── plan_live_telegram.md  # Telegram 推送计划
├── logs/                      # 日志文件
├── scripts/                   # 运行脚本（按模块分组）
│   ├── analysis/              # 分析脚本
│   ├── data/                  # 数据脚本
│   ├── notify/                # 通知脚本
│   └── runtime/               # 运行时脚本
├── src/bnb_quant_v2/          # 核心源码（包结构）
│   ├── analysis/              # 分析模块
│   ├── data/                  # 数据模块
│   │   └── live/              # 实时同步子模块
│   ├── notify/                # 通知模块
│   ├── runtime/               # 运行时模块
│   ├── signal/                # 兼容层（新代码用 analysis + runtime）
│   └── paths.py               # 路径工具
├── tests/                     # 测试用例（9个测试文件）
├── .env                       # 环境变量（敏感信息，gitignore）
├── .env.example               # 环境变量示例
├── .gitignore                 # Git 忽略规则
├── pyproject.toml             # 项目配置（依赖、构建）
└── README.md                  # 项目说明
```

---

## 6. 模块详细分析

### 6.1 数据模块（Data）

#### 6.1.1 导入与规范化

**[importers.py](src/bnb_quant_v2/data/importers.py)** 负责 Gate CSV 的导入和规范化：

- **Gate CSV 列顺序**: `timestamp, volume, close, high, low, open`（官方标准）
- **规范化输出**: `open_time, open, high, low, close, volume, closed`（全部 UTC）
- **自动识别**: 支持秒/毫秒时间戳或 ISO 字符串

#### 6.1.2 实时同步

**[live/](src/bnb_quant_v2/data/live/)** 子模块实现实时 K 线增量同步：

| 文件 | 功能 |
|------|------|
| [config.py](src/bnb_quant_v2/data/live/config.py) | 加载 `live_sync.yaml` 配置 |
| [fetcher.py](src/bnb_quant_v2/data/live/fetcher.py) | 交易所 K 线拉取器抽象（GateFetcher、StubFetcher） |
| [gate_rest.py](src/bnb_quant_v2/data/live/gate_rest.py) | Gate.io REST v4 API 实现 |
| [scheduler.py](src/bnb_quant_v2/data/live/scheduler.py) | 同步调度（build_sync_plan → fetch → merge_append） |

#### 6.1.3 质量审计

**[quality.py](src/bnb_quant_v2/data/quality.py)** 提供 K 线质量检查：

- 时间间隔一致性检查
- OHLC 合理性验证
- 数据完整性报告

### 6.2 分析模块（Analysis）

#### 6.2.1 特征工程

**[intra_5m.py](src/bnb_quant_v2/analysis/intra_5m.py)** 实现核心特征工程：

| 函数 | 功能 |
|------|------|
| `compute_intra_features()` | 单个小时桶内 5m K 线的微观结构特征 |
| `compute_first6_features()` | 当前 1H 前 6 根 5m 的特征（f6_*） |
| `compute_half2_features()` | 当前 1H 后 6 根 5m 的标签（half2_*） |
| `enrich_p1_f6()` | 构建 p1×f6 特征表（回测用） |
| `validate_hour_alignment()` | 校验 5m 聚合 OHLC 与 1H 是否一致（>99% 验收标准） |

**p1 特征列（P1_SHIFT_COLS）**:
- `yin`, `yang`, `body_pct`, `candle_type`
- `m5_yang_cnt`, `m5_yin_cnt`, `m5_ret_sum`
- `m5_first_half_ret`, `m5_second_half_ret`
- `m5_pattern_last3`, `m5_last2_yang`, `m5_close_strength`, `m5_recovery`

**f6 特征列**:
- `f6_yang_cnt`, `f6_yin_cnt`, `f6_ret_sum`
- `f6_all_yang`, `f6_all_yin`, `f6_last2_yang`
- `f6_close_strength`, `f6_range_hl`, `f6_pattern`

#### 6.2.2 回测

**[backtest_p1_f6.py](src/bnb_quant_v2/analysis/backtest_p1_f6.py)** 实现回测逻辑：

| 函数 | 功能 |
|------|------|
| `build_p1_f6_hour_predictions()` | 构建所有 p1×f6 规则的预测 |
| `run_p1_f6_backtest()` | 执行单条或全部规则回测 |
| `compare_push_rules_backtest()` | 四条推送规则并排回测 |
| `run_primary_hour_backtest()` | 默认主规则回测 + 按年/按月统计 |

**回测报告结构（P1F6BacktestReport）**:
- rule_name, target_col, baseline_up_rate
- total_bars, signals, correct, wrong
- accuracy, coverage_pct
- predict_up, predict_down, vs_baseline_pp
- signals_detail（每笔信号详情）

#### 6.2.3 实时评估

**[evaluator.py](src/bnb_quant_v2/analysis/evaluator.py)** 实现 :30 实时评估：

| 函数 | 功能 |
|------|------|
| `evaluate_from_store()` | 从 KlineStore 加载 1h/5m 并评估（主入口） |
| `evaluate_live_at()` | 评估指定时刻对应小时的四条推送规则 |
| `build_live_p1_f6_row()` | 构建实时评估行（当前小时 ≥6 根 5m + 前一小时完整 12 根 5m） |
| `validate_against_enriched()` | 验证实时行与回测行预测一致性 |

**数据要求**:
- 当前小时已有 ≥6 根 5m（f6）
- 上一小时有完整 12 根 5m（p1）
- 不足时 `EvalResult.ready=False`，流水线会发告警

### 6.3 通知模块（Notify）

#### 6.3.1 配置管理

**[config.py](src/bnb_quant_v2/notify/config.py)** 加载 Telegram 配置：

- 合并 `.env` 与 `telegram.yaml`
- 凭证通过环境变量传递，不写入 YAML
- 真发条件：`enabled=true`, `dry_run=false`, `bot_token`, `chat_id` 非空

#### 6.3.2 消息模板

**[format.py](src/bnb_quant_v2/notify/format.py)** 定义三种消息类型：

| 函数 | 用途 | 示例场景 |
|------|------|----------|
| `format_signal_message()` | 规则触发信号 | 主规则做多触发 |
| `format_alert_message()` | 运维告警 | 数据不足、sync 失败 |
| `format_heartbeat_message()` | 日心跳 | 每日 04:00 UTC 汇总 |

**双时区支持**: UTC / 北京时间（Asia/Shanghai）

#### 6.3.3 Bot API

**[telegram.py](src/bnb_quant_v2/notify/telegram.py)** 封装 Telegram Bot API：

- 使用 stdlib `urllib`，无第三方依赖
- `dry_run=True` 时返回模拟结果，不调用 API
- 支持 `SendResult` 返回发送状态

### 6.4 运行时模块（Runtime）

#### 6.4.1 流水线编排

**[pipeline.py](src/bnb_quant_v2/runtime/pipeline.py)** 是 launchd :30 任务的核心：

```
run_eval_pipeline()
    ↓
1. run_pre_eval_sync()      — eval 前拉取最新 5m（可选）
    ↓
2. evaluate_from_store()    — 模块二判定主/严格规则
    ↓
3. SignalDedup              — 过滤已推送的 (hour, rule)
    ↓
4. run_notify_step()        — 发信号 / 数据不足告警（可选）
```

#### 6.4.2 信号去重

**[dedup.py](src/bnb_quant_v2/runtime/dedup.py)** 防止重复推送：

- 持久化路径: `data/live/signal_state.json`
- 键为 `hour_open_time`（ISO），值为已推送的规则名列表
- 同一 (小时, 规则) 在 launchd 重试或手动重跑时不会二次推送

#### 6.4.3 运行统计

**[run_stats.py](src/bnb_quant_v2/runtime/run_stats.py)** 记录运行状态：

- 记录 sync / eval / signal 事件
- 供健康检查脚本使用
- 供日心跳统计使用

---

## 7. 配置文件说明

### 7.1 settings.yaml

```yaml
symbol: BTCUSDT           # 交易对
kline_dir: data/klines    # K 线存储目录
```

### 7.2 live_sync.yaml

```yaml
symbol: BTCUSDT           # 交易对
intervals:                # 同步周期
  - 5m
  - 1h
source: gate              # gate | binance
enabled: false            # 阶段 B 前保持 false
lookback_bars:            # 增量回溯根数
  5m: 24
  1h: 3
store_dir: data/klines    # 存储目录
```

### 7.3 telegram.yaml

```yaml
enabled: true             # 是否启用 Telegram
dry_run: false            # 是否模拟推送
parse_mode: ""            # 消息格式（空为纯文本）
send_on_signal: true      # 规则触发时发送信号
send_on_error: true       # 错误时发送告警
send_daily_heartbeat: true # 发送每日心跳
heartbeat_cron_utc: "0 4 * * *"  # 心跳时间（UTC 04:00 = 北京 12:00）
```

### 7.4 .env

```bash
# Gate API（公开 K 线通常无需密钥）
GATE_API_KEY=
GATE_API_SECRET=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Binance（备选，阶段 F）
# BINANCE_API_KEY=
# BINANCE_API_SECRET=
# BINANCE_TESTNET=true
```

---

## 8. 定时任务（macOS launchd）

### 8.1 任务清单

| 任务 | 时间（UTC） | 脚本 | 说明 |
|------|-------------|------|------|
| eval | 每小时 :30 | `scripts/runtime/eval_p1_f6_signal.py` | p1×f6 主/严格规则 → Telegram |
| heartbeat | 每天 04:00 | `scripts/notify/send_daily_heartbeat.py` | 日心跳（12:00 北京时间） |
| sync 5m | 每 5 分钟 | `scripts/data/sync_live_klines.py --interval 5m` | 需 `LOAD_SYNC=1` + live_sync 启用 |
| sync 1h | 每小时 :02 | `scripts/data/sync_live_klines.py --interval 1h` | 同上 |

### 8.2 安装方式

```bash
cd bnb-quant-v2
chmod +x scripts/install_launchd.sh scripts/uninstall_launchd.sh
./scripts/install_launchd.sh
```

启用 sync 任务：
```bash
LOAD_SYNC=1 ./scripts/install_launchd.sh
```

### 8.3 健康检查

```bash
# 查看任务状态
launchctl list | grep bnbquant

# 查看日志
tail -f logs/signal.log
tail -f logs/heartbeat.log

# 运行健康检查脚本
PYTHONPATH=src python scripts/runtime/check_live_health.py
```

---

## 9. 开发阶段说明

### 9.1 阶段定义

| 阶段 | 名称 | 状态 | 内容 |
|------|------|------|------|
| A | 基础数据 | ✅ 完成 | Gate CSV 导入、KlineStore、质量审计 |
| B | 实时同步 | ⏳ 待启用 | Gate REST API 增量同步（enabled=false） |
| C | 特征工程 | ✅ 完成 | p1×f6 特征表、5m 对齐校验 |
| D | Telegram | ✅ 完成 | 配置、消息模板、Bot API、日心跳 |
| E | 部署运行 | ✅ 完成 | launchd 定时任务、健康检查 |
| F | Binance 备选 | ⏳ 未实现 | Binance REST K 线（StubFetcher） |

### 9.2 当前状态

1. **实时同步**: `config/live_sync.yaml` 中 `enabled: false`，阶段 B 尚未启用
2. **Telegram**: `config/telegram.yaml` 中 `enabled: true`、`dry_run: false`，已配置为真实推送
3. **数据**: `data/klines/` 已有 `BTCUSDT_1h.parquet` 和 `BTCUSDT_5m.parquet`
4. **测试**: 项目包含完整测试用例，位于 `tests/` 目录

---

## 10. 关键命令参考

### 10.1 数据导入

```bash
python scripts/data/import_gate.py --dir ~/Downloads/gate1hData --interval 1h
```

### 10.2 回测

```bash
PYTHONPATH=src python scripts/analysis/backtest_p1_f6.py --rebuild
```

### 10.3 实时评估

```bash
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py
```

### 10.4 健康检查

```bash
PYTHONPATH=src python scripts/runtime/check_live_health.py
```

### 10.5 测试

```bash
PYTHONPATH=src pytest tests/ -v
```

---

## 11. 技术栈

| 分类 | 库/工具 | 版本 | 用途 |
|------|---------|------|------|
| 核心数据 | pandas | ≥2.0 | 数据处理、特征工程 |
| 数值计算 | numpy | ≥1.26 | 数值运算 |
| 列式存储 | pyarrow | ≥15.0 | Parquet 读写 |
| 日志 | loguru | ≥0.7 | 结构化日志 |
| 配置 | pyyaml | ≥6.0 | YAML 配置加载 |
| 测试 | pytest | ≥8.0 | 单元测试 |
| 部署 | launchd | macOS 内置 | 定时任务 |
| 通知 | Telegram Bot API | REST | 消息推送 |

---

## 12. 维护建议

### 12.1 代码维护

1. **规则更新**: 修改 `build_p1_f6_hour_predictions()` 后需同步更新回测和评估逻辑
2. **特征添加**: 在 `intra_5m.py` 中添加新特征后，需更新 `P1_SHIFT_COLS`
3. **配置变更**: 修改 `config/` 目录下的 YAML 文件后，需验证所有相关脚本

### 12.2 数据维护

1. **定期审计**: 运行 `audit_klines()` 检查数据质量
2. **备份策略**: 定期备份 `data/klines/` 目录
3. **历史数据**: 定期导入 Gate CSV 补充历史数据

### 12.3 运行维护

1. **日志监控**: 定期查看 `logs/` 目录下的日志文件
2. **健康检查**: 定期运行 `check_live_health.py`
3. **告警响应**: 及时处理 Telegram 推送的告警信息

---

**文档版本**: v0.1.0  
**最后更新**: 2025-07-01  
**维护者**: GohnGM