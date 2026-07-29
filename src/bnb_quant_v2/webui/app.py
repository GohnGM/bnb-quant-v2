"""Web UI 主入口 - BTC p1×f6 量化信号系统。"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root / "src"))

import streamlit as st

st.set_page_config(
    page_title="BTC p1×f6 量化信号系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 BTC p1×f6 量化信号系统")
st.markdown("---")

st.info("👈 请从左侧导航选择功能模块")

# 快速入口
col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.markdown("#### 📊 概览\n系统状态、快速统计")
with col2:
    st.markdown("#### 📈 回测\n回测结果可视化")
with col3:
    st.markdown("#### 📋 规则\n规则管理")
with col4:
    st.markdown("#### 📡 信号\n信号历史")
with col5:
    st.markdown("#### ⚙️ 系统\n系统监控")
