# launchd 定时任务

由 `scripts/install_launchd.sh` 生成并安装到 `~/Library/LaunchAgents/`。

| Label | 频率 (UTC) | 脚本 |
|-------|------------|------|
| `com.bnbquant.eval` | 每小时 :30 | `scripts/runtime/eval_p1_f6_signal.py --telegram --mark-sent` |
| `com.bnbquant.heartbeat` | 每天 04:00 | `scripts/notify/send_daily_heartbeat.py` |
| `com.bnbquant.sync5m` | 每 5 分钟 | `scripts/data/sync_live_klines.py --interval 5m --execute` |
| `com.bnbquant.sync1h` | 每小时 :02 | `scripts/data/sync_live_klines.py --interval 1h --execute` |

默认 **不加载 sync**（`LOAD_SYNC=1` 时才加载）。详见根目录 README「本机部署」。
