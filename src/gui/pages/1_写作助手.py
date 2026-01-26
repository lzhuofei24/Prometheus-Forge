import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_IMPL"] = "chromadb.telemetry.posthog.Posthog"

from pathlib import Path
import sys
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

import streamlit as st
from typing import Optional, Dict, Any
from datetime import datetime
import tempfile

from src.core.config import Settings
from src.core.llm import LLMClient
from src.core.state import AgentState
from src.core.celery_config import celery_app
from src.core.prompt_manager import PromptRouter
from src.rag.indexer import VectorIndexer
from src.rag.retriever import VectorRetriever
from src.agents.builder import WorldBuilder
from src.agents.novelist import Novelist
from src.agents.editor import ChiefEditor, Critic
from src.workflow.graph import NovelWorkflow
from src.utils.file_manager import ProjectManager
from src.utils.novel_query import NovelQuery
from src.utils.importer import NovelImporter
from src.workflow.import_graph import ImportWorkflow, BatchProcessor
from src.gui.workflow_executor import WorkflowExecutor
from celery.result import AsyncResult
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_session_state():
    if "current_novel" not in st.session_state:
        st.session_state.current_novel = None
    if "current_chapter" not in st.session_state:
        st.session_state.current_chapter = None
    if "workflow" not in st.session_state:
        st.session_state.workflow = None
    if "file_manager" not in st.session_state:
        st.session_state.file_manager = None
    if "query" not in st.session_state:
        st.session_state.query = None
    if "running_tasks" not in st.session_state:
        st.session_state.running_tasks = {}
    if "task_statuses" not in st.session_state:
        st.session_state.task_statuses = {}
    if "content_edit_mode" not in st.session_state:
        st.session_state.content_edit_mode = {}
    if "task_logs" not in st.session_state:
        st.session_state.task_logs = []
    if "agent_tasks" not in st.session_state:
        st.session_state.agent_tasks = {}
    if "danmaku_messages" not in st.session_state:
        st.session_state.danmaku_messages = []
    if "previous_nodes" not in st.session_state:
        st.session_state.previous_nodes = {}
    if "workflow_executors" not in st.session_state:
        st.session_state.workflow_executors = {}
    if "workflow_running" not in st.session_state:
        st.session_state.workflow_running = {}
    if "workflow_results" not in st.session_state:
        st.session_state.workflow_results = {}
    if "workflow_errors" not in st.session_state:
        st.session_state.workflow_errors = {}
    if "_save_success" not in st.session_state:
        st.session_state._save_success = False
    if "_refresh_success" not in st.session_state:
        st.session_state._refresh_success = False
    if "import_progress" not in st.session_state:
        st.session_state.import_progress = None
    if "import_logs" not in st.session_state:
        st.session_state.import_logs = []
    if "chapter_page" not in st.session_state:
        st.session_state.chapter_page = 0
    if "celery_tasks" not in st.session_state:
        st.session_state.celery_tasks = {}
    if "prompt_router" not in st.session_state:
        st.session_state.prompt_router = None
    if "llm_client" not in st.session_state:
        st.session_state.llm_client = None


