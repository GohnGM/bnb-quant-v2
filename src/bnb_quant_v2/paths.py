"""项目根目录定位。

所有需要读写 ``config/``、``data/``、``.env`` 的模块应通过此处获取 repo 根路径，
避免 ``Path(__file__).parents[N]`` 因目录层级变化而失效。
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
