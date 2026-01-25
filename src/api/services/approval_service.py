"""待审批写入：列出、查看目标位置现有内容、通过/拒绝。"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
from src.api.models import (
    Novel,
    Chapter,
    ChapterDraft,
    PendingWrite,
    PendingWriteStatus,
    ChapterStatus,
)


class ApprovalService:
    @staticmethod
    async def list_pending(
        db: AsyncSession,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q = (
            select(PendingWrite, Novel.title)
            .join(Novel, Novel.id == PendingWrite.novel_id)
            .where(PendingWrite.status == (status or PendingWriteStatus.PENDING.value))
            .order_by(PendingWrite.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(q)
        rows = result.all()
        out = []
        for pw, novel_title in rows:
            # 目标位置是否已有内容
            ch = await db.execute(
                select(Chapter)
                .where(
                    and_(
                        Chapter.novel_id == pw.novel_id,
                        Chapter.index == pw.chapter_index,
                    )
                )
                .options(selectinload(Chapter.drafts))
            )
            chapter = ch.scalar_one_or_none()
            existing_summary = None
            existing_content = None
            if chapter:
                active = next((d for d in chapter.drafts if d.is_active), None)
                if active:
                    existing_summary = active.summary
                    existing_content = active.content
            payload = pw.payload or {}
            preview = ""
            if pw.write_type == "outline":
                preview = (payload.get("summary") or "")[:500]
            else:
                preview = (payload.get("content") or "")[:500]
            out.append({
                "id": pw.id,
                "write_type": pw.write_type,
                "novel_id": pw.novel_id,
                "novel_title": novel_title,
                "chapter_index": pw.chapter_index,
                "workflow_id": pw.workflow_id,
                "source_agent": pw.source_agent,
                "status": pw.status,
                "created_at": pw.created_at.isoformat() if pw.created_at else None,
                "payload_preview": preview,
                "existing_has_summary": bool(existing_summary),
                "existing_has_content": bool(existing_content),
                "existing_summary_preview": (existing_summary or "")[:200] if existing_summary else None,
                "existing_content_preview": (existing_content or "")[:200] if existing_content else None,
            })
        return out

    @staticmethod
    async def get_pending_detail(
        db: AsyncSession,
        pending_id: str,
    ) -> Optional[Dict[str, Any]]:
        r = await db.execute(
            select(PendingWrite, Novel.title).join(
                Novel, Novel.id == PendingWrite.novel_id
            ).where(PendingWrite.id == pending_id)
        )
        row = r.one_or_none()
        if not row:
            return None
        pw, novel_title = row
        ch = await db.execute(
            select(Chapter)
            .where(
                and_(
                    Chapter.novel_id == pw.novel_id,
                    Chapter.index == pw.chapter_index,
                )
            )
            .options(selectinload(Chapter.drafts))
        )
        chapter = ch.scalar_one_or_none()
        existing_summary = None
        existing_content = None
        existing_critique_data = None
        if chapter:
            active = next((d for d in chapter.drafts if d.is_active), None)
            if active:
                existing_summary = active.summary
                existing_content = active.content
                existing_critique_data = active.critique_data
        return {
            "id": pw.id,
            "write_type": pw.write_type,
            "novel_id": pw.novel_id,
            "novel_title": novel_title,
            "chapter_index": pw.chapter_index,
            "workflow_id": pw.workflow_id,
            "source_agent": pw.source_agent,
            "status": pw.status,
            "created_at": pw.created_at.isoformat() if pw.created_at else None,
            "payload": pw.payload,
            "existing_summary": existing_summary,
            "existing_content": existing_content,
            "existing_critique_data": existing_critique_data,
        }

    @staticmethod
    async def approve(db: AsyncSession, pending_id: str) -> Dict[str, Any]:
        r = await db.execute(
            select(PendingWrite).where(
                and_(
                    PendingWrite.id == pending_id,
                    PendingWrite.status == PendingWriteStatus.PENDING.value,
                )
            )
        )
        pw = r.scalar_one_or_none()
        if not pw:
            return {"success": False, "error": "pending not found or already processed"}
        payload = pw.payload or {}
        chapter = (
            await db.execute(
                select(Chapter)
                .where(
                    and_(
                        Chapter.novel_id == pw.novel_id,
                        Chapter.index == pw.chapter_index,
                    )
                )
            )
        ).scalar_one_or_none()
        if not chapter:
            from src.api.services.novel_service import NovelService
            chapter = await NovelService.create_chapter(
                db, pw.novel_id, pw.chapter_index, None
            )
            await db.flush()
        result = await db.execute(
            select(ChapterDraft)
            .where(ChapterDraft.chapter_id == chapter.id)
            .order_by(ChapterDraft.version.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        new_version = (latest.version + 1) if latest else 1
        if latest and latest.is_active:
            from sqlalchemy import update
            await db.execute(
                update(ChapterDraft)
                .where(ChapterDraft.chapter_id == chapter.id)
                .where(ChapterDraft.is_active == True)
                .values(is_active=False)
            )
            await db.flush()
        new_draft = ChapterDraft(
            id=str(uuid.uuid4()),
            chapter_id=chapter.id,
            version=new_version,
            content=payload.get("content"),
            summary=payload.get("summary"),
            critique_data=payload.get("critique_data"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(new_draft)
        await db.flush()
        chapter.active_draft_id = new_draft.id
        chapter.updated_at = datetime.utcnow()
        if payload.get("content"):
            chapter.status = ChapterStatus.WRITING
        await db.flush()
        pw.status = PendingWriteStatus.APPROVED.value
        await db.flush()
        return {"success": True, "draft_id": new_draft.id}

    @staticmethod
    async def reject(db: AsyncSession, pending_id: str) -> Dict[str, Any]:
        r = await db.execute(
            select(PendingWrite).where(
                and_(
                    PendingWrite.id == pending_id,
                    PendingWrite.status == PendingWriteStatus.PENDING.value,
                )
            )
        )
        pw = r.scalar_one_or_none()
        if not pw:
            return {"success": False, "error": "pending not found or already processed"}
        pw.status = PendingWriteStatus.REJECTED.value
        await db.flush()
        return {"success": True}
