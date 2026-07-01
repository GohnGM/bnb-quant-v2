#!/usr/bin/env python3
"""兼容入口：等同 scripts/backtest_p1_f6.py --target half2。"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--target" not in argv:
        argv = ["--target", "half2", *argv]
    sys.argv = [sys.argv[0], *argv]
    runpy.run_path(str(Path(__file__).resolve().parent / "backtest_p1_f6.py"), run_name="__main__")
