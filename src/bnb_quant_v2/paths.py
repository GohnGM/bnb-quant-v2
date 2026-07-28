"""项目根目录定位。

所有需要读写 ``config/``、``data/``、``.env`` 的模块应通过此处获取 repo 根路径，
避免 ``Path(__file__).parents[N]`` 因目录层级变化而失效。

优先从环境变量 BNB_QUANT_ROOT 获取，其次从当前工作目录查找，最后使用安装目录。
"""
import os
from pathlib import Path

ENV_ROOT = os.environ.get("BNB_QUANT_ROOT")
CWD = Path.cwd()

# 优先级：环境变量 > 当前目录（包含 config/data） > 安装目录
if ENV_ROOT:
    PROJECT_ROOT = Path(ENV_ROOT).resolve()
elif (CWD / "config").exists() and (CWD / "data").exists():
    PROJECT_ROOT = CWD
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
KLINE_DIR = DATA_DIR / "klines"
ANALYSIS_DIR = DATA_DIR / "analysis"
LIVE_DIR = DATA_DIR / "live"

# 配置目录
CONFIG_DIR = PROJECT_ROOT / "config"

# 日志目录
LOG_DIR = PROJECT_ROOT / "logs"
