"""5_系统 - 系统监控页面。"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

import streamlit as st
import pandas as pd
import json
from datetime import datetime

from bnb_quant_v2.paths import DATA_DIR, KLINE_DIR, ANALYSIS_DIR, LIVE_DIR, LOG_DIR
from bnb_quant_v2.data.kline_store import KlineStore
from bnb_quant_v2.strategy.base import rule_registry

st.set_page_config(page_title="系统监控", page_icon="⚙️", layout="wide")
st.title("⚙️ 系统监控")

# 目录状态
st.subheader("📁 目录状态")

dirs_data = []
for dir_path, name in [
    (DATA_DIR, "数据目录"),
    (KLINE_DIR, "K线目录"),
    (ANALYSIS_DIR, "分析目录"),
    (LIVE_DIR, "运行时目录"),
    (LOG_DIR, "日志目录"),
]:
    exists = dir_path.exists()
    size = 0
    if exists:
        for f in dir_path.rglob("*"):
            if f.is_file():
                size += f.stat().st_size
    dirs_data.append({
        "目录": name,
        "路径": str(dir_path),
        "状态": "✅ 存在" if exists else "❌ 缺失",
        "大小": f"{size / 1024 / 1024:.1f} MB",
    })

st.dataframe(pd.DataFrame(dirs_data), use_container_width=True, hide_index=True)

st.markdown("---")

# 数据文件状态
st.subheader("📊 数据文件状态")

store = KlineStore()
files_data = []

for symbol, interval in [("BTCUSDT", "1h"), ("BTCUSDT", "5m")]:
    file_path = KLINE_DIR / f"{symbol}_{interval}.parquet"
    if file_path.exists():
        size_mb = file_path.stat().st_size / 1024 / 1024
        try:
            df = store.load(symbol, interval)
            rows = len(df)
            time_range = f"{df['open_time'].min()} 至 {df['open_time'].max()}"
        except Exception:
            rows = "❌ 读取失败"
            time_range = "N/A"
    else:
        size_mb = 0
        rows = "❌ 缺失"
        time_range = "N/A"
    
    files_data.append({
        "文件": f"{symbol}_{interval}",
        "大小": f"{size_mb:.1f} MB",
        "行数": rows,
        "时间范围": time_range,
        "状态": "✅ 正常" if file_path.exists() else "❌ 缺失",
    })

# 特征表
feature_file = ANALYSIS_DIR / "BTCUSDT_1h_p1_f6_features.parquet"
if feature_file.exists():
    feat_size = feature_file.stat().st_size / 1024 / 1024
    try:
        df_feat = pd.read_parquet(feature_file)
        feat_rows = len(df_feat)
    except Exception:
        feat_rows = "❌ 读取失败"
else:
    feat_size = 0
    feat_rows = "❌ 缺失"

files_data.append({
    "文件": "特征表",
    "大小": f"{feat_size:.1f} MB",
    "行数": feat_rows,
    "时间范围": "N/A",
    "状态": "✅ 正常" if feature_file.exists() else "❌ 缺失",
})

st.dataframe(pd.DataFrame(files_data), use_container_width=True, hide_index=True)

st.markdown("---")

# 运行时状态
st.subheader("🚀 运行时状态")

# 检查实时文件
runtime_files = [
    ("latest_signals.json", "最新信号"),
    ("dedup_state.json", "去重状态"),
    ("run_stats.json", "运行统计"),
]

for filename, name in runtime_files:
    file_path = LIVE_DIR / filename
    exists = file_path.exists()
    col1, col2, col3 = st.columns([1, 2, 2])
    with col1:
        st.markdown(f"**{name}**")
    with col2:
        if exists:
            size_kb = file_path.stat().st_size / 1024
            st.success(f"✅ 存在 ({size_kb:.1f} KB)")
        else:
            st.warning(f"⚠️ 不存在")
    with col3:
        if exists:
            # 尝试显示文件内容摘要
            try:
                with open(file_path) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    keys = list(data.keys())[:3]
                    st.caption(f"键: {keys}")
                elif isinstance(data, list):
                    st.caption(f"项目数: {len(data)}")
            except Exception:
                st.caption("读取失败")

st.markdown("---")

# 规则统计
st.subheader("📋 规则统计")
rules = list(rule_registry.get_enabled())

# 按层级统计
tier_stats = {}
risk_stats = {}
for rule in rules:
    tier = rule.metadata.tier
    risk = rule.metadata.risk
    tier_stats[tier] = tier_stats.get(tier, 0) + 1
    risk_stats[risk] = risk_stats.get(risk, 0) + 1

col1, col2 = st.columns(2)
with col1:
    st.markdown("**按层级**")
    for tier, count in sorted(tier_stats.items()):
        st.markdown(f"- {tier}: **{count}** 条")

with col2:
    st.markdown("**按风险等级**")
    for risk, count in sorted(risk_stats.items()):
        emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")
        st.markdown(f"{emoji} {risk}: **{count}** 条")

st.markdown("---")

# 系统信息
st.subheader("ℹ️ 系统信息")
info_col1, info_col2 = st.columns(2)
with info_col1:
    st.markdown(f"- **项目根目录**: `{Path.cwd()}`")
    st.markdown(f"- **Python 版本**: {sys.version.split()[0]}")
with info_col2:
    st.markdown(f"- **规则数量**: {len(rules)}")
    st.markdown(f"- **运行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
