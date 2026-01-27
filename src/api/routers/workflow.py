import asyncio
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
    WorkflowHistoryEntry,
    WorkflowResumeRequest,
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
    WORKFLOW_GENERATE_CHAPTER,
)
from src.core.database import get_db
from src.api.models import Novel, Chapter, ChapterDraft
from typing import Optional, Tuple, List
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


def _tasks_for_type(wt: str):
    wt = (wt or "").strip() or DEFAULT_WORKFLOW_ID
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


@router.get("/tasks/batch", response_model=dict)
async def list_workflow_tasks_batch(
    workflow_types: str = Query(..., description="逗号分隔的多个类型，如 generate_chapter,outline_only,content_only"),
):
    """批量按类型返回任务，写作页一次请求拉取全部。返回 { workflow_type: WorkflowTaskItem[] }。"""
    types_list = [s.strip() for s in (workflow_types or "").split(",") if s.strip()]
    result = {}
    for wt in types_list:
        result[wt] = _tasks_for_type(wt)
    return result


@router.get("/tasks", response_model=list)
async def list_workflow_tasks(
    workflow_type: str = Query(..., description="工作流类型，如 generate_chapter、outline_only"),
):
    """按工作流类型列出该类型下所有任务（含 workflow_id、任务内容、状态、所处节点）。"""
    return _tasks_for_type(workflow_type)


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

        # use_langgraph 且 generate_chapter：用 LangGraph 同步编排，支持 history/resume
        if getattr(request, "use_langgraph", False) and workflow_type == WORKFLOW_GENERATE_CHAPTER:
            from src.core.workflow_graph import get_graph

            initial: dict = {
                "workflow_id": workflow_id,
                "novel_name": request.novel_name,
                "chapter_num": request.chapter_num,
                "novel_id": request.novel_id or "",
                "chapter_index": request.chapter_num,
                "workflow_type": workflow_type,
                "outline": None,
                "content": None,
                "draft_content": None,
                "critique_score": None,
                "critique_comments": [],
                "revision_count": 0,
                "is_sensitive": False,
                "context_summary": "",
                "entities": [],
                "next_step": "",
                "user_feedback": None,
                "status": "started",
            }
            config = {"configurable": {"thread_id": workflow_id}}
            graph = get_graph()

            def _run():
                return graph.invoke(initial, config=config)

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _run)
            out = {"workflow_id": workflow_id, "status": result.get("status", "completed")}
            if "__interrupt__" in result:
                out["status"] = "interrupted"
                out["__interrupt__"] = result["__interrupt__"]
            state_manager.update_state(workflow_id, result)
            return out

        # generate_chapter / outline_only / approval_only 等：发 architect（Celery）
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


@router.get("/{workflow_id}/history", response_model=list)
async def get_workflow_history(
    workflow_id: str,
    limit: int = Query(50, ge=1, le=200, description="返回最近 N 个快照"),
):
    """LangGraph Checkpointer 中的状态快照历史，用于时光机。"""
    try:
        from src.core.workflow_graph import get_shared_checkpointer
        cp = get_shared_checkpointer()
        config = {"configurable": {"thread_id": workflow_id}}
        entries = []

        def _list():
            out = []
            for t in cp.list(config, limit=limit):
                cid = ""
                meta = {}
                v = {}
                try:
                    if hasattr(t, "config"):
                        cid = str((t.config.get("configurable") or {}).get("checkpoint_id", ""))
                    if hasattr(t, "metadata"):
                        meta = t.metadata if isinstance(t.metadata, dict) else {}
                    chk = getattr(t, "checkpoint", None)
                    if chk:
                        cv = chk.get("channel_values") if hasattr(chk, "get") else getattr(chk, "channel_values", None)
                        if cv and hasattr(cv, "items"):
                            v = dict(cv)
                except Exception:
                    pass
                out.append(WorkflowHistoryEntry(checkpoint_id=cid, metadata=meta, values=v or None))
            return out

        loop = asyncio.get_event_loop()
        entries = await loop.run_in_executor(None, _list)
        return entries
    except Exception as e:
        logger.warning("get_workflow_history failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/resume", response_model=dict)
async def resume_workflow(workflow_id: str, body: WorkflowResumeRequest):
    """从 human_review 节点恢复，传入 user_feedback。"""
    try:
        from src.core.workflow_graph import get_graph
        from langgraph.types import Command

        config = {"configurable": {"thread_id": workflow_id}}
        graph = get_graph()

        def _run():
            return graph.invoke(Command(resume=body.user_feedback or ""), config=config)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run)
        state_manager.update_state(workflow_id, result)
        out = {"workflow_id": workflow_id, "status": result.get("status", "completed")}
        if "__interrupt__" in result:
            out["status"] = "interrupted"
            out["__interrupt__"] = result["__interrupt__"]
        return out
    except Exception as e:
        logger.error("resume_workflow failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
