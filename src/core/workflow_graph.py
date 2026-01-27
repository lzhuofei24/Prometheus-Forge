"""
LangGraph 工作流图谱：带状态、可循环、可人工介入的编排。

替代硬编码路由，使用 StateGraph + NovelState；Checkpointer 持久化实现 Time Travel 基础。
节点封装现有 Architect/Writer/Critic/Censor/Knowledge Handler 为 Runnable。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.core.state import NovelState

logger = logging.getLogger(__name__)

# 可选：SqliteSaver 来自 langgraph-checkpoint-sqlite 或 langgraph 内置
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    _HAS_SQLITE_SAVER = True
except ImportError:
    try:
        from langgraph.checkpoint.memory import MemorySaver
        _HAS_SQLITE_SAVER = False
    except ImportError:
        MemorySaver = None  # type: ignore
        _HAS_SQLITE_SAVER = False


def _get_checkpointer(workflow_id: str = ""):
    """返回用于编译图谱的 checkpointer。优先 SQLite，否则内存。"""
    if _HAS_SQLITE_SAVER:
        db_path = Path("data/langgraph_checkpoints.sqlite")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        return SqliteSaver(conn)
    if MemorySaver is not None:
        return MemorySaver()
    return None


def _novel_state_to_legacy(s: Dict[str, Any]) -> Dict[str, Any]:
    """NovelState 转现有 state_manager 使用的字段名。"""
    out = {}
    if s.get("workflow_id"):
        out["workflow_id"] = s["workflow_id"]
    if s.get("novel_name") is not None:
        out["novel_name"] = s["novel_name"]
    if s.get("chapter_num") is not None:
        out["chapter_num"] = s["chapter_num"]
    if s.get("novel_id"):
        out["novel_id"] = s["novel_id"]
    if s.get("workflow_type"):
        out["workflow_type"] = s["workflow_type"]
    if s.get("outline") is not None:
        out["outline"] = s["outline"]
    if s.get("content") is not None:
        out["draft_content"] = s["content"]
    if s.get("draft_content") is not None:
        out["draft_content"] = s["draft_content"]
    if s.get("reference_context") is not None:
        out["reference_context"] = s["reference_context"]
    if s.get("revision_count") is not None:
        out["revision_count"] = s["revision_count"]
    if s.get("critique_score") is not None:
        out["score"] = s["critique_score"]
        out["critique_score"] = s["critique_score"]
    if s.get("is_sensitive") is not None:
        out["is_sensitive"] = s["is_sensitive"]
    out.setdefault("status", "running")
    return out


def _legacy_to_novel_updates(legacy: Dict[str, Any]) -> Dict[str, Any]:
    """state_manager 返回的 state 转为对 NovelState 的增量更新。"""
    u = {}
    if "outline" in legacy:
        u["outline"] = legacy["outline"]
    if "draft_content" in legacy:
        u["content"] = legacy["draft_content"]
        u["draft_content"] = legacy["draft_content"]
    if "revision_count" in legacy:
        u["revision_count"] = legacy["revision_count"]
    if "score" in legacy or "critique_score" in legacy:
        u["critique_score"] = legacy.get("critique_score") or legacy.get("score")
    if "critique_comments" in legacy:
        comments = legacy["critique_comments"]
        u["critique_comments"] = [comments] if isinstance(comments, str) else (comments or [])
    elif "comments" in legacy:
        comments = legacy["comments"]
        u["critique_comments"] = [comments] if isinstance(comments, str) else (comments or [])
    if "is_sensitive" in legacy:
        u["is_sensitive"] = legacy["is_sensitive"]
    if "context_summary" in legacy:
        u["context_summary"] = legacy["context_summary"]
    if "entities" in legacy:
        u["entities"] = legacy["entities"] if isinstance(legacy["entities"], list) else []
    if "status" in legacy:
        u["status"] = legacy["status"]
    return u


def _run_handler(
    workflow_id: str,
    agent_name: str,
    state: Dict[str, Any],
    input_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """将 NovelState 同步到 state_manager，执行对应 handler，再转回 NovelState 更新。"""
    from src.core.app_settings import get_settings
    from src.core.state_manager import StateManager
    from src.core.dispatcher import Dispatcher
    from src.core.llm import LLMClient
    from src.utils.file_manager import ProjectManager
    from src.core.config import Settings
    from pathlib import Path as P
    import os

    sm = StateManager(
        redis_host=get_settings().redis_host,
        redis_port=get_settings().redis_port,
        redis_db=get_settings().redis_db,
    )
    disp = Dispatcher(sm)
    legacy = _novel_state_to_legacy(state)
    legacy["workflow_type"] = legacy.get("workflow_type") or "generate_chapter"
    sm.update_state(workflow_id, legacy)

    project_root = P(__file__).resolve().parents[2]
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    file_manager = ProjectManager(P(config.paths.workspace))
    api_key = os.getenv(config.model.api_key_env or "OPENROUTER_API_KEY")
    llm = LLMClient(
        provider=config.model.provider,
        model=config.model.name,
        api_key=api_key or "",
        base_url=config.model.base_url,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        api_key_env=config.model.api_key_env,
    )

    if agent_name == "architect":
        from src.workers.handlers.architect import ArchitectHandler
        h = ArchitectHandler(sm, disp, llm, file_manager)
        out = h._process(workflow_id, input_data or {})
    elif agent_name == "writer":
        from src.workers.handlers.writer import WriterHandler
        h = WriterHandler(sm, disp, llm, file_manager)
        feedback = (state.get("user_feedback") or (input_data or {}).get("feedback"))
        out = h._process(workflow_id, {"feedback": feedback} if feedback else {})
    elif agent_name == "critic":
        from src.workers.handlers.critic import CriticHandler
        h = CriticHandler(sm, disp, llm, file_manager)
        out = h._process(workflow_id, input_data or {})
    elif agent_name == "censor":
        from src.workers.handlers.censor import CensorHandler
        h = CensorHandler(sm, disp, llm)
        out = h._process(workflow_id, {"content": state.get("content") or state.get("draft_content")})
    elif agent_name == "knowledge":
        from src.workers.handlers.knowledge import KnowledgeHandler
        h = KnowledgeHandler(sm, disp, llm, file_manager)
        out = h._process(workflow_id, {"chapter_content": state.get("content") or state.get("draft_content")})
    else:
        return {}

    sm.update_state(workflow_id, out)
    merged = sm.get_state(workflow_id)
    return _legacy_to_novel_updates(merged)


def _architect_node(state: NovelState) -> Dict[str, Any]:
    wid = state.get("workflow_id") or ""
    if not wid:
        return {"status": "failed", "next_step": ""}
    updates = _run_handler(wid, "architect", state, None)
    updates["next_step"] = "writer"
    return updates


def _writer_node(state: NovelState) -> Dict[str, Any]:
    wid = state.get("workflow_id") or ""
    if not wid:
        return {"status": "failed", "next_step": ""}
    updates = _run_handler(wid, "writer", state, None)
    updates["next_step"] = "censor"
    return updates


def _critic_node(state: NovelState) -> Dict[str, Any]:
    wid = state.get("workflow_id") or ""
    if not wid:
        return {"status": "failed", "next_step": ""}
    updates = _run_handler(wid, "critic", state, None)
    score = updates.get("critique_score") or state.get("critique_score") or 0
    rev = updates.get("revision_count", state.get("revision_count", 0))
    if score < 75 and rev < 3:
        updates["next_step"] = "writer"
        updates["revision_count"] = rev + 1
    else:
        updates["next_step"] = "censor"
    return updates


def _censor_node(state: NovelState) -> Dict[str, Any]:
    wid = state.get("workflow_id") or ""
    if not wid:
        return {"status": "failed", "next_step": ""}
    updates = _run_handler(wid, "censor", state, None)
    if updates.get("is_sensitive"):
        updates["next_step"] = "human_review"
    else:
        updates["next_step"] = "end"
        updates["status"] = "completed"
    return updates


def _human_review_node(state: NovelState) -> Dict[str, Any]:
    """敏感时挂起，等待人工反馈；resume 时 user_feedback 由 Command(resume=...) 注入。完成后直接结束，knowledge 仅通过索引管理手动触发。"""
    value = interrupt({
        "message": "内容敏感，需人工审核",
        "reason": state.get("censor_reason", ""),
        "content_preview": (state.get("content") or state.get("draft_content") or "")[:500],
    })
    return {"user_feedback": value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), "next_step": "__end__", "status": "completed"}


def _route_after_critic(state: NovelState) -> Literal["writer", "censor"]:
    score = state.get("critique_score") or 0
    rev = state.get("revision_count", 0)
    if score < 75 and rev < 3:
        return "writer"
    return "censor"


def _route_after_censor(state: NovelState) -> Literal["critic", "human_review", "end"]:
    """首次从 writer 进入 censor -> critic；从 critic 再进 censor 后按是否敏感 -> human_review | end。knowledge 已从工作流移除，仅通过索引管理手动触发。"""
    if state.get("critique_score") is not None and (state.get("critique_score") or 0) >= 75:
        if state.get("is_sensitive"):
            return "human_review"
        return "end"
    return "critic"


def build_novel_graph(checkpointer=None):
    """构建 开始 -> architect -> writer -> censor -> critic -> [writer|censor]；censor 再分支 -> [human_review|end] -> END。knowledge 不做为节点，仅通过「添加索引」等手动管理。"""
    workflow = StateGraph(dict)  # 使用 dict 兼容现有 NovelState 的 TypedDict 与任意字段

    workflow.add_node("architect", _architect_node)
    workflow.add_node("writer", _writer_node)
    workflow.add_node("censor", _censor_node)
    workflow.add_node("critic", _critic_node)
    workflow.add_node("human_review", _human_review_node)

    workflow.add_edge(START, "architect")
    workflow.add_edge("architect", "writer")
    workflow.add_edge("writer", "censor")
    workflow.add_conditional_edges("censor", _route_after_censor, {"critic": "critic", "human_review": "human_review", "end": END})
    workflow.add_conditional_edges("critic", _route_after_critic, {"writer": "writer", "censor": "censor"})
    workflow.add_edge("human_review", END)

    return workflow.compile(checkpointer=checkpointer)


_shared_checkpointer = None


def get_shared_checkpointer():
    """单例 checkpointer，供 API 的 history/resume 与 start 共用。"""
    global _shared_checkpointer
    if _shared_checkpointer is None:
        _shared_checkpointer = _get_checkpointer()
    return _shared_checkpointer


def get_graph(checkpointer=None):
    """返回已编译的图谱；thread_id 在 invoke 时通过 config[\"configurable\"][\"thread_id\"] 传入（通常取 workflow_id）。"""
    cp = checkpointer or get_shared_checkpointer()
    return build_novel_graph(checkpointer=cp)
