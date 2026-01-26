"""待审批写入：列出、查看目标位置现有内容、通过/拒绝。"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import uuid
from src.api.models import (
    Novel,
    Chapter,
    ChapterDraft,
    PendingWrite,
    PendingWriteStatus,
    ChapterStatus,
)


def _outline_json_to_markdown(raw: str, chapter_index: int) -> str:
    """将架构师输出的 JSON 大纲转为可读 Markdown。若解析失败则返回原串。"""
    if not raw or not raw.strip():
        return raw or ""
    try:
        obj = json.loads(raw)
        scenes = obj.get("scenes") if isinstance(obj, dict) else None
        if not scenes or not isinstance(scenes, list):
            return raw
        lines = [f"# 第{chapter_index}章分场景大纲", ""]
        for s in scenes:
            if not isinstance(s, dict):
                continue
            sid = s.get("id", "?")
            lines.append(f"## 场景 {sid}")
            lines.append("")
            if s.get("summary"):
                lines.append(f"**描述**: {s['summary']}")
                lines.append("")
            if "expected_words" in s:
                lines.append(f"**目标字数**: {s['expected_words']} 字")
                lines.append("")
            if s.get("key_characters"):
                lines.append(f"**关键人物**: {', '.join(s['key_characters'])}")
                lines.append("")
        return "\n".join(lines).strip() or raw
    except Exception:
        return raw


class ApprovalService:
    @staticmethod
    async def list_workflow_types_with_pending(
        db: AsyncSession,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """返回有待审批项的启动形式（workflow_type）及数量，用于审批助手最左侧「启动形式」层。"""
        st = status or PendingWriteStatus.PENDING.value
        q = (
            select(PendingWrite.workflow_type, func.count(PendingWrite.id).label("count"))
            .where(PendingWrite.status == st)
            .group_by(PendingWrite.workflow_type)
        )
        result = await db.execute(q)
        return [
            {"workflow_type": row[0] or "", "count": row[1]}
            for row in result.all()
        ]

    @staticmethod
    async def list_pending(
        db: AsyncSession,
        limit: int = 50,
        status: Optional[str] = None,
        workflow_id: Optional[str] = None,
        workflow_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q = (
            select(PendingWrite, Novel.title)
            .join(Novel, Novel.id == PendingWrite.novel_id)
            .where(PendingWrite.status == (status or PendingWriteStatus.PENDING.value))
        )
        if workflow_id is not None and str(workflow_id).strip():
            q = q.where(PendingWrite.workflow_id == workflow_id.strip())
        if workflow_type is not None:
            wt = str(workflow_type).strip()
            if wt == "":
                q = q.where((PendingWrite.workflow_type == "") | (PendingWrite.workflow_type.is_(None)))
            else:
                q = q.where(PendingWrite.workflow_type == wt)
        q = q.order_by(PendingWrite.created_at.desc()).limit(limit)
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
    async def list_workflows_with_pending(
        db: AsyncSession,
        status: Optional[str] = None,
        workflow_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """返回有待审批项的工作流 id 及各自数量；可按 workflow_type（启动形式）筛选。"""
        st = status or PendingWriteStatus.PENDING.value
        q = (
            select(PendingWrite.workflow_id, func.count(PendingWrite.id).label("count"))
            .where(PendingWrite.status == st, PendingWrite.workflow_id.isnot(None))
        )
        if workflow_type is not None:
            wt = str(workflow_type).strip()
            if wt == "":
                q = q.where((PendingWrite.workflow_type == "") | (PendingWrite.workflow_type.is_(None)))
            else:
                q = q.where(PendingWrite.workflow_type == wt)
        q = q.group_by(PendingWrite.workflow_id)
        result = await db.execute(q)
        return [
            {"workflow_id": row[0], "count": row[1]}
            for row in result.all()
        ]

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
        await db.refresh(chapter, ["drafts"])
        active_draft = next((d for d in chapter.drafts if d.is_active), None)
        result = await db.execute(
            select(ChapterDraft)
            .where(ChapterDraft.chapter_id == chapter.id)
            .order_by(ChapterDraft.version.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        new_version = (latest.version + 1) if latest else 1
        if active_draft:
            from sqlalchemy import update
            await db.execute(
                update(ChapterDraft)
                .where(ChapterDraft.chapter_id == chapter.id)
                .where(ChapterDraft.is_active == True)
                .values(is_active=False)
            )
            await db.flush()
        if pw.write_type == "outline":
            new_content = active_draft.content if active_draft else None
            new_critique_data = active_draft.critique_data if active_draft else None
            raw_summary = payload.get("summary") or ""
            new_summary = _outline_json_to_markdown(raw_summary, pw.chapter_index)
        else:
            # 正文审批：保留现有大纲，仅当当前无大纲时才用 payload 的 summary
            new_content = payload.get("content")
            existing_summary = (active_draft.summary if active_draft else None) or (latest.summary if latest else None)
            new_summary = existing_summary if (existing_summary and str(existing_summary).strip()) else (payload.get("summary") or existing_summary)
            new_critique_data = payload.get("critique_data") if "critique_data" in (payload or {}) else (active_draft.critique_data if active_draft else None)
        new_draft = ChapterDraft(
            id=str(uuid.uuid4()),
            chapter_id=chapter.id,
            version=new_version,
            content=new_content,
            summary=new_summary,
            critique_data=new_critique_data,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(new_draft)
        await db.flush()
        chapter.active_draft_id = new_draft.id
        chapter.updated_at = datetime.utcnow()
        if new_content:
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
