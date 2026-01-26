import json
import logging
import uuid
from fastapi import APIRouter, HTTPException, Query, Depends
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.schemas.workflow import (
    WorkflowStartRequest,
    WorkflowStateResponse,
    WorkflowTraceResponse,
    AuditLogEntryResponse,
    WorkflowTaskItem,
)
from src.core.state_manager import StateManager
from src.core.dispatcher import Dispatcher
from src.core.events import EventType, EventSource, EventPayload, AuditLogEntry
from src.core.celery_config import celery_app
from src.core.app_settings import get_settings
from src.core.workflows import (
    DEFAULT_WORKFLOW_ID,
    list_workflows,
    WORKFLOW_CONTENT_ONLY,
    WORKFLOW_MEDIA_ONLY,
)
from src.core.database import get_db
from src.api.models import Novel, Chapter, ChapterDraft
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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


@router.get("/tasks", response_model=list)
async def list_workflow_tasks(
    workflow_type: str = Query(..., description="工作流类型，如 generate_chapter、outline_only"),
):
    """按工作流类型列出该类型下所有任务（含 workflow_id、任务内容、状态、所处节点）。"""
    wt = (workflow_type or "").strip() or DEFAULT_WORKFLOW_ID
    ids = state_manager.list_workflow_ids_by_type(wt)
    out = []
    for wid in ids:
        state = state_manager.get_state(wid)
        if not state:
            continue
        created = state_manager.redis_client.get(f"workflow:{wid}:created_at")
        logs = state_manager.get_workflow_trace(wid)
        last_source = (logs[-1].get("source") or "system") if logs else "system"
        out.append(
            WorkflowTaskItem(
                workflow_id=wid,
                novel_name=state.get("novel_name", ""),
                chapter_num=state.get("chapter_num", 0),
                status=state.get("status", "unknown"),
                created_at=created,
                current_node=last_source,
            )
        )
    return out


async def _resolve_novel_id_and_chapter(
    db: AsyncSession, novel_name: str, chapter_num: int, novel_id: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """返回 (novel_id, chapter_id)。novel_id 优先用入参，否则按 novel_name 查。"""
    nid = novel_id
    if not nid:
        r = await db.execute(select(Novel.id).where(Novel.title == novel_name).limit(1))
        nid = r.scalar_one_or_none()
    if not nid:
        return None, None
    r = await db.execute(
        select(Chapter.id).where(
            Chapter.novel_id == nid, Chapter.index == chapter_num
        ).limit(1)
    )
    cid = r.scalar_one_or_none()
    return nid, cid


@router.post("/start", response_model=dict)
async def start_workflow(request: WorkflowStartRequest, db: AsyncSession = Depends(get_db)):
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
                    "chapter_num": request.chapter_num,
                },
            ),
        )
        event_payload = EventPayload(
            workflow_id=workflow_id,
            event_type=EventType.WORKFLOW_STARTED,
            data={
                "novel_name": request.novel_name,
                "chapter_num": request.chapter_num,
                "workflow_type": workflow_type,
            },
            source=EventSource.SYSTEM,
        )
        dispatcher.handle_event(event_payload)

        if workflow_type == WORKFLOW_CONTENT_ONLY:
            nid, cid = await _resolve_novel_id_and_chapter(
                db, request.novel_name, request.chapter_num, request.novel_id
            )
            if not cid:
                raise HTTPException(
                    status_code=400,
                    detail="仅生成正文需要已存在章节且有大纲，请先创建章节并生成大纲，或传入 novel_id",
                )
            ch = await db.execute(
                select(Chapter).where(Chapter.id == cid).options(
                    selectinload(Chapter.drafts)
                )
            )
            chapter = ch.scalar_one_or_none()
            summary = None
            if chapter and chapter.drafts:
                active = next((d for d in chapter.drafts if d.is_active), chapter.drafts[0])
                summary = active.summary if active else None
            if not summary or not str(summary).strip():
                raise HTTPException(
                    status_code=400,
                    detail="仅生成正文需要该章节已有大纲，请先运行「仅生成大纲」或手动填写大纲",
                )
            state_manager.update_state(workflow_id, {"outline": summary})
            result = celery_app.send_task(
                "writer.write_content",
                queue="writer_pending",
                args=[workflow_id],
            )
            queue_after = state_manager.redis_client.llen("writer_pending")
            return {
                "workflow_id": workflow_id,
                "status": "started",
                "task_id": result.id,
                "architect_pending_after_send": queue_after,
            }

        if workflow_type == WORKFLOW_MEDIA_ONLY:
            nid, cid = await _resolve_novel_id_and_chapter(
                db, request.novel_name, request.chapter_num, request.novel_id
            )
            if not cid:
                raise HTTPException(
                    status_code=400,
                    detail="仅生成媒体需要已存在章节，请先创建章节或传入 novel_id",
                )
            ch = await db.execute(
                select(Chapter).where(Chapter.id == cid).options(
                    selectinload(Chapter.drafts)
                )
            )
            chapter = ch.scalar_one_or_none()
            content = None
            if chapter and chapter.drafts:
                active = next((d for d in chapter.drafts if d.is_active), chapter.drafts[0])
                content = active.content if active else None
            state_manager.update_state(workflow_id, {"draft_content": content or ""})
            result = celery_app.send_task(
                "media.generate_media",
                queue="media_pending",
                args=[workflow_id],
            )
            queue_after = state_manager.redis_client.llen("media_pending")
            return {
                "workflow_id": workflow_id,
                "status": "started",
                "task_id": result.id,
                "architect_pending_after_send": queue_after,
            }

        # generate_chapter / outline_only / approval_only 等：发 architect
        result = celery_app.send_task(
            "architect.generate_outline",
            queue="architect_pending",
            args=[workflow_id, request.novel_name, request.chapter_num],
        )
        architect_pending_after = state_manager.redis_client.llen("architect_pending")
        logger.info(
            "Task sent to queue: %s, workflow_id: %s, queue=architect_pending, llen_after=%s",
            result.id, workflow_id, architect_pending_after,
        )
        return {
            "workflow_id": workflow_id,
            "status": "started",
            "task_id": result.id,
            "architect_pending_after_send": architect_pending_after,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start workflow: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start workflow: {str(e)}")


@router.get("/{workflow_id}/state", response_model=WorkflowStateResponse)
async def get_workflow_state(workflow_id: str):
    state = state_manager.get_state(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    created_at = state_manager.redis_client.get(f"workflow:{workflow_id}:created_at")
    outline_raw = state.get("outline")
    outline_str = (
        outline_raw if isinstance(outline_raw, str) else
        json.dumps(outline_raw, ensure_ascii=False) if outline_raw is not None else None
    )
    return WorkflowStateResponse(
        workflow_id=workflow_id,
        novel_name=state.get("novel_name", ""),
        chapter_num=state.get("chapter_num", 0),
        status=state.get("status", "unknown"),
        outline=outline_str,
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
