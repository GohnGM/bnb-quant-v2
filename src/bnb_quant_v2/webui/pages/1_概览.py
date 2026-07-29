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

# ========== 快捷操作：立即发送分析邮件 ==========
st.markdown("""
<div style="background: linear-gradient(135deg, #1a1f2e 0%, #252d42 100%);
            border: 1px solid #FFD700; border-radius: 12px; padding: 1.2rem 1.5rem; margin-bottom: 1rem;">
    <div style="display: flex; align-items: center; gap: 0.8rem;">
        <div style="font-size: 1.8rem;">🚀</div>
        <div>
            <div style="font-size: 1.05rem; font-weight: 700; color: #FFD700;">一键分析并发送邮件</div>
            <div style="font-size: 0.8rem; color: #8B949E;">运行 p1×f6 信号评估，将结果发送到配置的邮箱</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

btn_col1, btn_col2 = st.columns([2, 1])
with btn_col1:
    if st.button("📧 立即发送分析邮件", type="primary", key="quick_email", use_container_width=True):
        with st.spinner("🔄 正在分析并发送..."):
            try:
                from bnb_quant_v2.analysis.evaluator import evaluate_from_store
                from bnb_quant_v2.runtime.pipeline import run_notify_step
                from bnb_quant_v2.notify.config import load_telegram_config, load_email_config

                result = evaluate_from_store()

                if not result.ready:
                    st.error(f"❌ 数据不足：{result.skip_reason}")
                else:
                    triggered_new = [s.to_dict() for s in result.signals if s.triggered]

                    if not triggered_new:
                        st.info("ℹ️ 当前小时无触发信号，将发送日报邮件")
                        # 即使无信号也发送日报
                        email_cfg = load_email_config()
                        if email_cfg.can_send:
                            from bnb_quant_v2.notify.email import EmailClient
                            client = EmailClient(email_cfg)
                            has_price = hasattr(result, 'price')
                            price_str = f"${result.price:,.2f}" if has_price else "N/A"
                            body = f"""📊 紫御BTC量化分析系统 - 日报

⏰ 评估时间: {result.as_of}
📈 BTC 价格: {price_str}

📋 规则评估结果:
"""
                            for signal in result.signals:
                                direction = "📈 涨" if signal.direction == 1 else "📉 跌" if signal.direction == -1 else "➡️ 观望"
                                body += f"  - {signal.rule}: {signal.prediction} ({direction})\n"

                            ok, msg = client.test_connection()
                            if ok:
                                send_result = client.send("紫御BTC量化分析系统 - 今日分析报告", body)
                                if send_result.ok and not send_result.dry_run:
                                    st.success("✅ 分析报告已发送到邮箱！")
                                elif send_result.dry_run:
                                    st.warning("⚠️ 模拟模式，未真实发送邮件")
                                else:
                                    st.error(f"❌ 发送失败: {send_result.error}")
                            else:
                                st.error(f"❌ SMTP 连接失败: {msg}")
                        else:
                            st.warning("⚠️ 邮件未配置，请先在「配置」页面设置")
                    else:
                        # 有信号时通过 pipeline 发送
                        tg_cfg = load_telegram_config()
                        email_cfg = load_email_config()
                        notify_result = run_notify_step(
                            result, triggered_new,
                            tg_cfg=tg_cfg,
                            email_cfg=email_cfg,
                        )
                        if notify_result.signals_sent > 0:
                            st.success(f"✅ 信号通知已发送 ({notify_result.signals_sent} 条)")
                        elif notify_result.dry_run:
                            st.warning("⚠️ 模拟模式，未真实发送邮件")
                        else:
                            st.error(f"❌ 发送失败: {notify_result.errors}")

                    # 显示评估结果
                    with st.expander("📊 查看评估详情"):
                        st.markdown(f"**评估时间**: {result.as_of}")
                        st.markdown(f"**小时**: {result.hour_open_time}")
                        for signal in result.signals:
                            direction = "📈" if signal.direction == 1 else "📉" if signal.direction == -1 else "➡️"
                            triggered_tag = " **[已触发]**" if signal.triggered else ""
                            st.markdown(f"- **{signal.rule}**: {signal.prediction} {direction}{triggered_tag}")

            except Exception as e:
                st.error(f"❌ 运行失败: {e}")

with btn_col2:
    if st.button("📋 查看历史信号", key="goto_signals", use_container_width=True):
        st.info("👈 请从左侧导航选择「信号」页面")

st.markdown("---")

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
