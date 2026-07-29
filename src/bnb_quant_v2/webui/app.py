"""Web UI 主入口 - 紫御BTC量化分析系统。"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root / "src"))

import streamlit as st

st.set_page_config(
    page_title="紫御BTC量化分析系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ========== Custom CSS ==========
st.markdown("""
<style>
    /* 全局字体与间距 */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* 隐藏默认 Streamlit chrome 的部分 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* 主标题 */
    h1 {
        background: linear-gradient(90deg, #FFD700, #FF8C00, #FF6347);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        padding: 0.5rem 0;
        font-size: 2.4rem !important;
        letter-spacing: 2px;
    }

    /* 子标题 */
    h2 {
        color: #FFD700 !important;
        border-left: 4px solid #FFD700;
        padding-left: 12px;
        margin-top: 1.5rem;
    }

    h3 {
        color: #E6EDF3 !important;
        margin-top: 1rem;
    }

    /* 信息卡片 */
    .stAlert {
        border-radius: 12px !important;
        padding: 1rem 1.2rem !important;
        border: none !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }

    /* 快速入口卡片 */
    .card {
        background: linear-gradient(135deg, #161B22 0%, #1C2333 100%);
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        transition: all 0.3s ease;
        cursor: pointer;
        min-height: 100px;
    }
    .card:hover {
        border-color: #FFD700;
        box-shadow: 0 4px 20px rgba(255, 215, 0, 0.15);
        transform: translateY(-2px);
    }
    .card-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #FFD700;
        margin-bottom: 0.3rem;
    }
    .card-desc {
        font-size: 0.85rem;
        color: #8B949E;
    }

    /* 指标卡片 */
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
        color: #FFD700 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #8B949E !important;
        font-size: 0.85rem !important;
    }
    div[data-testid="stMetric"] {
        background: #161B22;
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid #30363d;
    }

    /* 表格美化 */
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #30363d;
    }

    /* 按钮 */
    .stButton > button {
        border-radius: 8px !important;
        transition: all 0.2s ease;
        font-weight: 500;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(255,215,0,0.2);
    }

    /* 标签页 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0 !important;
        padding: 0.5rem 1rem !important;
    }
    .stTabs [aria-selected="true"] {
        background: #FFD700 !important;
        color: #0D1117 !important;
        font-weight: 600;
    }

    /* 侧边栏 */
    section[data-testid="stSidebar"] {
        background: #0D1117;
        border-right: 1px solid #30363d;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 2rem;
    }

    /* 代码块 */
    code {
        border-radius: 8px;
        padding: 0.5rem 0.8rem !important;
    }

    /* 分割线 */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, #30363d, transparent);
        margin: 1.5rem 0;
    }

    /* 徽章/标签 */
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.8rem;
        font-weight: 500;
    }
    .badge-success {
        background: rgba(63, 185, 80, 0.15);
        color: #3FB950;
    }
    .badge-warn {
        background: rgba(210, 153, 34, 0.15);
        color: #D29922;
    }
    .badge-danger {
        background: rgba(248, 81, 73, 0.15);
        color: #F85149;
    }
</style>
""", unsafe_allow_html=True)

# ========== 页面内容 ==========
st.title("📈 紫御BTC量化分析系统")

# 快速入口 - 使用 CSS 卡片布局
st.markdown("""
<div style="display: grid; grid-template-columns: repeat(6, 1fr); gap: 1rem; margin-bottom: 1.5rem;">
    <a href="/概览" style="text-decoration: none;">
        <div class="card">
            <div class="card-title">📊 概览</div>
            <div class="card-desc">系统状态、快速统计</div>
        </div>
    </a>
    <a href="/回测" style="text-decoration: none;">
        <div class="card">
            <div class="card-title">📈 回测</div>
            <div class="card-desc">回测结果可视化</div>
        </div>
    </a>
    <a href="/规则" style="text-decoration: none;">
        <div class="card">
            <div class="card-title">📋 规则</div>
            <div class="card-desc">规则管理</div>
        </div>
    </a>
    <a href="/信号" style="text-decoration: none;">
        <div class="card">
            <div class="card-title">📡 信号</div>
            <div class="card-desc">信号历史</div>
        </div>
    </a>
    <a href="/系统" style="text-decoration: none;">
        <div class="card">
            <div class="card-title">⚙️ 系统</div>
            <div class="card-desc">系统监控</div>
        </div>
    </a>
    <a href="/配置" style="text-decoration: none;">
        <div class="card">
            <div class="card-title">🔧 配置</div>
            <div class="card-desc">参数配置管理</div>
        </div>
    </a>
</div>
""", unsafe_allow_html=True)
