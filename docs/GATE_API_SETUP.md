# Gate API 配置指南（接手指南）

本文给**接手项目的同事**：从零配置 Gate 实时 K 线拉取，直到 `eval` 不再报「5m=0/6」。

---

## 1. 先搞清楚：要不要 API Key？

| 接口 | 是否必须 Key | 说明 |
|------|--------------|------|
| `GET /api/v4/spot/candlesticks` | **通常不需要** | 公开行情，本项目 K 线同步用这个 |
| 下单、账户等私有接口 | 必须 | 本项目**未使用** |

因此：

- **能访问 `api.gateio.ws` 的网络** → 往往**不配 Key 也能拉 K 线**
- **被墙 / 公司网络限制** → 需要代理或换网络；Key 解决不了网络问题
- **频繁拉取被限流** → 在 Gate 后台创建 API Key 填到 `.env`，可提高限额

代码读取环境变量：

```bash
GATE_API_KEY=...
GATE_API_SECRET=...   # K 线拉取暂不需要签名，预留后续扩展
```

---

## 2. 在 Gate 后台创建 API Key（可选）

1. 登录 [Gate.io](https://www.gate.io) → **API 管理**
2. 创建 **API v4 Key**
3. 权限：实时 K 线只需**读取**；**不要**开提现、交易（本项目不需要）
4. 记下 **Key** 和 **Secret**，填入项目 `.env`

---

## 3. 项目内配置（必做 2 处）

### 3.1 复制环境变量文件

```bash
cd bnb-quant-v2
cp .env.example .env
```

编辑 `.env`（Key 可选，网络通可先留空）：

```bash
# 可选；公开 K 线可不填
GATE_API_KEY=你的Key
GATE_API_SECRET=你的Secret
```

### 3.2 打开实时同步开关

编辑 `config/live_sync.yaml`：

```yaml
symbol: BTCUSDT
intervals:
  - 5m
  - 1h
source: gate
enabled: true          # ← 必须为 true
lookback_bars:
  5m: 24
  1h: 3
store_dir: data/klines
```

---

## 4. 验证步骤（按顺序执行）

### 步骤 A：Python 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas pyyaml numpy pyarrow loguru
```

### 步骤 B：Gate 网络连通性（最重要）

```bash
PYTHONPATH=src python scripts/data/test_gate_api.py
```

期望输出包含：

```
✓ Gate API 可达，返回 N 根 5m K 线
  最新: 2026-xx-xx ... close=xxxxx
```

若失败，常见原因：

| 报错 | 处理 |
|------|------|
| `网络错误` / `timed out` | 检查代理、防火墙、能否 `curl api.gateio.ws` |
| `HTTP 403/429` | 换 IP 或配置 `GATE_API_KEY` |
| `响应异常` | 检查 Gate 是否维护、交易对是否为 `BTC_USDT` |

也可用 curl 自测（无需 Key）：

```bash
curl -s "https://api.gateio.ws/api/v4/spot/candlesticks?currency_pair=BTC_USDT&interval=5m&limit=3"
```

应返回 JSON 数组。

### 步骤 C：增量同步写入 parquet

```bash
# 先 dry-run 看计划
PYTHONPATH=src python scripts/data/sync_live_klines.py

# 真写入（merge_append，不覆盖历史）
PYTHONPATH=src python scripts/data/sync_live_klines.py --interval 5m --execute
PYTHONPATH=src python scripts/data/sync_live_klines.py --interval 1h --execute
```

成功时应看到类似：

```
[LIVE] BTCUSDT 5m via gate | lookback=24 since=... → data/klines/BTCUSDT_5m.parquet
  → 拉取 XX 行，合并后共 XXXXX 行 → ...
```

### 步骤 D：健康检查

```bash
PYTHONPATH=src python scripts/runtime/check_live_health.py
```

`5m` 的 `age` 应在 **15 分钟以内**（若刚 sync 过）。

### 步骤 E：手动跑一次 eval

```bash
PYTHONPATH=src python scripts/runtime/eval_p1_f6_signal.py
```

不应再出现 `5m=0/6`（当前小时有数据时）。

---

## 5. 挂定时任务（本机长期跑）

```bash
./scripts/doctor_launchd.sh
./scripts/install_launchd.sh              # eval + heartbeat
LOAD_SYNC=1 ./scripts/install_launchd.sh  # 再加 sync 5m / 1h
```

| 任务 (UTC) | 作用 |
|------------|------|
| 每 5 分钟 | 增量 5m |
| 每小时 :02 | 增量 1h |
| 每小时 :30 | eval → Telegram |

**防睡眠**（否则 :30 会晚 10+ 分钟触发）：

```bash
caffeinate -dims &
```

---

## 6. 数据与策略的关系

- sync 使用 **`merge_append`**：在原有 parquet 上**追加合并**，按 `open_time` 去重
- **不会删除**离线导入的历史 K 线
- 仅重叠的 lookback 窗口（5m 约 24 根）可能被 API 新值覆盖
- 策略回测主体不变；实时 eval 依赖**最新 5m**

---

## 7. 交接清单（Checklist）

接手人逐项打勾：

- [ ] `.venv` 已创建，依赖已安装
- [ ] `cp .env.example .env`（Key 按需填写）
- [ ] `config/live_sync.yaml` → `enabled: true`
- [ ] `test_gate_api.py` 通过
- [ ] `sync_live_klines.py --execute` 5m + 1h 成功
- [ ] `check_live_health.py` 5m 数据新鲜
- [ ] `eval_p1_f6_signal.py` 无 `5m=0/6`
- [ ] （可选）Telegram `.env` + `config/telegram.yaml` 已配置
- [ ] （可选）`LOAD_SYNC=1 ./scripts/install_launchd.sh` 已安装
- [ ] 本机防睡眠或接电源

---

## 8. 相关代码位置

| 文件 | 作用 |
|------|------|
| `src/bnb_quant_v2/data/live/gate_rest.py` | Gate HTTP 请求与解析 |
| `src/bnb_quant_v2/data/live/fetcher.py` | `GateFetcher` |
| `src/bnb_quant_v2/data/live/scheduler.py` | sync 编排、`merge_append` |
| `src/bnb_quant_v2/data/kline_store.py` | parquet 读写 |
| `scripts/data/sync_live_klines.py` | 同步 CLI |
| `scripts/data/test_gate_api.py` | 连通性测试 |

更完整的运行说明见 [RUN.md](RUN.md)。
