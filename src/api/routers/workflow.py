import uuid
from fastapi import APIRouter, HTTPException
from datetime import datetime
from src.api.schemas.workflow import (
    WorkflowStartRequest,
    WorkflowStateResponse,
    WorkflowTraceResponse,
    AuditLogEntryResponse
)
from src.core.state_manager import StateManager
from src.core.dispatcher import Dispatcher
from src.core.events import EventType, EventSource, EventPayload, AuditLogEntry
from src.core.celery_config import celery_app
from src.core.app_settings import get_settings
from src.core.workflows import DEFAULT_WORKFLOW_ID, list_workflows

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.get("/types", response_model=list)
async def get_workflow_types():
    """返回已注册工作流列表（id、name），供工作流助手切换使用。"""
    return list_workflows()

_settings = get_settings()
state_manager = StateManager(
    redis_host=_settings.redis_host,
    redis_port=_settings.redis_port,
    redis_db=_settings.redis_db,
)
dispatcher = Dispatcher(state_manager)


@router.post("/start", response_model=dict)
async def start_workflow(request: WorkflowStartRequest):
    import logging
    logger = logging.getLogger(__name__)
    
    workflow_id = str(uuid.uuid4())
    workflow_type = (request.workflow_type or "").strip() or DEFAULT_WORKFLOW_ID

    try:
        state_manager.init_workflow(workflow_id, {
            "novel_name": request.novel_name,
            "chapter_num": request.chapter_num,
            "status": "started",
            "revision_count": 0,
            "workflow_type": workflow_type,
        })
        
        state_manager.add_audit_log(
            workflow_id,
            AuditLogEntry(
                workflow_id=workflow_id,
                source=EventSource.SYSTEM,
                event_type=EventType.WORKFLOW_STARTED,
                details={
                    "novel_name": request.novel_name,
                    "chapter_num": request.chapter_num
                }
            )
        )
        
        event_payload = EventPayload(
            workflow_id=workflow_id,
            event_type=EventType.WORKFLOW_STARTED,
            data={
                "novel_name": request.novel_name,
                "chapter_num": request.chapter_num,
                "workflow_type": workflow_type,
            },
            source=EventSource.SYSTEM
        )
        dispatcher.handle_event(event_payload)
        
        # 发送任务到 architect_pending 队列（与 celery_config 一致）
        try:
            result = celery_app.send_task(
                "architect.generate_outline",
                queue="architect_pending",
                args=[workflow_id, request.novel_name, request.chapter_num]
            )
            # 入队后立刻读取长度，便于前端/监控确认任务已进入队列。
            # 若 Architect 已禁用但仍为 0：Worker 仍会 BRPOP 取走消息，在任务体内才检查禁用并 retry，
            # 取走瞬间队列已空，故要看到 Pending 堆积需停掉 Architect 进程而非仅禁用。
            architect_pending_after = state_manager.redis_client.llen("architect_pending")
            logger.info(
                f"Task sent to queue: {result.id}, workflow_id: {workflow_id}, "
                f"queue=architect_pending, llen_after={architect_pending_after}"
            )
        except Exception as e:
            logger.error(f"Failed to send task to queue: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to send task to queue: {str(e)}")
        
        return {
            "workflow_id": workflow_id,
            "status": "started",
            "task_id": result.id,
            "architect_pending_after_send": architect_pending_after,
        }
    except Exception as e:
        logger.error(f"Failed to start workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")


@router.get("/{workflow_id}/state", response_model=WorkflowStateResponse)
async def get_workflow_state(workflow_id: str):
    state = state_manager.get_state(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    created_at = state_manager.redis_client.get(f"workflow:{workflow_id}:created_at")
    
    return WorkflowStateResponse(
        workflow_id=workflow_id,
        novel_name=state.get("novel_name", ""),
        chapter_num=state.get("chapter_num", 0),
        status=state.get("status", "unknown"),
        outline=state.get("outline"),
        draft_content=state.get("draft_content"),
        critique_score=state.get("critique_score"),
        critique_comments=state.get("critique_comments"),
        revision_count=state.get("revision_count", 0),
        created_at=created_at
    )


@router.get("/{workflow_id}/trace", response_model=WorkflowTraceResponse)
async def get_workflow_trace(workflow_id: str):
    logs = state_manager.get_workflow_trace(workflow_id)
    
    log_responses = []
    for log in logs:
        timestamp = log.get("timestamp")
        if isinstance(timestamp, datetime):
            timestamp_str = timestamp.isoformat()
        elif isinstance(timestamp, str):
            timestamp_str = timestamp
        else:
            timestamp_str = datetime.now().isoformat()
        
        log_responses.append(
            AuditLogEntryResponse(
                timestamp=timestamp_str,
                workflow_id=log.get("workflow_id", ""),
                source=log.get("source", ""),
                event_type=log.get("event_type", ""),
                details=log.get("details", {}),
                task_id=log.get("task_id"),
                error=log.get("error")
            )
        )
    
    return WorkflowTraceResponse(
        workflow_id=workflow_id,
        logs=log_responses
    )
