"""1_概览 - 系统状态和快速统计。"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

import streamlit as st
import pandas as pd
from datetime import datetime

from bnb_quant_v2.paths import DATA_DIR, KLINE_DIR, ANALYSIS_DIR, LIVE_DIR
from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.strategy.base import rule_registry

st.set_page_config(page_title="概览", page_icon="📊", layout="wide")
st.title("📊 系统概览")

# 系统状态卡片
col1, col2, col3, col4 = st.columns(4)

# 数据文件状态
store = KlineStore()
df_1h = None
df_5m = None

try:
    df_1h = store.load("BTCUSDT", "1h")
    with col1:
        st.metric("1H K线", f"{len(df_1h):,} 条", f"{df_1h['close'].iloc[-1]:,.2f}")
except Exception:
    with col1:
        st.metric("1H K线", "❌ 缺失")

try:
    df_5m = store.load("BTCUSDT", "5m")
    with col2:
        st.metric("5m K线", f"{len(df_5m):,} 条")
except Exception:
    with col2:
        st.metric("5m K线", "❌ 缺失")

# 特征表状态
feature_file = ANALYSIS_DIR / "BTCUSDT_1h_p1_f6_features.parquet"
if feature_file.exists():
    df_features = pd.read_parquet(feature_file)
    with col3:
        st.metric("特征表", f"{len(df_features):,} 行", "✅")
else:
    with col3:
        st.metric("特征表", "❌ 缺失")

# 规则数量
rules = list(rule_registry.get_enabled())
with col4:
    st.metric("已注册规则", f"{len(rules)} 条")

st.markdown("---")

# 最新价格显示
if df_1h is not None and len(df_1h) > 0:
    st.subheader("💰 最新价格")
    latest = df_1h.iloc[-1]
    prev = df_1h.iloc[-2]
    change = latest["close"] - prev["close"]
    change_pct = (change / prev["close"]) * 100
    
    price_col1, price_col2, price_col3 = st.columns(3)
    with price_col1:
        st.metric("当前价格", f"${latest['close']:,.2f}", f"{change:+,.2f} ({change_pct:+.2f}%)")
    with price_col2:
        st.metric("24H 最高", f"${latest['high']:,.2f}")
    with price_col3:
        st.metric("24H 最低", f"${latest['low']:,.2f}")

st.markdown("---")

# 规则列表摘要
st.subheader("📋 规则摘要")
rule_data = []
for rule in rules:
    rule_data.append({
        "名称": rule.metadata.name,
        "层级": rule.metadata.tier,
        "风险": rule.metadata.risk,
        "描述": rule.metadata.description[:30] + "..." if len(rule.metadata.description) > 30 else rule.metadata.description,
    })

if rule_data:
    df_rules = pd.DataFrame(rule_data)
    st.dataframe(df_rules, use_container_width=True, hide_index=True)
