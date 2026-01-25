import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_IMPL"] = "chromadb.telemetry.posthog.Posthog"

from pathlib import Path
import sys
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

import streamlit as st
from src.core.config import Settings
from src.core.llm import LLMClient
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    layout="wide",
    page_title="Novel-Agent",
    page_icon="📚",
    initial_sidebar_state="expanded"
)

# 初始化 LLM 客户端
if "llm_client" not in st.session_state:
    st.session_state.llm_client = None

if st.session_state.llm_client is None:
    try:
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        st.session_state.llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens
        )
        logger.info(f"✅ LLM客户端初始化成功: {config.model.provider}/{config.model.name}")
    except Exception as e:
        logger.error(f"❌ LLM客户端初始化失败：{str(e)}")
        st.session_state.llm_client = None

st.title("📚 Novel-Agent")
st.markdown("欢迎使用多Agent小说创作系统")

# 显示系统状态
col_status1, col_status2, col_status3 = st.columns(3)
with col_status1:
    if st.session_state.llm_client:
        st.success("✅ LLM 已就绪")
    else:
        st.error("❌ LLM 未初始化")
with col_status2:
    st.info("📊 系统运行中")
with col_status3:
    st.info("🔧 配置已加载")

st.markdown("### 📱 快速入口")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("📝 写作助手", use_container_width=True, type="primary"):
        st.switch_page("pages/1_写作助手.py")

with col2:
    if st.button("🔍 检索助手", use_container_width=True):
        st.switch_page("pages/2_检索助手.py")

with col3:
    if st.button("💡 提示词助手", use_container_width=True):
        st.switch_page("pages/3_提示词助手.py")
