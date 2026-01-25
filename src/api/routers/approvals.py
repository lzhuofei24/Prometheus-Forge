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


@router.get("/pending", response_model=List[PendingItem])
async def list_pending(
    limit: int = 50,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """列出待审批写入；不传 status 时默认只返回 pending。"""
    items = await ApprovalService.list_pending(db, limit=limit, status=status)
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
