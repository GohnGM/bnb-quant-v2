"""p1×f6 策略常量。

这些常量原本定义在 analysis/intra_5m.py 中，为避免循环导入，
移到这里作为策略模块的一部分。

核心参数
--------
- F6_CLOSE_STRENGTH_MIN: f6 收盘强度阈值（67%）
- F6_RET_STRONG: f6 累计涨幅阈值（0.2%）
- F6_RANGE_HL_MIN: f6 振幅阈值（0.4%）
"""
from __future__ import annotations

F6_CLOSE_STRENGTH_MIN = 0.67
F6_RET_STRONG = 0.002
F6_RANGE_HL_MIN = 0.004