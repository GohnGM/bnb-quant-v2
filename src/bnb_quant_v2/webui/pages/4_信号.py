"""4_信号 - 信号历史页面。"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from bnb_quant_v2.paths import ANALYSIS_DIR, LIVE_DIR
from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.strategy.base import rule_registry

st.set_page_config(page_title="信号历史", page_icon="📡", layout="wide")
st.title("📡 信号历史")

# 加载特征表
feature_file = ANALYSIS_DIR / "BTCUSDT_1h_p1_f6_features.parquet"

if not feature_file.exists():
    st.error("❌ 特征表不存在！请先在终端运行 `bnbquant backtest build`")
    st.stop()

@st.cache_data
def load_features():
    return pd.read_parquet(feature_file)

df = load_features()
st.success(f"✅ 特征表已加载: {len(df):,} 行")

st.markdown("---")

# 选择规则生成信号
st.subheader("🎯 选择规则生成信号")
rules = list(rule_registry.get_enabled())
rule_names = [r.metadata.name for r in rules]

selected_rule = st.selectbox("选择规则", rule_names)
rule = next((r for r in rules if r.metadata.name == selected_rule), None)

if rule:
    signal_col = rule(df)
    signal_count = signal_col.sum()
    signal_df = df[signal_col == True].copy()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总信号数", f"{signal_count}")
    with col2:
        st.metric("信号占比", f"{signal_count / len(df):.2%}")
    with col3:
        st.metric("样本总数", f"{len(df):,}")
    
    st.markdown("---")
    
    # 最近信号
    st.subheader("📋 最近信号")
    
    if len(signal_df) > 0:
        recent = signal_df.tail(20)
        
        # 显示关键列
        display_cols = ["open_time", "close", "f6_up_count", "f6_first_candle_up"]
        available_cols = [c for c in display_cols if c in signal_df.columns]
        
        if available_cols:
            display_df = recent[available_cols].copy()
            display_df["open_time"] = display_df["open_time"].dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # 信号分布图
    st.subheader("📊 信号分布")
    
    if len(signal_df) > 0:
        # 按月统计
        signal_df["month"] = signal_df["open_time"].dt.to_period("M")
        monthly_signals = signal_df.groupby("month").size().reset_index(name="信号数")
        monthly_signals["month"] = monthly_signals["month"].astype(str)
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=monthly_signals["month"],
            y=monthly_signals["信号数"],
            marker_color="#00d4aa",
        ))
        fig.update_layout(
            title="月度信号分布",
            xaxis_title="月份",
            yaxis_title="信号数",
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # 按年统计
        signal_df["year"] = signal_df["open_time"].dt.year
        yearly_signals = signal_df.groupby("year").size().reset_index(name="信号数")
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("年度信号统计")
            st.dataframe(yearly_signals, use_container_width=True, hide_index=True)
        with col2:
            st.metric("平均每月信号", f"{signal_count / len(monthly_signals):.1f}")

st.markdown("---")

# 实时信号文件检查
st.subheader("⚡ 实时信号状态")
signal_file = LIVE_DIR / "latest_signals.json"

if signal_file.exists():
    import json
    with open(signal_file) as f:
        signals = json.load(f)
    
    if isinstance(signals, list) and len(signals) > 0:
        st.success(f"✅ 最新信号: {len(signals)} 条")
        st.dataframe(pd.DataFrame(signals).head(10), use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ 暂无实时信号")
else:
    st.info("ℹ️ 实时信号文件不存在，系统可能尚未运行")
