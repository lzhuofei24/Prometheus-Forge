"""
LangGraph Nodes 适配器

将现有的 Agent Handlers 封装为 LangGraph 的异步 Nodes。
每个 Node 负责：
1. 从 WorkflowState 提取输入数据
2. 调用 Handler 的核心处理逻辑（_process 方法）
3. 将处理结果合并回 WorkflowState
4. 错误处理和状态更新
"""
import logging
import asyncio
from typing import Dict, Any
from datetime import datetime

from src.workflow.state import WorkflowState
from src.workers.handlers.architect import ArchitectHandler
from src.workers.handlers.writer import WriterHandler
from src.workers.handlers.critic import CriticHandler
from src.workers.handlers.censor import CensorHandler
from src.workers.handlers.media import MediaHandler
from src.core.state_manager import StateManager
from src.core.dispatcher import Dispatcher
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager
from src.core.app_settings import get_settings
from src.core.config import Settings
from pathlib import Path

logger = logging.getLogger(__name__)

# 全局组件缓存（避免重复初始化）
_state_manager: StateManager = None
_dispatcher: Dispatcher = None
_llm_client: LLMClient = None
_file_manager: ProjectManager = None


def _init_components():
    """延迟初始化全局组件"""
    global _state_manager, _dispatcher, _llm_client, _file_manager
    
    if _state_manager is None:
        settings = get_settings()
        _state_manager = StateManager(
            redis_host=settings.redis_host,
            redis_port=settings.redis_port,
            redis_db=settings.redis_db
        )
    
    if _dispatcher is None:
        _dispatcher = Dispatcher(_state_manager)
    
    if _llm_client is None:
        project_root = Path(__file__).parent.parent.parent
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        
        import os
        from dotenv import load_dotenv
        load_dotenv(project_root / ".env")
        
        api_key = None
        if hasattr(config.model, 'api_key_env') and config.model.api_key_env:
            api_key = os.getenv(config.model.api_key_env)
        elif config.model.provider == "siliconflow":
            api_key = os.getenv("SILICONFLOW_API_KEY")
        elif config.model.provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
        else:
            api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            raise ValueError("API Key 未设置！请在 .env 文件中设置相应的 API Key")
        
        base_url = getattr(config.model, 'base_url', None)
        site_url = None
        app_name = None
        if hasattr(config, 'llm') and config.llm:
            site_url = config.llm.get('site_url')
            app_name = config.llm.get('app_name')
        
        _llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            api_key=api_key,
            base_url=base_url,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            api_key_env=getattr(config.model, 'api_key_env', None),
            site_url=site_url,
            app_name=app_name
        )
    
    if _file_manager is None:
        project_root = Path(__file__).parent.parent.parent
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        _file_manager = ProjectManager(Path(config.paths.workspace))
    
    return _state_manager, _dispatcher, _llm_client, _file_manager


class StateAdapter:
    """
    状态适配器：将 WorkflowState 转换为 Handler 期望的格式
    
    Handler 的 _process 方法需要 workflow_id 和 input_data，
    并且会调用 self.state_manager.get_state(workflow_id) 和 update_state。
    这个适配器提供一个临时的 state_manager，将 WorkflowState 映射为 Redis 状态格式，
    并收集 Handler 中的状态更新。
    """
    
    def __init__(self, state: WorkflowState, real_state_manager: StateManager):
        self.state = state
        self.real_state_manager = real_state_manager
        self.workflow_id = state.get("workflow_id", "")
        self.pending_updates: Dict[str, Any] = {}  # 收集 Handler 中的状态更新
    
    def get_state(self, workflow_id: str) -> Dict[str, Any]:
        """返回适配后的状态（从 WorkflowState 转换）"""
        # 将 WorkflowState 转换为 Handler 期望的格式
        return {
            "novel_name": self.state.get("novel_name", ""),
            "chapter_num": self.state.get("chapter_num", 0),
            "workflow_type": self.state.get("workflow_type", "generate_chapter"),
            "outline": self.state.get("outline"),
            "draft_content": self.state.get("draft_content"),
            "reference_context": self.state.get("reference_context"),
            "critique_score": self.state.get("critique_score"),
            "critique_comments": self.state.get("critique_comments"),
            "revision_count": self.state.get("revision_count", 0),
            "is_sensitive": self.state.get("is_sensitive"),
            "censor_result": self.state.get("censor_result"),
            "feedback": self.state.get("feedback"),
        }
    
    def update_state(self, workflow_id: str, updates: Dict[str, Any]):
        """收集状态更新（在 Node 中会应用到 WorkflowState）"""
        # 收集 Handler 中的状态更新，稍后在 Node 中合并回 WorkflowState
        self.pending_updates.update(updates)


