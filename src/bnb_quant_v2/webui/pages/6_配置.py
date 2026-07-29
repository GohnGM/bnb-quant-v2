"""6_配置 - 项目配置管理页面。

支持通过 UI 编辑所有配置参数：
- 基础设置 (config/settings.yaml)
- 实时同步 (config/live_sync.yaml)
- Telegram 通知 (config/telegram.yaml + .env)
- 邮件通知 (config/email.yaml + .env)
- 环境变量 (.env)

所有修改直接写回文件，敏感凭证（密码/Token）以掩码显示。
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "src"))

import streamlit as st
import yaml

from bnb_quant_v2.paths import CONFIG_DIR, PROJECT_ROOT

st.set_page_config(page_title="配置管理", page_icon="🔧", layout="wide")
st.title("🔧 配置管理")
st.caption("集中管理项目所有配置参数 · 修改后点击「保存」写回文件")

ENV_PATH = PROJECT_ROOT / ".env"


# ========== 工具函数 ==========
def load_yaml(path: Path) -> dict:
    """加载 YAML 文件，不存在返回空 dict。"""
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def save_yaml(path: Path, data: dict) -> None:
    """保存 dict 到 YAML 文件。"""
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def load_env() -> dict:
    """解析 .env 文件为 dict（保留注释行结构）。"""
    if not ENV_PATH.exists():
        return {}
    result = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def save_env(env_dict: dict) -> None:
    """保存 dict 到 .env 文件（保留原注释，仅更新键值）。"""
    if not ENV_PATH.exists():
        # 新建文件
        lines = ["# bnb-quant-v2 环境变量\n"]
        for k, v in env_dict.items():
            lines.append(f"{k}={v}\n")
        ENV_PATH.write_text("".join(lines), encoding="utf-8")
        return

    original = ENV_PATH.read_text(encoding="utf-8").splitlines()
    new_lines = []
    written_keys = set()

    for line in original:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if key in env_dict:
            new_lines.append(f"{key}={env_dict[key]}")
            written_keys.add(key)
        else:
            new_lines.append(line)

    # 追加新增的键
    for key, val in env_dict.items():
        if key not in written_keys:
            new_lines.append(f"{key}={val}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def mask_value(val: str, visible: int = 4) -> str:
    """掩码敏感值，仅显示末尾几位。"""
    if not val:
        return ""
    if len(val) <= visible:
        return "*" * len(val)
    return "*" * (len(val) - visible) + val[-visible:]


# ========== Tab 布局 ==========
tab_basic, tab_sync, tab_tg, tab_email, tab_env = st.tabs(
    ["📦 基础设置", "🔄 实时同步", "📡 Telegram", "📧 邮件", "🔑 环境变量"]
)


# ========== 基础设置 ==========
with tab_basic:
    st.subheader("基础设置")
    st.caption("config/settings.yaml · 交易对与数据存储路径")

    settings_path = CONFIG_DIR / "settings.yaml"
    settings = load_yaml(settings_path)

    col1, col2 = st.columns(2)
    with col1:
        symbol = st.text_input("交易对", value=settings.get("symbol", "BTCUSDT"), key="set_symbol")
    with col2:
        kline_dir = st.text_input("K线存储目录", value=settings.get("kline_dir", "data/klines"), key="set_kline_dir")

    if st.button("💾 保存基础设置", type="primary", key="save_basic"):
        save_yaml(settings_path, {"symbol": symbol, "kline_dir": kline_dir})
        st.success("✅ 已保存到 config/settings.yaml")
        st.info("💡 部分修改可能需要重启服务生效")

    st.markdown("---")
    st.markdown("**当前文件内容**")
    st.code(settings_path.read_text(encoding="utf-8") if settings_path.exists() else "(文件不存在)", language="yaml")


# ========== 实时同步 ==========
with tab_sync:
    st.subheader("实时 K 线同步")
    st.caption("config/live_sync.yaml · Gate/Binance 实时数据拉取配置")

    sync_path = CONFIG_DIR / "live_sync.yaml"
    sync = load_yaml(sync_path)

    col1, col2 = st.columns(2)
    with col1:
        sync_symbol = st.text_input("交易对", value=sync.get("symbol", "BTCUSDT"), key="sync_symbol")
        sync_source = st.selectbox(
            "数据源",
            options=["gate", "binance"],
            index=0 if sync.get("source", "gate") == "gate" else 1,
            key="sync_source",
        )
        sync_enabled = st.checkbox("启用实时同步", value=sync.get("enabled", False), key="sync_enabled")
    with col2:
        intervals = st.multiselect(
            "同步周期",
            options=["5m", "1h", "15m", "30m", "4h"],
            default=sync.get("intervals", ["5m", "1h"]),
            key="sync_intervals",
        )
        lb_5m = st.number_input(
            "5m 回看根数", min_value=1, value=sync.get("lookback_bars", {}).get("5m", 24), key="sync_lb_5m"
        )
        lb_1h = st.number_input(
            "1h 回看根数", min_value=1, value=sync.get("lookback_bars", {}).get("1h", 3), key="sync_lb_1h"
        )

    sync_store_dir = st.text_input("存储目录", value=sync.get("store_dir", "data/klines"), key="sync_store_dir")

    if st.button("💾 保存同步配置", type="primary", key="save_sync"):
        sync_data = {
            "symbol": sync_symbol,
            "intervals": intervals,
            "source": sync_source,
            "enabled": sync_enabled,
            "lookback_bars": {"5m": lb_5m, "1h": lb_1h},
            "store_dir": sync_store_dir,
        }
        save_yaml(sync_path, sync_data)
        st.success("✅ 已保存到 config/live_sync.yaml")

    st.markdown("---")
    st.markdown("**当前文件内容**")
    st.code(sync_path.read_text(encoding="utf-8") if sync_path.exists() else "(文件不存在)", language="yaml")


# ========== Telegram ==========
with tab_tg:
    st.subheader("Telegram 通知")
    st.caption("config/telegram.yaml + .env (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")

    tg_path = CONFIG_DIR / "telegram.yaml"
    tg = load_yaml(tg_path)
    env = load_env()

    col1, col2 = st.columns(2)
    with col1:
        tg_enabled = st.checkbox("启用 Telegram", value=tg.get("enabled", False), key="tg_enabled")
        tg_dry_run = st.checkbox("模拟模式 (dry_run)", value=tg.get("dry_run", True), key="tg_dry_run")
        tg_send_signal = st.checkbox("信号触发时发送", value=tg.get("send_on_signal", True), key="tg_send_signal")
        tg_send_error = st.checkbox("错误告警时发送", value=tg.get("send_on_error", True), key="tg_send_error")
        tg_send_heartbeat = st.checkbox("发送日心跳", value=tg.get("send_daily_heartbeat", True), key="tg_send_heartbeat")
    with col2:
        tg_parse_mode = st.selectbox(
            "解析模式",
            options=["", "HTML", "Markdown"],
            index=["", "HTML", "Markdown"].index(tg.get("parse_mode", "")),
            key="tg_parse_mode",
        )
        tg_heartbeat_cron = st.text_input(
            "心跳定时 (UTC cron)", value=tg.get("heartbeat_cron_utc", "0 4 * * *"), key="tg_heartbeat_cron"
        )
        st.markdown("**凭证 (.env)**")
        tg_token = st.text_input(
            "BOT_TOKEN",
            value=env.get("TELEGRAM_BOT_TOKEN", ""),
            type="password",
            placeholder="未配置",
            key="tg_token",
        )
        tg_chat_id = st.text_input(
            "CHAT_ID",
            value=env.get("TELEGRAM_CHAT_ID", ""),
            placeholder="未配置",
            key="tg_chat_id",
        )

    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
    with col_btn1:
        if st.button("💾 保存", type="primary", key="save_tg"):
            tg_data = {
                "enabled": tg_enabled,
                "dry_run": tg_dry_run,
                "parse_mode": tg_parse_mode,
                "send_on_signal": tg_send_signal,
                "send_on_error": tg_send_error,
                "send_daily_heartbeat": tg_send_heartbeat,
                "heartbeat_cron_utc": tg_heartbeat_cron,
            }
            save_yaml(tg_path, tg_data)
            new_env = load_env()
            if tg_token:
                new_env["TELEGRAM_BOT_TOKEN"] = tg_token
            if tg_chat_id:
                new_env["TELEGRAM_CHAT_ID"] = tg_chat_id
            save_env(new_env)
            st.success("✅ 已保存 Telegram 配置和凭证")
    with col_btn2:
        if st.button("🧪 测试连接", key="test_tg"):
            from bnb_quant_v2.notify.config import load_telegram_config
            from bnb_quant_v2.notify.telegram import TelegramClient

            cfg = load_telegram_config()
            if not cfg.can_send:
                st.error("❌ Telegram 未配置完整（需 enabled + token + chat_id）")
            else:
                client = TelegramClient(cfg)
                result = client.send("🏗️ bnb-quant-v2 Telegram 测试消息")
                if result.ok and not result.dry_run:
                    st.success("✅ Telegram 测试成功")
                elif result.dry_run:
                    st.warning("⚠️ 模拟模式，未真实发送")
                else:
                    st.error(f"❌ 失败: {result.error}")

    st.markdown("---")
    st.markdown("**当前配置**")
    st.code(tg_path.read_text(encoding="utf-8") if tg_path.exists() else "(文件不存在)", language="yaml")


# ========== 邮件 ==========
with tab_email:
    st.subheader("邮件通知")
    st.caption("config/email.yaml + .env (EMAIL_PASSWORD)")

    email_path = CONFIG_DIR / "email.yaml"
    email_cfg = load_yaml(email_path)
    env = load_env()

    col1, col2 = st.columns(2)
    with col1:
        em_enabled = st.checkbox("启用邮件", value=email_cfg.get("enabled", False), key="em_enabled")
        em_dry_run = st.checkbox("模拟模式 (dry_run)", value=email_cfg.get("dry_run", True), key="em_dry_run")
        em_host = st.text_input("SMTP 服务器", value=email_cfg.get("smtp_host", "smtp.qq.com"), key="em_host")
        em_port = st.number_input("SMTP 端口", value=int(email_cfg.get("smtp_port", 465)), key="em_port")
        em_secure = st.checkbox("使用 SSL (465端口)", value=email_cfg.get("smtp_secure", True), key="em_secure")
        em_username = st.text_input(
            "发件邮箱 (username)",
            value=email_cfg.get("username", "") or env.get("EMAIL_USERNAME", ""),
            placeholder="you@qq.com",
            key="em_username",
        )
    with col2:
        em_from_name = st.text_input("发件人名称", value=email_cfg.get("from_name", "bnb-quant-v2"), key="em_from_name")
        em_from_addr = st.text_input(
            "发件地址 (留空则用 username)", value=email_cfg.get("from_addr", ""), key="em_from_addr"
        )
        to_addrs_str = st.text_input(
            "收件人 (多个用逗号分隔)",
            value=", ".join(email_cfg.get("to_addrs", []) or []),
            placeholder="a@x.com, b@y.com",
            key="em_to_addrs",
        )
        em_password = st.text_input(
            "SMTP 密码/授权码 (.env EMAIL_PASSWORD)",
            value=env.get("EMAIL_PASSWORD", ""),
            type="password",
            placeholder="未配置",
            key="em_password",
        )
        st.markdown("**发送选项**")
        em_send_signal = st.checkbox("信号触发时发送", value=email_cfg.get("send_on_signal", True), key="em_send_signal")
        em_send_error = st.checkbox("错误告警时发送", value=email_cfg.get("send_on_error", True), key="em_send_error")
        em_send_heartbeat = st.checkbox("发送日心跳", value=email_cfg.get("send_daily_heartbeat", True), key="em_send_heartbeat")

    st.caption("💡 常见配置：QQ邮箱 smtp.qq.com:465(SSL) · 163 smtp.163.com:465(SSL) · Gmail smtp.gmail.com:587(STARTTLS)")

    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
    with col_btn1:
        if st.button("💾 保存", type="primary", key="save_email"):
            to_list = [a.strip() for a in to_addrs_str.split(",") if a.strip()]
            email_data = {
                "enabled": em_enabled,
                "dry_run": em_dry_run,
                "smtp_host": em_host,
                "smtp_port": int(em_port),
                "smtp_secure": em_secure,
                "username": em_username,
                "from_name": em_from_name,
                "from_addr": em_from_addr,
                "to_addrs": to_list,
                "send_on_signal": em_send_signal,
                "send_on_error": em_send_error,
                "send_daily_heartbeat": em_send_heartbeat,
            }
            save_yaml(email_path, email_data)
            new_env = load_env()
            if em_username:
                new_env["EMAIL_USERNAME"] = em_username
            if em_password:
                new_env["EMAIL_PASSWORD"] = em_password
            if em_host:
                new_env["EMAIL_SMTP_HOST"] = em_host
            new_env["EMAIL_SMTP_PORT"] = str(int(em_port))
            save_env(new_env)
            st.success("✅ 已保存邮件配置和凭证")
    with col_btn2:
        if st.button("🧪 测试连接", key="test_email"):
            from bnb_quant_v2.notify.config import load_email_config
            from bnb_quant_v2.notify.email import EmailClient

            cfg = load_email_config()
            if not cfg.can_send:
                st.error("❌ 邮件未配置完整（需 enabled + host + username + password + 收件人）")
            else:
                client = EmailClient(cfg)
                ok, msg = client.test_connection()
                if ok:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")

    st.markdown("---")
    st.markdown("**当前配置**")
    st.code(email_path.read_text(encoding="utf-8") if email_path.exists() else "(文件不存在)", language="yaml")


# ========== 环境变量 ==========
with tab_env:
    st.subheader("环境变量")
    st.caption(f".env · {ENV_PATH}")

    env = load_env()

    st.markdown("**已知环境变量**（修改后点击保存写回 `.env`）")

    # 标准环境变量列表
    known_keys = [
        ("GATE_API_KEY", "Gate API Key (实时同步)"),
        ("GATE_API_SECRET", "Gate API Secret"),
        ("TELEGRAM_BOT_TOKEN", "Telegram Bot Token"),
        ("TELEGRAM_CHAT_ID", "Telegram Chat ID"),
        ("EMAIL_USERNAME", "邮箱用户名"),
        ("EMAIL_PASSWORD", "邮箱密码/授权码"),
        ("EMAIL_SMTP_HOST", "SMTP 服务器"),
        ("EMAIL_SMTP_PORT", "SMTP 端口"),
        ("BINANCE_API_KEY", "Binance API Key (未实现)"),
        ("BINANCE_API_SECRET", "Binance API Secret (未实现)"),
        ("BINANCE_TESTNET", "Binance 测试网 (true/false)"),
        ("BNB_QUANT_ROOT", "项目根目录覆盖"),
    ]

    new_env = {}
    cols = st.columns(2)
    for idx, (key, desc) in enumerate(known_keys):
        with cols[idx % 2]:
            current = env.get(key, "")
            is_secret = any(s in key.upper() for s in ["SECRET", "PASSWORD", "TOKEN"])
            widget_type = "password" if is_secret else "default"
            val = st.text_input(
                f"{key}",
                value=current,
                placeholder=f"未配置 · {desc}",
                type=widget_type,
                key=f"env_{key}",
                help=desc,
            )
            if val:
                new_env[key] = val

    # 显示其他未归类的环境变量
    other_keys = [k for k in env.keys() if k not in {k for k, _ in known_keys}]
    if other_keys:
        st.markdown("**其他环境变量**")
        for key in other_keys:
            is_secret = any(s in key.upper() for s in ["SECRET", "PASSWORD", "TOKEN"])
            val = st.text_input(
                key,
                value=env.get(key, ""),
                type="password" if is_secret else "default",
                key=f"env_other_{key}",
            )
            if val:
                new_env[key] = val

    if st.button("💾 保存环境变量", type="primary", key="save_env"):
        # 合并：保留未在表单中显示但已存在的值
        merged = dict(env)
        merged.update(new_env)
        save_env(merged)
        st.success(f"✅ 已保存到 {ENV_PATH}")

    st.markdown("---")
    st.markdown("**当前 .env 内容**（敏感值已掩码）")
    if ENV_PATH.exists():
        masked_lines = []
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, val = stripped.partition("=")
                if any(s in key.upper() for s in ["SECRET", "PASSWORD", "TOKEN"]):
                    masked_lines.append(f"{key}={mask_value(val.strip())}")
                else:
                    masked_lines.append(line)
            else:
                masked_lines.append(line)
        st.code("\n".join(masked_lines), language="bash")
    else:
        st.warning("⚠️ .env 文件不存在")
