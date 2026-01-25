from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime


class WorkflowStartRequest(BaseModel):
    novel_name: str
    chapter_num: int
    workflow_type: Optional[str] = None  # 工作流唯一标识，缺省为 generate_chapter


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


class TokenStatsResponse(BaseModel):
    stats: Dict[str, Dict[str, Any]]
