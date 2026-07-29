"""2_回测 - 回测结果可视化。"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from bnb_quant_v2.paths import ANALYSIS_DIR
from bnb_quant_v2.analysis.backtest_p1_f6 import run_p1_f6_backtest
from bnb_quant_v2.strategy.base import rule_registry

st.set_page_config(page_title="回测", page_icon="📈", layout="wide")
st.title("📈 回测分析")

# 加载特征表
feature_file = ANALYSIS_DIR / "BTCUSDT_1h_p1_f6_features.parquet"

if not feature_file.exists():
    st.error("❌ 特征表不存在！请先在终端运行 `bnbquant backtest build`")
    st.stop()

# 使用缓存加载特征表
@st.cache_data
def load_features():
    return pd.read_parquet(feature_file)

df = load_features()
st.success(f"✅ 特征表已加载: {len(df):,} 行")

st.markdown("---")

# 选择规则
st.subheader("🎯 选择回测规则")
rules = list(rule_registry.get_enabled())
rule_names = [r.metadata.name for r in rules]
rule_descriptions = {r.metadata.name: r.metadata.description for r in rules}

selected_rule = st.selectbox(
    "选择规则",
    rule_names,
    format_func=lambda x: f"{x}",
)

# 缓存回测结果
@st.cache_data
def run_cached_backtest(rule_name, df_rows):
    result = run_p1_f6_backtest(df, rule_name=rule_name)
    # 计算年度数据
    yearly_data = []
    rule = result.rule_name  # 修正：使用 rule_name 而非 rule
    for year in sorted(df["open_time"].dt.year.unique()):
        year_df = df[df["open_time"].dt.year == year]
        if len(year_df) > 0:
            year_result = run_p1_f6_backtest(year_df, rule_name=rule)
            yearly_data.append({
                "年份": year,
                "信号数": year_result.signals,
                "准确率": year_result.accuracy,
            })
    return result, yearly_data

# 运行回测按钮
if st.button("🚀 运行回测", type="primary"):
    with st.spinner("运行回测中..."):
        result, yearly_data = run_cached_backtest(selected_rule, len(df))
        
        # 显示核心指标
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("信号数", f"{result.signals}")
        with col2:
            st.metric("准确率", f"{result.accuracy:.2%}")
        with col3:
            st.metric("覆盖度", f"{result.coverage_pct:.2f}%")
        with col4:
            st.metric("基准对比", f"{result.accuracy - result.baseline_up_rate:+.2%}")
        
        st.markdown("---")
        
        # 年度表现
        if yearly_data:
            st.subheader("📈 年度表现")
            df_yearly = pd.DataFrame(yearly_data)
            
            # 年度准确率柱状图
            fig_yearly = go.Figure()
            fig_yearly.add_trace(go.Bar(
                x=df_yearly["年份"].astype(str),
                y=df_yearly["准确率"] * 100,
                text=[f"{v:.1f}%" for v in df_yearly["准确率"] * 100],
                textposition="outside",
                name="准确率",
                marker_color="#00d4aa",
            ))
            fig_yearly.update_layout(
                title="年度准确率",
                xaxis_title="年份",
                yaxis_title="准确率 (%)",
                yaxis_tickformat=".1f",
            )
            st.plotly_chart(fig_yearly, use_container_width=True)
            
            # 年度数据表格
            st.dataframe(df_yearly, use_container_width=True, hide_index=True)
        
        # 最近信号
        st.subheader("📋 最近 10 笔信号")
        rule_name = result.rule_name
        # 使用规则名称作为列名来获取信号
        if rule_name in df.columns:
            signal_df = df[df[rule_name] == True].tail(10)
        else:
            # 如果规则名称不在列中，跳过
            signal_df = pd.DataFrame()
        
        if len(signal_df) > 0:
            display_cols = ["open_time", "close", "high", "low", "f6_up_count"]
            available_cols = [c for c in display_cols if c in signal_df.columns]
            if available_cols:
                display_df = signal_df[available_cols].copy()
                display_df["open_time"] = display_df["open_time"].dt.strftime("%Y-%m-%d %H:%M")
                st.dataframe(display_df, use_container_width=True, hide_index=True)
