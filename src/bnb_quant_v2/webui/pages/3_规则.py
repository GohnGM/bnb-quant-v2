"""3_规则 - 规则管理页面。"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

import streamlit as st
import pandas as pd

from bnb_quant_v2.strategy.base import rule_registry
from bnb_quant_v2.paths import ANALYSIS_DIR
from bnb_quant_v2.analysis.backtest_p1_f6 import run_p1_f6_backtest

st.set_page_config(page_title="规则管理", page_icon="📋", layout="wide")
st.title("📋 规则管理")

# 获取所有规则
rules = list(rule_registry.get_enabled())

st.subheader(f"📊 已注册规则: {len(rules)} 条")

# 规则列表表格
rule_data = []
for rule in rules:
    rule_data.append({
        "规则名称": rule.metadata.name,
        "层级": rule.metadata.tier,
        "风险等级": rule.metadata.risk,
        "描述": rule.metadata.description,
        "启用": "✅" if rule.metadata.enabled else "❌",
    })

df_rules = pd.DataFrame(rule_data)
st.dataframe(df_rules, use_container_width=True, hide_index=True)

st.markdown("---")

# 规则详情
st.subheader("🔍 规则详情与回测")

selected_rule = st.selectbox(
    "选择规则查看详情",
    [r.metadata.name for r in rules],
    format_func=lambda x: f"{x}",
)

rule = next((r for r in rules if r.metadata.name == selected_rule), None)

if rule:
    # 显示规则信息
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**名称**: {rule.metadata.name}")
        st.markdown(f"**层级**: {rule.metadata.tier}")
        st.markdown(f"**风险**: {rule.metadata.risk}")
    with col2:
        st.markdown(f"**描述**: {rule.metadata.description}")
        st.markdown(f"**启用状态**: {'✅ 启用' if rule.metadata.enabled else '❌ 禁用'}")
    
    st.markdown("---")
    
    # 快速回测
    if ANALYSIS_DIR.joinpath("BTCUSDT_1h_p1_f6_features.parquet").exists():
        if st.button("🚀 快速回测此规则"):
            with st.spinner("运行回测..."):
                df = pd.read_parquet(ANALYSIS_DIR / "BTCUSDT_1h_p1_f6_features.parquet")
                result = run_p1_f6_backtest(df, rule_name=selected_rule)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("信号数", result.signals)
                with col2:
                    st.metric("准确率", f"{result.accuracy:.2%}")
                with col3:
                    st.metric("覆盖度", f"{result.coverage_pct:.2f}%")
                with col4:
                    st.metric("基准对比", f"{result.accuracy - result.baseline_up_rate:+.2%}")
        
        st.info("💡 提示: 在回测页面可以查看更详细的图表分析")
    else:
        st.warning("⚠️ 特征表不存在，请先在终端运行 `bnbquant backtest build`")

st.markdown("---")

# 按层级统计
st.subheader("📈 按层级统计")
tier_counts = {}
for rule in rules:
    tier = rule.metadata.tier
    tier_counts[tier] = tier_counts.get(tier, 0) + 1

tier_col1, tier_col2, tier_col3, tier_col4 = st.columns(4)
tiers = list(tier_counts.keys())
cols = [tier_col1, tier_col2, tier_col3, tier_col4]

for i, (tier, count) in enumerate(tier_counts.items()):
    if i < len(cols):
        with cols[i % len(cols)]:
            st.metric(tier, f"{count} 条规则")
