"""待审批写入：列表、详情（含目标位置现有内容）、通过、拒绝。"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel
from src.core.database import get_db
from src.api.services.approval_service import ApprovalService
from src.api.models import PendingWriteStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


class PendingItem(BaseModel):
    id: str
    write_type: str
    novel_id: str
    novel_title: str
    chapter_index: int
    workflow_id: Optional[str]
    source_agent: Optional[str]
    status: str
    created_at: Optional[str]
    payload_preview: str
    existing_has_summary: bool
    existing_has_content: bool
    existing_summary_preview: Optional[str]
    existing_content_preview: Optional[str]


class PendingDetail(BaseModel):
    id: str
    write_type: str
    novel_id: str
    novel_title: str
    chapter_index: int
    workflow_id: Optional[str]
    source_agent: Optional[str]
    status: str
    created_at: Optional[str]
    payload: dict
    existing_summary: Optional[str]
    existing_content: Optional[str]
    existing_critique_data: Optional[dict]


class WorkflowWithCount(BaseModel):
    workflow_id: str
    count: int


class WorkflowTypeWithCount(BaseModel):
    workflow_type: str
    count: int


@router.get("/workflow-types", response_model=List[WorkflowTypeWithCount])
async def list_workflow_types_with_pending(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """返回有待审批项的启动形式（workflow_type）及数量，用于审批助手最左侧「启动形式」层。"""
    rows = await ApprovalService.list_workflow_types_with_pending(db, status=status or "pending")
    return [WorkflowTypeWithCount(workflow_type=r["workflow_type"], count=r["count"]) for r in rows]


@router.get("/workflows", response_model=List[WorkflowWithCount])
async def list_workflows_with_pending(
    status: Optional[str] = None,
    workflow_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """返回有待审批项的工作流 id 及数量；可按 workflow_type（启动形式）筛选。"""
    rows = await ApprovalService.list_workflows_with_pending(
        db, status=status or "pending", workflow_type=workflow_type
    )
    return [WorkflowWithCount(workflow_id=r["workflow_id"], count=r["count"]) for r in rows]


@router.get("/pending", response_model=List[PendingItem])
async def list_pending(
    limit: int = 50,
    status: Optional[str] = None,
    workflow_id: Optional[str] = None,
    workflow_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """列出待审批写入；可按 workflow_type、workflow_id 筛选；不传 status 时默认只返回 pending。"""
    items = await ApprovalService.list_pending(
        db, limit=limit, status=status, workflow_id=workflow_id, workflow_type=workflow_type
    )
    return [PendingItem(**x) for x in items]


@router.get("/pending/{pending_id}", response_model=PendingDetail)
async def get_pending_detail(
    pending_id: str,
    db: AsyncSession = Depends(get_db),
):
    """单条待审批详情，含完整 payload 与目标位置当前内容。"""
    detail = await ApprovalService.get_pending_detail(db, pending_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Pending write not found")
    return PendingDetail(**detail)


@router.post("/pending/{pending_id}/approve", response_model=dict)
async def approve_pending(
    pending_id: str,
    db: AsyncSession = Depends(get_db),
):
    """通过：将待审批内容写入章节草稿并标记为已通过。"""
    result = await ApprovalService.approve(db, pending_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "approve failed"))
    return result


@router.post("/pending/{pending_id}/reject", response_model=dict)
async def reject_pending(
    pending_id: str,
    db: AsyncSession = Depends(get_db),
):
    """拒绝：仅将待审批标记为已拒绝，不写库。"""
    result = await ApprovalService.reject(db, pending_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "reject failed"))
    return result


@router.delete("/pending/{pending_id}", response_model=dict)
async def clear_pending(
    pending_id: str,
    db: AsyncSession = Depends(get_db),
):
    """清除审批请求：直接删除记录（无论状态如何）。"""
    result = await ApprovalService.clear(db, pending_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "clear failed"))
    return result


@router.delete("/pending/workflow/{workflow_id}", response_model=dict)
async def clear_pending_by_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
):
    """清除指定工作流的所有审批请求：直接删除所有相关记录（无论状态如何）。"""
    result = await ApprovalService.clear_by_workflow(db, workflow_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "clear failed"))
    return result
