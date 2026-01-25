from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EventType(str, Enum):
    WORKFLOW_STARTED = "workflow_started"
    TASK_DISPATCHED = "task_dispatched"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    OUTLINE_GENERATED = "outline_generated"
    CONTENT_WRITTEN = "content_written"
    CRITIQUE_COMPLETED = "critique_completed"
    CRITIQUE_FAILED = "critique_failed"
    REVISION_REQUESTED = "revision_requested"
    MEDIA_GENERATED = "media_generated"
    KNOWLEDGE_UPDATED = "knowledge_updated"
    CONTENT_CENSORED = "content_censored"


class EventSource(str, Enum):
    DISPATCHER = "dispatcher"
    AGENT_WRITER = "agent_writer"
    AGENT_CRITIC = "agent_critic"
    AGENT_ARCHITECT = "agent_architect"
    AGENT_MEDIA = "agent_media"
    AGENT_KNOWLEDGE = "agent_knowledge"
    AGENT_CENSOR = "agent_censor"
    SYSTEM = "system"


class AuditLogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    workflow_id: str
    source: EventSource
    event_type: EventType
    details: Dict[str, Any] = Field(default_factory=dict)
    task_id: Optional[str] = None
    error: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EventPayload(BaseModel):
    workflow_id: str
    event_type: EventType
    data: Dict[str, Any] = Field(default_factory=dict)
    source: EventSource
    task_id: Optional[str] = None

    class Config:
        use_enum_values = True
