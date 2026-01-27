from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime


class WorkflowStartRequest(BaseModel):
    novel_name: str
    chapter_num: int
    workflow_type: Optional[str] = None  # 工作流唯一标识，缺省为 generate_chapter
    novel_id: Optional[str] = None  # content_only/media_only 时用于查库，不传则按 novel_name 解析
    use_langgraph: Optional[bool] = False  # True 时用 LangGraph 编排（仅 generate_chapter），支持 history/resume


class WorkflowStateResponse(BaseModel):
    workflow_id: str
    novel_name: str
    chapter_num: int
    status: str
    outline: Optional[str] = None
    draft_content: Optional[str] = None
    critique_score: Optional[int] = None
    critique_comments: Optional[str] = None
    revision_count: int = 0
    created_at: Optional[str] = None


class AuditLogEntryResponse(BaseModel):
    timestamp: str
    workflow_id: str
    source: str
    event_type: str
    details: Dict[str, Any]
    task_id: Optional[str] = None
    error: Optional[str] = None


class WorkflowTraceResponse(BaseModel):
    workflow_id: str
    logs: List[AuditLogEntryResponse]


class WorkflowTaskItem(BaseModel):
    """按 workflow_type 列出的单条任务，用于写作助手等工作流启动区域展示。"""
    workflow_id: str
    novel_name: str
    chapter_num: int
    status: str
    created_at: Optional[str] = None
    current_node: str = ""  # 最近一条审计的 source 或 "system"，表示所处环节


class TokenStatsResponse(BaseModel):
    stats: Dict[str, Dict[str, Any]]


class WorkflowHistoryEntry(BaseModel):
    """LangGraph 状态快照历史中的单条。"""
    checkpoint_id: str
    metadata: Optional[Dict[str, Any]] = None
    values: Optional[Dict[str, Any]] = None  # 该时刻的 NovelState 摘要（outline/content/score 等）


class WorkflowResumeRequest(BaseModel):
    user_feedback: Optional[str] = None  # 从 human_review 恢复时传入的人工指令
