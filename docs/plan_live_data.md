# 实时 K 线同步 — 计划任务（暂未接入交易所）

## 1. 背景

当前策略（p1×f6 → 整根 1H）依赖：

- `BTCUSDT_1h.parquet` — 1H K 线
- `BTCUSDT_5m.parquet` — 5m K 线（:30 信号需前 6 根 5m）

**现状**：本机暂无法访问交易所 API，历史数据仍通过 Gate CSV 离线导入。  
**目标**：预留「定时拉取 → 增量合并 → 触发信号」流水线，待网络/API 可用后启用。

---

## 2. 非目标（本阶段）

- 不实现真实 HTTP/WebSocket 请求
- 不做实盘下单
- 不替换现有 `import_gate.py` 离线流程

---

## 3. 架构（拟定）

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  cron / launchd │────▶│ sync_live_klines │────▶│  KlineStore     │
│  (计划任务)      │     │  (scripts/)       │     │  data/klines/   │
└─────────────────┘     └────────┬─────────┘     └────────┬────────┘
                                 │                          │
                                 ▼                          ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │ live.fetcher     │     │ enrich_p1_f6    │
                        │ Gate / Binance   │     │ 信号评估 (:30)   │
                        └──────────────────┘     └─────────────────┘
```

| 模块 | 路径 | 职责 |
|------|------|------|
| 配置 | `data/live/config.py` | symbol、interval、数据源、增量窗口 |
| 拉取器 | `data/live/fetcher.py` | 交易所接口（当前 Stub） |
| 调度 | `data/live/scheduler.py` | 单次同步编排、日志 |
| CLI | `scripts/sync_live_klines.py` | 手动/计划任务入口 |
| 存储 | `data/kline_store.py` | 读写的 parquet（已有） |

---

## 4. 计划任务频率

| 任务 | 建议 cron | 说明 |
|------|-----------|------|
| **5m 增量** | `*/5 * * * *` | 每 5 分钟拉最近 N 根，合并到 `BTCUSDT_5m.parquet` |
| **1H 增量** | `2 * * * *` | 每小时第 2 分钟拉上一根已收盘 1H |
| **:30 信号检查** | `30 * * * *` | 整点后 30 分跑 p1×f6 主规则（可选，依赖 5m 已更新） |

时区：**UTC**（与 Gate 导入、回测一致）。

示例 crontab（启用真实拉取后）：

```cron
# 5m K 线
*/5 * * * * cd /path/to/bnb-quant-v2 && PYTHONPATH=src .venv/bin/python scripts/sync_live_klines.py --interval 5m >> logs/sync_5m.log 2>&1

# 1H K 线
2 * * * * cd /path/to/bnb-quant-v2 && PYTHONPATH=src .venv/bin/python scripts/sync_live_klines.py --interval 1h >> logs/sync_1h.log 2>&1

# :30 信号（仅评估，不下单）
30 * * * * cd /path/to/bnb-quant-v2 && PYTHONPATH=src .venv/bin/python scripts/eval_p1_f6_signal.py >> logs/signal.log 2>&1
```

macOS 可用 `launchd` plist，结构同上。

---

## 5. 分阶段实施

### 阶段 A：占位与计划（当前）✅

- [x] `live/` 模块 Stub + `LiveDataUnavailableError`
- [x] `sync_live_klines.py --dry-run` 打印将执行的操作
- [x] 本文档

### 阶段 B：Gate REST 增量拉取

- [ ] 实现 `GateFetcher.fetch_klines(since, limit)`
- [ ] `KlineStore.merge_append()` — 按 `open_time` 去重合并
- [ ] 拉取后跑 `audit_klines` 门禁
- [ ] 环境变量：`GATE_API_KEY`（公开 K 线可不需要）

Gate 参考：`GET /api/v4/spot/candlesticks`  
参数：`currency_pair=BTC_USDT`, `interval=5m|1h`, `from`, `to`

### 阶段 C：:30 实时信号

- [ ] `scripts/eval_p1_f6_signal.py` — 用最新 parquet 判断当前小时是否触发主规则
- [ ] 输出 JSON/日志：入场时间、价格、预测方向（与回测 CSV 同结构）
- [ ] 可选：写入 `data/live/latest_signal.json`

### 阶段 D：Binance 备选 / WebSocket

- [ ] 复用 bnb-quant `BinanceFuturesClient` 思路或 CCXT
- [ ] 5m WebSocket 降低延迟

---

## 6. 配置（拟定）

`config/live_sync.yaml`（阶段 B 启用）：

```yaml
symbol: BTCUSDT
intervals: [5m, 1h]
source: gate  # gate | binance
lookback_bars:
  5m: 24      # 每次多拉几根防漏
  1h: 3
store_dir: data/klines
```

环境变量见 `.env.example`。

---

## 7. 与现有流程关系

| 场景 | 命令 |
|------|------|
| 离线全量/补历史 | `scripts/import_gate.py` |
| 计划增量（未来） | `scripts/sync_live_klines.py` |
| 回测/研究 | `scripts/backtest_p1_f6.py`（读 parquet） |

离线导入与实时增量**共用** `KlineStore` 路径，避免双份数据。

---

## 8. 验收标准（阶段 B 完成后）

1. `--dry-run` 与真实模式输出 interval/symbol/时间范围一致  
2. 连续跑 24h 5m 任务，`m5_count==12` 的小时不减少  
3. :30 信号脚本能在最后一根 5m 闭合后 1 分钟内给出结果  

---

*文档版本：v1 · 状态：阶段 A 完成，待交易所可访问后进入阶段 B*

**后续**：实时信号 + Telegram 见 [plan_live_telegram.md](plan_live_telegram.md)。