async def architect_node(state: WorkflowState) -> WorkflowState:
    """
    Architect Node: 生成章节大纲
    
    从 WorkflowState 提取 novel_name 和 chapter_num，
    调用 ArchitectHandler._process 生成大纲，
    将结果合并回 WorkflowState。
    """
    try:
        state_manager, dispatcher, llm_client, file_manager = _init_components()
        
        # 创建适配器
        adapter = StateAdapter(state, state_manager)
        
        # 创建 Handler（使用适配器作为临时 state_manager）
        handler = ArchitectHandler(adapter, dispatcher, llm_client, file_manager)
        
        # 准备输入数据
        input_data = {
            "novel_name": state.get("novel_name"),
            "chapter_num": state.get("chapter_num")
        }
        
        # 调用核心处理逻辑（在线程池中执行，因为 LLM 调用是同步的）
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            handler._process,
            state.get("workflow_id", ""),
            input_data
        )
        
        # 将结果合并回 state（包括 Handler 中的状态更新）
        state["outline"] = result.get("outline")
        # 应用 adapter 收集的更新（如 reference_context）
        if adapter.pending_updates:
            state.update(adapter.pending_updates)
        state["reference_context"] = result.get("reference_context") or state.get("reference_context") or adapter.pending_updates.get("reference_context")
        state["current_agent"] = "architect"
        state["status"] = "processing"
        state["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"[Architect Node] 大纲生成完成，workflow_id={state.get('workflow_id')}")
        return state
        
    except Exception as e:
        logger.error(f"[Architect Node] 执行失败: {e}", exc_info=True)
        state["status"] = "failed"
        state["error"] = str(e)
        state["current_agent"] = "architect"
        import traceback
        state["error_traceback"] = traceback.format_exc()
        return state


async def writer_node(state: WorkflowState) -> WorkflowState:
    """
    Writer Node: 生成章节正文
    
    支持两种模式：
    1. 首次生成：使用 outline 生成正文
    2. 修订模式：使用 feedback 修订已有正文
    """
    try:
        state_manager, dispatcher, llm_client, file_manager = _init_components()
        
        adapter = StateAdapter(state, state_manager)
        handler = WriterHandler(adapter, dispatcher, llm_client, file_manager)
        
        # 准备输入数据
        input_data = {}
        if state.get("feedback") or state.get("revision_count", 0) > 0:
            # 修订模式
            input_data["feedback"] = state.get("feedback") or state.get("critique_comments", "")
        
        # 调用核心处理逻辑
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            handler._process,
            state.get("workflow_id", ""),
            input_data
        )
        
        # 将结果合并回 state（Writer 返回的是 "content" 字段，需要映射到 "draft_content"）
        content = result.get("draft_content") or result.get("content")
        if content:
            state["draft_content"] = content
        # 应用 adapter 收集的更新
        if adapter.pending_updates:
            state.update(adapter.pending_updates)
        state["current_agent"] = "writer"
        state["status"] = "processing"
        state["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"[Writer Node] 正文生成完成，workflow_id={state.get('workflow_id')}")
        return state
        
    except Exception as e:
        logger.error(f"[Writer Node] 执行失败: {e}", exc_info=True)
        state["status"] = "failed"
        state["error"] = str(e)
        state["current_agent"] = "writer"
        import traceback
        state["error_traceback"] = traceback.format_exc()
        return state


async def censor_node(state: WorkflowState) -> WorkflowState:
    """
    Censor Node: 敏感内容审查
    
    检查 draft_content 是否包含敏感内容。
    """
    try:
        state_manager, dispatcher, llm_client, _ = _init_components()
        
        adapter = StateAdapter(state, state_manager)
        handler = CensorHandler(adapter, dispatcher, llm_client)
        
        # 准备输入数据
        input_data = {
            "content": state.get("draft_content", "")
        }
        
        # 调用核心处理逻辑
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            handler._process,
            state.get("workflow_id", ""),
            input_data
        )
        
        # 将结果合并回 state
        state["is_sensitive"] = result.get("is_sensitive", False)
        state["censor_result"] = result
        state["censor_reason"] = result.get("reason", "")
        # 应用 adapter 收集的更新
        if adapter.pending_updates:
            state.update(adapter.pending_updates)
        state["current_agent"] = "censor"
        state["status"] = "processing"
        state["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"[Censor Node] 审查完成，is_sensitive={state['is_sensitive']}, workflow_id={state.get('workflow_id')}")
        return state
        
    except Exception as e:
        logger.error(f"[Censor Node] 执行失败: {e}", exc_info=True)
        state["status"] = "failed"
        state["error"] = str(e)
        state["current_agent"] = "censor"
        import traceback
        state["error_traceback"] = traceback.format_exc()
        return state


async def critic_node(state: WorkflowState) -> WorkflowState:
    """
    Critic Node: 内容质量审稿
    
    对 draft_content 进行评分（0-100），并提供改进建议。
    评分 < 75 时会触发修订流程。
    """
    try:
        state_manager, dispatcher, llm_client, file_manager = _init_components()
        
        adapter = StateAdapter(state, state_manager)
        handler = CriticHandler(adapter, dispatcher, llm_client, file_manager)
        
        # 准备输入数据（Critic 通常不需要额外输入）
        input_data = {}
        
        # 调用核心处理逻辑
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            handler._process,
            state.get("workflow_id", ""),
            input_data
        )
        
        # 将结果合并回 state
        state["critique_score"] = result.get("score") or result.get("critique_score")
        state["critique_comments"] = result.get("comments") or result.get("critique_comments") or result.get("advice")
        state["advice"] = result.get("advice") or state.get("critique_comments")
        # 应用 adapter 收集的更新
        if adapter.pending_updates:
            state.update(adapter.pending_updates)
        state["current_agent"] = "critic"
        state["status"] = "processing"
        state["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"[Critic Node] 审稿完成，score={state['critique_score']}, workflow_id={state.get('workflow_id')}")
        return state
        
    except Exception as e:
        logger.error(f"[Critic Node] 执行失败: {e}", exc_info=True)
        state["status"] = "failed"
        state["error"] = str(e)
        state["current_agent"] = "critic"
        import traceback
        state["error_traceback"] = traceback.format_exc()
        return state


async def media_node(state: WorkflowState) -> WorkflowState:
    """
    Media Node: 生成章节配图
    
    根据 draft_content 或 outline 生成配图。
    """
    try:
        state_manager, dispatcher, llm_client, file_manager = _init_components()
        
        adapter = StateAdapter(state, state_manager)
        handler = MediaHandler(adapter, dispatcher, llm_client, file_manager)
        
        # 准备输入数据
        input_data = {
            "chapter_content": state.get("draft_content", ""),
            "scene_description": state.get("outline", "")  # 如果没有正文，使用大纲
        }
        
        # 调用核心处理逻辑
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            handler._process,
            state.get("workflow_id", ""),
            input_data
        )
        
        # 将结果合并回 state
        state["media_generated"] = True
        state["media_url"] = result.get("image_url")
        # 应用 adapter 收集的更新
        if adapter.pending_updates:
            state.update(adapter.pending_updates)
        state["current_agent"] = "media"
        state["status"] = "processing"
        state["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"[Media Node] 配图生成完成，workflow_id={state.get('workflow_id')}")
        return state
        
    except Exception as e:
        logger.error(f"[Media Node] 执行失败: {e}", exc_info=True)
        state["status"] = "failed"
        state["error"] = str(e)
        state["current_agent"] = "media"
        import traceback
        state["error_traceback"] = traceback.format_exc()
        return state