def init_components():
    # 优先初始化 LLM 客户端
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
    
    if st.session_state.workflow is None:
        try:
            config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
            workspace_root = Path(config.paths.workspace)
            
            llm_client = st.session_state.llm_client
            
            # ⚡ 优化：延迟加载 VectorIndexer，避免启动时的慢速初始化
            # 只有在真正需要 WorldBuilder 时才初始化（目前基本不使用）
            indexer = None
            retriever = None
            # 注释掉自动初始化，改为按需加载
            # try:
            #     indexer = VectorIndexer(
            #         persist_directory=Path(config.paths.chroma_db),
            #         collection_name="novel_chunks"
            #     )
            #     retriever = VectorRetriever(indexer.collection)
            # except Exception as e:
            #     logger.warning(f"向量数据库初始化失败，将使用基础功能：{str(e)}")
            
            file_manager = ProjectManager(workspace_root)
            
            world_builder = None
            # WorldBuilder 依赖 retriever，暂时禁用（功能基本不使用）
            # if retriever and llm_client:
            #     try:
            #         world_builder = WorldBuilder(llm_client, retriever, file_manager)
            #     except Exception as e:
            #         logger.warning(f"WorldBuilder初始化失败：{str(e)}")
            
            novelist = None
            chief_editor = None
            critic = None
            if llm_client:
                try:
                    novelist = Novelist(llm_client, file_manager)
                    chief_editor = ChiefEditor(llm_client, file_manager)
                    critic = Critic(llm_client, file_manager)
                except Exception as e:
                    logger.warning(f"Agent初始化失败：{str(e)}")
            
            workflow = None
            # ⚡ 优化：即使 world_builder 为 None 也允许创建 workflow（仅需 novelist）
            if novelist:
                try:
                    # 从YAML文件直接读取workflow配置
                    import yaml
                    config_path = project_root / "config" / "settings.yaml"
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = yaml.safe_load(f)
                    use_new_arch = config_data.get("workflow", {}).get("use_new_architecture", False)
                    
                    workflow = NovelWorkflow(
                        world_builder=world_builder,  # 可以为 None
                        novelist=novelist,
                        chief_editor=chief_editor,
                        critic=critic,
                        file_manager=file_manager,
                        llm_client=llm_client,
                        use_new_architecture=use_new_arch
                    )
                except Exception as e:
                    logger.warning(f"工作流初始化失败：{str(e)}")
            
            st.session_state.workflow = workflow
            st.session_state.file_manager = file_manager
            st.session_state.query = NovelQuery()
            if "prompt_router" not in st.session_state or st.session_state.prompt_router is None:
                try:
                    st.session_state.prompt_router = PromptRouter()
                except Exception as e:
                    logger.warning(f"PromptRouter初始化失败：{str(e)}")
                    st.session_state.prompt_router = None
        except Exception as e:
            logger.error(f"组件初始化失败：{str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            if st.session_state.file_manager is None:
                try:
                    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
                    workspace_root = Path(config.paths.workspace)
                    st.session_state.file_manager = ProjectManager(workspace_root)
                    st.session_state.query = NovelQuery()
                except Exception as e2:
                    logger.error(f"基础组件初始化也失败：{str(e2)}")
                    st.error(f"系统初始化失败：{str(e)}")
                    with st.expander("查看详细错误信息"):
                        st.code(traceback.format_exc())
                    st.stop()


def process_novel_import(file_path: Path, novel_name: str, enable_analysis: bool, progress_container=None, log_container=None):
    logs = []
    
    def update_logs(new_log):
        logs.append(new_log)
        if log_container:
            log_container.markdown("\n".join([f"- {log}" for log in logs[-10:]]))
    
    try:
        file_manager = st.session_state.file_manager
        if file_manager is None:
            raise ValueError("文件管理器未初始化")
        
        workspace_root = file_manager.workspace_root
        importer = NovelImporter(workspace_root)
        
        update_logs("开始导入小说...")
        if progress_container:
            progress_container.progress(0.0, text="正在切分章节...")
        
        try:
            update_logs(f"正在读取文件: {file_path}")
            results = importer.import_novel(file_path, novel_name)
            
            original_chapters = [r for r in results if isinstance(r.get("chapter_num"), (int, float)) and (isinstance(r.get("chapter_num"), int) or (isinstance(r.get("chapter_num"), float) and r["chapter_num"] == int(r["chapter_num"])))]
            long_chapters = [r for r in results if isinstance(r.get("chapter_num"), float) and r["chapter_num"] != int(r["chapter_num"])]
            
            update_logs(f"✅ 切分完成，共 {len(results)} 章")
            if long_chapters:
                update_logs(f"📊 检测到 {len(original_chapters)} 个原始章节，其中超长章节已切分为 {len(long_chapters)} 个子章节")
            else:
                update_logs(f"📊 共 {len(results)} 个章节，未检测到超长章节（所有章节均 ≤ 3000 字）")
            
        except Exception as e:
            update_logs(f"❌ 导入错误：{str(e)}")
            import traceback
            update_logs(f"详细错误：{traceback.format_exc()}")
            raise
        
        if progress_container:
            progress_container.progress(1.0, text=f"切分完成，共 {len(results)} 章")
        
        if enable_analysis:
            logs.append("开始 AI 分析...")
            if log_container:
                log_container.markdown("\n".join([f"- {log}" for log in logs[-5:]]))
            
            llm_client = None
            if st.session_state.workflow and hasattr(st.session_state.workflow, 'novelist'):
                llm_client = st.session_state.workflow.novelist.llm_client
            
            if llm_client is None:
                config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
                llm_client = LLMClient(
                    provider=config.model.provider,
                    model=config.model.name,
                    temperature=config.model.temperature,
                    max_tokens=config.model.max_tokens
                )
            
            novelist = Novelist(llm_client, file_manager)
            critic = Critic(llm_client, file_manager)
            import_workflow = ImportWorkflow(novelist, critic, file_manager, llm_client)
            batch_processor = BatchProcessor(import_workflow, file_manager)
            
            def update_callback(novel, chapter_num, node_name, node_state):
                total_chapters = len(results)
                chapter_nums = [r["chapter_num"] for r in results]
                if chapter_num in chapter_nums:
                    current_index = chapter_nums.index(chapter_num) + 1
                else:
                    current_index = 1
                
                stage_map = {
                    "load": "加载章节",
                    "extract": "提取信息",
                    "outline": "生成大纲",
                    "review": "生成审阅"
                }
                stage = stage_map.get(node_name, "处理中")
                
                progress_text = f"正在分析第 {current_index}/{total_chapters} 章 - {stage}"
                if progress_container:
                    progress_value = current_index / total_chapters
                    progress_container.progress(progress_value, text=progress_text)
                
                if node_name == "outline":
                    outline = node_state.get("outline", "")
                    if outline:
                        preview = outline[:200] + "..." if len(outline) > 200 else outline
                        logs.append(f"📝 第{chapter_num}章大纲预览：{preview}")
                        if log_container:
                            log_container.markdown("\n".join([f"- {log}" for log in logs[-5:]]))
            
            analysis_results = batch_processor.process_all_chapters(novel_name, update_callback)
            
            success_count = sum(1 for r in analysis_results if r.get("status") == "success")
            logs.append(f"✅ 分析完成：{success_count}/{len(analysis_results)} 章成功")
            if log_container:
                log_container.markdown("\n".join([f"- {log}" for log in logs[-5:]]))
            if progress_container:
                progress_container.progress(1.0, text="分析完成")
        
        if file_path.exists() and str(file_path).startswith(str(Path(tempfile.gettempdir()))):
            try:
                file_path.unlink()
            except:
                pass
        
        return True
    except Exception as e:
        logs.append(f"❌ 错误：{str(e)}")
        if log_container:
            log_container.markdown("\n".join([f"- {log}" for log in logs[-5:]]))
        import traceback
        logger.error(traceback.format_exc())
        raise


def run_workflow(novel_name: str, chapter_num: int, user_feedback: Optional[str] = None, status_container=None):
    """
    执行工作流 - 使用 Celery 异步任务
    """
    logger.info(f"开始执行工作流: novel={novel_name}, chapter={chapter_num}")
    
    try:
        # 读取配置判断使用新旧架构
        import yaml
        project_root = Path(__file__).parent.parent.parent.parent  # 回到项目根目录
        config_path = project_root / "config" / "settings.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        use_new_arch = config_data.get("workflow", {}).get("use_new_architecture", False)
        
        logger.info(f"使用{'新' if use_new_arch else '旧'}架构工作流")
        
        novel_key = f"{novel_name}_{chapter_num}"
        
        if use_new_arch:
            # 使用新架构的完整工作流
            from src.workers.tasks import run_workflow_task
            task = run_workflow_task.delay(novel_name, chapter_num, user_feedback)
        else:
            # 使用旧架构的分离任务
            from src.workers.tasks import generate_outline_task, write_chapter_task
            if user_feedback:
                task = write_chapter_task.delay(novel_name, chapter_num, user_feedback)
            else:
                task = generate_outline_task.delay(novel_name, chapter_num)
        
        st.session_state.celery_tasks[novel_key] = {
            "task_id": task.id,
            "novel_name": novel_name,
            "chapter_num": chapter_num,
            "status": "PENDING",
            "started_at": datetime.now()
        }
        
        logger.info(f"Celery 任务已提交: {task.id}")
        
        # 提示用户任务已提交，引导至监控页面
        st.toast(f"✅ 任务已提交 | ID: {task.id[:16]}...\n📍 前往 '5_任务监控助手' 查看进度", icon="🚀")
        
        return task.id
            
    except Exception as e:
        logger.error(f"run_workflow 异常: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise


def apply_custom_css():
    st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
    }
    .chapter-item {
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 0.25rem;
        cursor: pointer;
        transition: background-color 0.2s;
    }
    .chapter-item:hover {
        background-color: rgba(250, 250, 250, 0.8);
    }
    .chapter-item.selected {
        background-color: rgba(49, 51, 63, 0.1);
        border-left: 3px solid #1f77b4;
    }
    [data-testid="stSidebar"] {
        padding-top: 1rem;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.5rem;
    }
    h3 {
        margin-top: 0.5rem;
        margin-bottom: 0.5rem;
    }
    .danmaku-container {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 100vh;
        pointer-events: none;
        z-index: 9999;
        overflow: hidden;
    }
    .danmaku-item {
        position: absolute;
        white-space: nowrap;
        font-size: 14px;
        color: #1f77b4;
        background: rgba(255, 255, 255, 0.9);
        padding: 4px 8px;
        border-radius: 4px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        animation: danmaku-move 10s linear;
    }
    @keyframes danmaku-move {
        from {
            transform: translateX(100vw);
        }
        to {
            transform: translateX(-100%);
        }
    }
    .agent-card {
        border-radius: 8px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        border: 1px solid rgba(128, 128, 128, 0.3);
        background: transparent;
    }
    .task-card {
        border-radius: 4px;
        padding: 0.5rem;
        margin: 0.25rem 0;
        font-size: 0.85rem;
        border: 1px solid rgba(128, 128, 128, 0.2);
        background: transparent;
        color: inherit;
    }
    .task-scroll {
        max-height: 200px;
        overflow-y: auto;
    }
    [data-testid="stAppViewContainer"] {
        background-color: transparent !important;
    }
    [data-testid="stAppViewContainer"]::before {
        display: none !important;
    }
    .element-container {
        position: relative;
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 2rem;
        padding-right: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)


# 任务监控功能已移至独立页面: 5_任务监控助手.py
# 保留 celery_tasks session state 用于记录已提交的任务


def main():
    st.set_page_config(
        layout="wide", 
        page_title="Novel-Agent", 
        page_icon="📚",
        initial_sidebar_state="expanded"
    )
    
    apply_custom_css()
    
    try:
        init_session_state()
        init_components()
        
        if st.session_state.file_manager is None:
            st.error("⚠️ 文件管理器未初始化，请检查配置")
            st.info("请确保 config/settings.yaml 文件存在且配置正确")
            st.stop()
        
        if st.session_state.query is None:
            st.error("⚠️ 查询对象未初始化")
            st.stop()
    except Exception as e:
        st.error(f"❌ 系统初始化失败：{str(e)}")
        import traceback
        with st.expander("查看详细错误信息"):
            st.code(traceback.format_exc())
        st.stop()
    
    
    if hasattr(st.session_state, "_import_file_path") and st.session_state._import_file_path:
        file_path = st.session_state._import_file_path
        novel_name = st.session_state._import_novel_name
        enable_analysis = st.session_state._import_enable_analysis
        
        with st.container():
            st.markdown("### 📥 导入进度")
            progress_placeholder = st.empty()
            log_placeholder = st.empty()
            
            progress_placeholder.progress(0.0, text="准备导入...")
            log_placeholder.markdown("- 正在初始化...")
            
            try:
                process_novel_import(file_path, novel_name, enable_analysis, progress_placeholder, log_placeholder)
                st.success("✅ 导入完成！")
                st.session_state.current_novel = novel_name
                st.session_state.current_chapter = None
                del st.session_state._import_file_path
                del st.session_state._import_novel_name
                del st.session_state._import_enable_analysis
                st.rerun()
            except Exception as e:
                st.error(f"❌ 导入失败：{str(e)}")
                import traceback
                with st.expander("查看详细错误信息"):
                    st.code(traceback.format_exc())
                del st.session_state._import_file_path
                del st.session_state._import_novel_name
                del st.session_state._import_enable_analysis
    
    # 侧边栏监控已移除，请访问 "5_任务监控助手" 页面查看任务状态
    
    for key in list(st.session_state.workflow_errors.keys()):
        err = st.session_state.workflow_errors[key]
        if err:
            st.toast(f"❌ {err['message']}")
            st.session_state.workflow_errors[key] = None

    for key in list(st.session_state.workflow_results.keys()):
        res = st.session_state.workflow_results[key]
        if res:
            st.toast("✅ 章节生成完成！")
            st.session_state.workflow_results[key] = None
    
    if "_workflow_error" in st.session_state and st.session_state._workflow_error:
        error_info = st.session_state._workflow_error
        st.error(error_info["message"])
        with st.expander("查看详细错误信息"):
            st.code(error_info["trace"])
        st.session_state._workflow_error = None
    
    if "danmaku_messages" in st.session_state and len(st.session_state.danmaku_messages) > 0:
        danmaku_items = []
        recent_messages = st.session_state.danmaku_messages[-5:]
        for i, msg in enumerate(recent_messages):
            top_pos = (hash(msg.get('message', '')) % 70) + 10
            delay = i * 0.5
            message_text = msg.get('message', '')
            if message_text:
                danmaku_items.append(
                    f'<div class="danmaku-item" style="top: {top_pos}%; animation-delay: {delay}s;">{message_text}</div>'
                )
        if danmaku_items:
            danmaku_html = f"""
            <div class="danmaku-container">
                {''.join(danmaku_items)}
            </div>
            """
            st.markdown(danmaku_html, unsafe_allow_html=True)
    
    col_left, col_mid, col_right = st.columns([1.2, 2, 6], gap="small")
    
    with col_left:
        st.markdown('<h3 style="margin-top: 10px; margin-bottom: 10px;">📚 小说列表</h3>', unsafe_allow_html=True)
        
        with st.expander("📥 导入小说", expanded=False):
            import_mode = st.radio(
                "导入方式",
                ["上传文件", "本地路径"],
                horizontal=True,
                key="import_mode"
            )
            
            if import_mode == "上传文件":
                uploaded_file = st.file_uploader(
                    "选择 .txt 文件",
                    type=["txt"],
                    key="import_file_upload"
                )
                file_path = None
                if uploaded_file:
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb") as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        file_path = Path(tmp_file.name)
            else:
                file_path_str = st.text_input(
                    "文件路径",
                    placeholder="例如：D:/novels/小说.txt",
                    key="import_file_path"
                )
                file_path = Path(file_path_str) if file_path_str else None
                uploaded_file = None
            
            novel_name = st.text_input(
                "小说名称",
                placeholder="输入小说名称（将作为项目文件夹名）",
                key="import_novel_name"
            )
            
            enable_analysis = st.checkbox(
                "导入并生成大纲/书评",
                value=True,
                key="import_enable_analysis"
            )
            
            if st.button("🚀 开始导入并分析", use_container_width=True, type="primary"):
                if not file_path and not uploaded_file:
                    st.error("请选择或上传文件")
                elif not novel_name:
                    st.error("请输入小说名称")
                elif file_path and not file_path.exists():
                    st.error(f"文件不存在：{file_path}")
                else:
                    try:
                        actual_file_path = file_path
                        if uploaded_file:
                            import tempfile
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="wb") as tmp_file:
                                tmp_file.write(uploaded_file.getvalue())
                                actual_file_path = Path(tmp_file.name)
                        
                        st.session_state.import_progress = {
                            "status": "importing",
                            "current": 0,
                            "total": 0,
                            "stage": "正在切分章节..."
                        }
                        st.session_state.import_logs = []
                        st.session_state._import_file_path = actual_file_path
                        st.session_state._import_novel_name = novel_name
                        st.session_state._import_enable_analysis = enable_analysis
                        st.rerun()
                    except Exception as e:
                        st.error(f"导入失败：{str(e)}")
        
        if st.session_state.query is None:
            st.error("系统未正确初始化，请刷新页面")
            st.stop()
        
        novels = st.session_state.query.list_novels()
        
        if not novels:
            st.info("暂无小说")
        else:
            for novel in novels:
                chapters_summary = st.session_state.query.get_chapters_summary(novel)
                chapter_count = len(chapters_summary)
                is_selected = novel == st.session_state.current_novel
                
                button_label = f"{novel} ({chapter_count}章)"
                
                if st.button(
                    button_label,
                    key=f"novel_{novel}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary"
                ):
                    if novel != st.session_state.current_novel:
                        st.session_state.current_novel = novel
                        st.session_state.current_chapter = None
                        st.session_state.chapter_page = 0
                        st.rerun()
                        return
    
    with col_mid:
        st.markdown("### 📑 章节列表")
        
        if st.session_state.current_novel:
            if st.session_state.query is None:
                st.error("系统未正确初始化，请刷新页面")
                st.stop()
            
            novel_name = st.session_state.current_novel
            chapters_summary = st.session_state.query.get_chapters_summary(novel_name)
            
            ITEMS_PER_PAGE = 10
            total_chapters = len(chapters_summary)
            total_pages = (total_chapters + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE if total_chapters > 0 else 1
            
            if total_pages > 0:
                current_page = st.session_state.chapter_page
                if current_page >= total_pages:
                    current_page = total_pages - 1
                    st.session_state.chapter_page = current_page
                
                start_idx = current_page * ITEMS_PER_PAGE
                end_idx = min(start_idx + ITEMS_PER_PAGE, total_chapters)
                chapters_to_display = chapters_summary[start_idx:end_idx]
            else:
                chapters_to_display = []
                current_page = 0
                total_pages = 1
            
            if st.button("➕ 新建章节", use_container_width=True, type="primary"):
                if st.session_state.workflow is None:
                    st.session_state._workflow_error = {
                        "message": "工作流未初始化，无法创建章节。请刷新页面或检查配置。",
                        "trace": ""
                    }
                    st.rerun()
                    return
                
                file_manager = st.session_state.file_manager
                workflow = st.session_state.workflow
                
                if file_manager is None:
                    st.session_state._workflow_error = {
                        "message": "文件管理器未初始化",
                        "trace": ""
                    }
                    st.rerun()
                    return
                
                try:
                    logger.info(f"用户点击新建章节: {novel_name}")
                    query = st.session_state.query
                    info = query.get_novel_info(novel_name)
                    chapters = info.get("chapters") or []
                    next_chapter_num = (max(chapters) + 1) if chapters else 1
                    logger.info(f"下一个章节号: {next_chapter_num}")
                    from src.core.db_service import DatabaseService
                    novel = DatabaseService.get_novel_by_title(novel_name)
                    if novel:
                        DatabaseService.get_or_create_chapter(novel.id, next_chapter_num)
                    if file_manager:
                        file_manager.init_chapter(novel_name, next_chapter_num)
                    logger.info("章节目录初始化完成")
                    
                    st.session_state.current_chapter = next_chapter_num
                    
                    novel_key = f"{novel_name}_{next_chapter_num}"
                    if novel_key not in st.session_state.workflow_running or not st.session_state.workflow_running[novel_key]:
                        try:
                            logger.info("开始执行工作流")
                            run_workflow(novel_name, next_chapter_num, status_container=None)
                            logger.info("工作流已启动（后台执行）")
                        except Exception as e:
                            logger.error(f"工作流启动异常: {str(e)}")
                            import traceback
                            error_trace = traceback.format_exc()
                            logger.error(f"错误堆栈:\n{error_trace}")
                            
                            error_msg = str(e)
                            if len(error_msg) > 200:
                                error_msg = error_msg[:200] + "..."
                            st.session_state._workflow_error = {
                                "message": f"章节生成失败：{error_msg}",
                                "trace": error_trace
                            }
                except Exception as e:
                    logger.error(f"创建章节失败: {str(e)}")
                    import traceback
                    error_trace = traceback.format_exc()
                    logger.error(f"错误堆栈:\n{error_trace}")
                    st.session_state._workflow_error = {
                        "message": f"创建章节失败：{str(e)}",
                        "trace": error_trace
                    }
                
                st.rerun()
                return
            
            st.markdown('<div style="margin-bottom: 10px;"></div>', unsafe_allow_html=True)
            
            for ch_info in chapters_to_display:
                title = ch_info.get('title', '')
                status_text = ch_info.get('status', 'unknown')
                chapter_num_raw = ch_info.get('chapter_num')
                folder_index = ch_info.get('folder_index', chapter_num_raw)
                is_selected = folder_index == st.session_state.current_chapter
                
                status_icon = "🟢" if status_text == "published" else "🟡"
                
                if chapter_num_raw is None:
                    chapter_num_str = str(folder_index)
                elif isinstance(chapter_num_raw, float):
                    if chapter_num_raw.is_integer():
                        chapter_num_str = str(int(chapter_num_raw))
                    else:
                        chapter_num_str = str(chapter_num_raw)
                elif isinstance(chapter_num_raw, int):
                    chapter_num_str = str(chapter_num_raw)
                else:
                    chapter_num_str = str(chapter_num_raw)
                
                if not title:
                    display_text = f"{status_icon} 第{chapter_num_str}章"
                else:
                    display_text = f"{status_icon} 第{chapter_num_str}章 {title}"
                
                button_type = "primary" if is_selected else "secondary"
                
                if st.button(
                    display_text,
                    key=f"chapter_{folder_index}",
                    use_container_width=True,
                    type=button_type
                ):
                    st.session_state.current_chapter = folder_index
                    st.rerun()
            
            if total_pages > 1:
                st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
                
                c1, c2 = st.columns([3, 1])
                
                with c1:
                    target_page = st.number_input(
                        f"第 {current_page + 1}/{total_pages} 页 | 跳转至:", 
                        min_value=1, 
                        max_value=total_pages, 
                        value=current_page + 1,
                        label_visibility="visible",
                        key=f"chapter_page_input_{novel_name}"
                    )
                
                with c2:
                    st.markdown('<div style="height: 28px"></div>', unsafe_allow_html=True)
                    if st.button("Go", use_container_width=True, key=f"go_{novel_name}"):
                        st.session_state.chapter_page = target_page - 1
                        st.rerun()
        else:
            st.info("请先选择小说")
    
    if st.session_state._save_success:
        st.success("已保存！")
        st.session_state._save_success = False
    
    if st.session_state.get("_refresh_success"):
        st.success("🔄 章节已刷新")
        st.session_state._refresh_success = False
    
    with col_right:
        if st.session_state.current_novel and st.session_state.current_chapter:
            novel_name = st.session_state.current_novel
            chapter_num = st.session_state.current_chapter
            chapter_info = st.session_state.query.get_chapter_info(novel_name, chapter_num)
            
            if not chapter_info:
                st.error(f"无法加载章节信息：第{chapter_num}章")
            else:
                meta = chapter_info.get('meta', {})
                chapter_title = meta.get('title', '')
                
                st.markdown('<div style="height: 10px"></div>', unsafe_allow_html=True)
                
                c_title, c_refresh, c_save, c_rewrite, c_del = st.columns([5, 0.8, 0.8, 0.8, 0.8], gap="small", vertical_alignment="bottom")
                
                with c_title:
                    new_title = st.text_input(
                        "章节标题",
                        value=chapter_title,
                        placeholder="输入章节标题",
                        key=f"title_{chapter_num}",
                        label_visibility="visible"
                    )
                
                with c_refresh:
                    if st.button("🔄", key=f"refresh_{chapter_num}", use_container_width=True, help="刷新章节"):
                        # 清除该章节的缓存
                        content_key = f"content_{chapter_num}"
                        outline_key = f"outline_{chapter_num}"
                        title_key = f"title_{chapter_num}"
                        edit_mode_key = f"edit_mode_{chapter_num}"
                        
                        if content_key in st.session_state:
                            del st.session_state[content_key]
                        if outline_key in st.session_state:
                            del st.session_state[outline_key]
                        if title_key in st.session_state:
                            del st.session_state[title_key]
                        if edit_mode_key in st.session_state.content_edit_mode:
                            del st.session_state.content_edit_mode[edit_mode_key]
                        
                        # 清除该章节的章节信息缓存
                        chapter_cache_key = f"chapter_{novel_name}_{chapter_num}"
                        if chapter_cache_key in st.session_state:
                            del st.session_state[chapter_cache_key]
                        
                        st.session_state._refresh_success = True
                        st.rerun()
                
                with c_save:
                    if st.button("💾", key=f"save_{chapter_num}", use_container_width=True, help="保存"):
                        content_key = f"content_{chapter_num}"
                        outline_key = f"outline_{chapter_num}"
                        title_key = f"title_{chapter_num}"
                        
                        content = chapter_info.get('content', '')
                        outline = chapter_info.get('outline', '')
                        title = chapter_title
                        
                        if content_key in st.session_state:
                            content = st.session_state[content_key]
                        if outline_key in st.session_state:
                            outline = st.session_state[outline_key]
                        if title_key in st.session_state:
                            title = st.session_state[title_key]
                        
                        save_chapter(novel_name, chapter_num, title, content, outline)
                        st.session_state._save_success = True
                        st.rerun()
                
                with c_rewrite:
                    if st.button("🤖", key=f"rewrite_{chapter_num}", use_container_width=True, help="AI重写"):
                        st.session_state.show_rewrite_dialog = True
                        st.rerun()
                
                with c_del:
                    if st.button("🗑️", key=f"delete_{chapter_num}", use_container_width=True, help="删除"):
                        st.session_state.show_delete_confirm = True
                        st.rerun()
                
                if st.session_state.get("show_rewrite_dialog"):
                    with st.container(border=True):
                        st.write("**输入修改意见**")
                        
                        rewrite_type = st.radio(
                            "重写类型",
                            ["重写正文", "重写大纲"],
                            horizontal=True
                        )
                        
                        feedback = st.text_area(
                            "修改意见",
                            height=150,
                            key="rewrite_feedback"
                        )
                        
                        col_ok, col_cancel = st.columns(2)
                        with col_ok:
                            if st.button("确定", use_container_width=True, type="primary"):
                                if feedback:
                                    rewrite_type_val = "content" if rewrite_type == "重写正文" else "outline"
                                    
                                    novel_key = f"{novel_name}_{chapter_num}"
                                    if novel_key not in st.session_state.workflow_running or not st.session_state.workflow_running[novel_key]:
                                        result = run_workflow(novel_name, chapter_num, feedback, status_container=None)
                                    
                                    st.session_state.show_rewrite_dialog = False
                                    st.rerun()
                                else:
                                    st.warning("请输入修改意见")
                        
                        with col_cancel:
                            if st.button("取消", use_container_width=True):
                                st.session_state.show_rewrite_dialog = False
                                st.rerun()
                
                if st.session_state.get("show_delete_confirm"):
                    with st.container(border=True):
                        st.warning(f"确定要删除《{novel_name}》第{chapter_num}章吗？此操作不可恢复！")
                        
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("确认删除", use_container_width=True, type="primary"):
                                delete_chapter(novel_name, chapter_num)
                                st.session_state.current_chapter = None
                                st.session_state.show_delete_confirm = False
                                st.rerun()
                        
                        with col_no:
                            if st.button("取消", use_container_width=True):
                                st.session_state.show_delete_confirm = False
                                st.rerun()
                
                st.markdown('<div style="margin-bottom: -28px;"></div>', unsafe_allow_html=True)
                
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["📄 正文", "📝 大纲", "📊 元数据", "📋 审稿意见", "🎨 多模态"])
                
                with tab1:
                    content_key = f"content_{chapter_num}"
                    edit_mode_key = f"edit_mode_{chapter_num}"
                    
                    if edit_mode_key not in st.session_state.content_edit_mode:
                        st.session_state.content_edit_mode[edit_mode_key] = True
                    
                    st.markdown("""
                    <style>
                    div[data-testid="stRadio"] > div {
                        flex-direction: row !important;
                        gap: 20px !important;
                    }
                    .stRadio { margin-top: -15px; margin-bottom: -15px; }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    c_mode, c_spacer = st.columns([3.5, 6.5], vertical_alignment="center")
                    
                    with c_mode:
                        mode = st.radio(
                            "模式",
                            ["编辑", "预览"],
                            horizontal=True,
                            index=0 if st.session_state.content_edit_mode[edit_mode_key] else 1,
                            key=f"mode_radio_{chapter_num}",
                            label_visibility="collapsed"
                        )
                        st.session_state.content_edit_mode[edit_mode_key] = (mode == "编辑")
                    
                    st.markdown('<div style="margin-bottom: 5px;"></div>', unsafe_allow_html=True)

                    content = chapter_info.get('content', '')
                    if content_key in st.session_state:
                        content = st.session_state[content_key]
                    
                    if st.session_state.content_edit_mode[edit_mode_key]:
                        content = st.text_area(
                            "正文内容",
                            value=content,
                            height=600,
                            key=content_key,
                            label_visibility="collapsed"
                        )
                    else:
                        with st.container(border=True):
                            st.markdown(content)
                
                with tab2:
                    outline = st.text_area(
                        "大纲内容",
                        value=chapter_info.get('outline', ''),
                        height=600,
                        key=f"outline_{chapter_num}",
                        label_visibility="collapsed"
                    )
                
                with tab3:
                    st.json(meta)
                    
                    if meta.get("character_states"):
                        st.subheader("人物状态")
                        for name, state in meta.get("character_states", {}).items():
                            appeared = "出现" if state.get('appeared', False) else "未出现"
                            st.write(f"- **{name}**: {appeared}")
                
                with tab4:
                    critique = chapter_info.get("critique", "")
                    critique_comments = meta.get("critique_comments", "")
                    critique_score = meta.get("critique_score", None)
                    
                    if critique_score is not None:
                        st.metric("审稿评分", f"{critique_score}分")
                    
                    if critique:
                        st.markdown("### 审稿意见")
                        st.markdown(critique)
                    elif critique_comments:
                        st.markdown("### 审稿意见")
                        st.markdown(critique_comments)
                    else:
                        st.info("暂无审稿意见")
                
                with tab5:
                    chapter_path = st.session_state.file_manager.get_chapter_path(novel_name, chapter_num)
                    assets_dir = chapter_path / "assets"
                    
                    # 样式调整，使按钮与正文模块的"编辑/预览"风格一致
                    st.markdown("""
                    <style>
                    div[data-testid="stRadio"] > div {
                        flex-direction: row !important;
                        gap: 20px !important;
                    }
                    .stRadio { margin-top: -15px; margin-bottom: -15px; }
                    </style>
                    """, unsafe_allow_html=True)
                    
                    c_mode, c_spacer = st.columns([2, 8], vertical_alignment="center")
                    
                    with c_mode:
                        if st.button("生成", key=f"generate_media_{chapter_num}", use_container_width=True):
                            try:
                                from src.workers.tasks import post_process_chapter_task
                                from celery.result import AsyncResult
                                
                                task = post_process_chapter_task.delay(novel_name, chapter_num)
                                
                                # 等待父任务完成并获取workflow_id
                                import time
                                max_wait = 5  # 最多等待5秒
                                start_time = time.time()
                                workflow_id = None
                                
                                while time.time() - start_time < max_wait:
                                    if task.ready():
                                        result = task.result
                                        if isinstance(result, dict) and 'workflow_id' in result:
                                            workflow_id = result['workflow_id']
                                            break
                                    time.sleep(0.1)
                                
                                # 追踪workflow_id（finalize任务）而不是父任务
                                task_key = f"media_{novel_name}_{chapter_num}"
                                track_task_id = workflow_id if workflow_id else task.id
                                
                                st.session_state.celery_tasks[task_key] = {
                                    "task_id": track_task_id,
                                    "novel_name": novel_name,
                                    "chapter_num": chapter_num,
                                    "status": "PROGRESS",
                                    "started_at": datetime.now(),
                                    "is_media_workflow": True  # 标记为多模态工作流
                                }
                                
                                st.toast(f"✅ 多模态任务已提交 | ID: {track_task_id[:16] if track_task_id else 'N/A'}...\n📍 前往 '5_任务监控助手' 查看进度", icon="🎨")
                                st.rerun()
                            except Exception as e:
                                st.error(f"提交任务失败: {e}")
                                import traceback
                                with st.expander("查看错误详情"):
                                    st.code(traceback.format_exc())
                    
                    st.markdown('<div style="margin-bottom: 15px;"></div>', unsafe_allow_html=True)
                    
                    image_path = assets_dir / "image.png"
                    audio_path = assets_dir / "audio.mp3"
                    
                    if image_path.exists():
                        st.subheader("🖼️ 场景插画")
                        st.image(str(image_path), caption=f"第{chapter_num}章场景插画")
                    else:
                        st.info("💡 暂无插画，点击上方按钮生成")
                    
                    st.divider()
                    
                    if audio_path.exists():
                        st.subheader("🎵 音频朗读")
                        st.audio(str(audio_path), format="audio/mp3")
                        file_size = audio_path.stat().st_size / 1024
                        st.caption(f"文件大小: {file_size:.1f} KB")
                    else:
                        st.info("💡 暂无音频，点击上方按钮生成")
        elif st.session_state.current_novel:
            st.info("请从中间栏选择章节查看")
        else:
            st.title("欢迎使用写作助手")
            st.markdown("""
            ### 使用说明
            
            1. **选择小说**：从左侧栏的小说列表中选择要编辑的小说
            2. **查看章节**：选择小说后，可以在中间栏查看所有章节
            3. **编辑内容**：点击章节后，可以在右侧编辑正文、大纲和标题
            4. **新建章节**：点击"➕ 新建章节"按钮，系统会自动生成新章节
            5. **保存修改**：编辑完成后，点击"💾 保存"按钮保存
            6. **重写章节**：如果对生成的内容不满意，可以输入修改意见后重写
            7. **风格管理**：在侧边栏导航中访问"🧠 Prompt Registry"页面管理提示词模板
            """)


def save_chapter(novel_name: str, chapter_num: int, title: Optional[str], content: Optional[str], outline: Optional[str]):
    from src.core.db_service import DatabaseService
    novel = DatabaseService.get_novel_by_title(novel_name)
    if not novel:
        raise ValueError(f"小说不存在：{novel_name}")
    if outline is not None:
        DatabaseService.save_outline(novel.id, chapter_num, outline)
    if content is not None:
        DatabaseService.save_content(novel.id, chapter_num, content)
    if title is not None:
        DatabaseService.update_chapter_title(novel.id, chapter_num, title)


def delete_chapter(novel_name: str, chapter_num: int):
    from src.core.db_service import DatabaseService
    novel = DatabaseService.get_novel_by_title(novel_name)
    if novel:
        DatabaseService.delete_chapter_by_index(novel.id, chapter_num)


if __name__ == "__main__":
    main()
