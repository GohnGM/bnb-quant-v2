"""命令行界面模块。

提供统一的 bnbquant 命令，包含数据管理、回测、信号评估、通知、系统管理等子命令。
"""
from __future__ import annotations

from bnb_quant_v2.cli.main import app, console

__all__ = ["app", "console"]