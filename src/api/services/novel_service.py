from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
from src.api.models import Novel, Chapter, ChapterDraft, ChapterStatus


class NovelService:
    @staticmethod
    async def create_novel(
        db: AsyncSession,
        title: str,
        genre: Optional[str] = None,
        summary: Optional[str] = None
    ) -> Novel:
        novel = Novel(
            id=str(uuid.uuid4()),
            title=title,
            genre=genre,
            summary=summary,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(novel)
        await db.flush()
        return novel

    @staticmethod
    async def get_novel_by_id(db: AsyncSession, novel_id: str) -> Optional[Novel]:
        result = await db.execute(
            select(Novel)
            .where(Novel.id == novel_id)
            .options(selectinload(Novel.chapters).selectinload(Chapter.drafts))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_novel_by_title(db: AsyncSession, title: str) -> Optional[Novel]:
        result = await db.execute(
            select(Novel)
            .where(Novel.title == title)
            .options(selectinload(Novel.chapters).selectinload(Chapter.drafts))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_novels(db: AsyncSession, limit: int = 100, offset: int = 0) -> List[Novel]:
        result = await db.execute(
            select(Novel)
            .order_by(Novel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_chapter(
        db: AsyncSession,
        novel_id: str,
        index: int,
        title: Optional[str] = None
    ) -> Chapter:
        chapter = Chapter(
            id=str(uuid.uuid4()),
            novel_id=novel_id,
            index=index,
            title=title,
            status=ChapterStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(chapter)
        await db.flush()
        return chapter

    @staticmethod
    async def get_chapter_by_id(db: AsyncSession, chapter_id: str) -> Optional[Chapter]:
        result = await db.execute(
            select(Chapter)
            .where(Chapter.id == chapter_id)
            .options(selectinload(Chapter.drafts))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_chapter_by_novel_and_index(
        db: AsyncSession,
        novel_id: str,
        index: int
    ) -> Optional[Chapter]:
        result = await db.execute(
            select(Chapter)
            .where(and_(Chapter.novel_id == novel_id, Chapter.index == index))
            .options(selectinload(Chapter.drafts))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_chapters(
        db: AsyncSession,
        novel_id: str,
        limit: int = 100
    ) -> List[Chapter]:
        result = await db.execute(
            select(Chapter)
            .where(Chapter.novel_id == novel_id)
            .order_by(Chapter.index.asc())
            .limit(limit)
            .options(selectinload(Chapter.drafts))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_chapter_content(
        db: AsyncSession,
        chapter_id: str
    ) -> Optional[Dict[str, Any]]:
        chapter = await NovelService.get_chapter_by_id(db, chapter_id)
        if not chapter:
            return None

        await db.refresh(chapter, ["drafts"])
        active_draft = next((d for d in chapter.drafts if d.is_active), None)
        if not active_draft:
            return {
                "chapter_id": chapter_id,
                "title": chapter.title,
                "status": chapter.status.value,
                "content": None,
                "summary": None,
                "version": 0
            }

        result = {
            "chapter_id": chapter_id,
            "title": chapter.title,
            "status": chapter.status.value,
            "content": active_draft.content,
            "summary": active_draft.summary,
            "version": active_draft.version,
            "created_at": active_draft.created_at.isoformat()
        }
        if active_draft.critique_data:
            result["critique_data"] = active_draft.critique_data
        return result

    @staticmethod
    async def save_draft(
        db: AsyncSession,
        chapter_id: str,
        content: Optional[str] = None,
        summary: Optional[str] = None,
        critique_data: Optional[Dict[str, Any]] = None
    ) -> ChapterDraft:
        chapter = await NovelService.get_chapter_by_id(db, chapter_id)
        if not chapter:
            raise ValueError(f"Chapter {chapter_id} not found")


        result = await db.execute(
            select(ChapterDraft)
            .where(ChapterDraft.chapter_id == chapter_id)
            .order_by(ChapterDraft.version.desc())
            .limit(1)
        )
        latest_draft = result.scalar_one_or_none()

        new_version = (latest_draft.version + 1) if latest_draft else 1

        if latest_draft and latest_draft.is_active:
            await db.execute(
                update(ChapterDraft)
                .where(ChapterDraft.chapter_id == chapter_id)
                .where(ChapterDraft.is_active == True)
                .values(is_active=False)
            )
            await db.flush()

        new_draft = ChapterDraft(
            id=str(uuid.uuid4()),
            chapter_id=chapter_id,
            version=new_version,
            content=content,
            summary=summary,
            critique_data=critique_data,
            is_active=True,
            created_at=datetime.utcnow()
        )
        db.add(new_draft)
        await db.flush()

        chapter.updated_at = datetime.utcnow()
        await db.flush()

        return new_draft

    @staticmethod
    async def update_chapter_status(
        db: AsyncSession,
        chapter_id: str,
        status: ChapterStatus
    ) -> Optional[Chapter]:
        chapter = await NovelService.get_chapter_by_id(db, chapter_id)
        if not chapter:
            return None

        chapter.status = status
        chapter.updated_at = datetime.utcnow()
        await db.flush()
        return chapter

    @staticmethod
    async def get_draft_history(
        db: AsyncSession,
        chapter_id: str
    ) -> List[ChapterDraft]:
        result = await db.execute(
            select(ChapterDraft)
            .where(ChapterDraft.chapter_id == chapter_id)
            .order_by(ChapterDraft.version.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def delete_chapter(
        db: AsyncSession,
        novel_id: str,
        chapter_index: int
    ) -> bool:
        chapter = await NovelService.get_chapter_by_novel_and_index(db, novel_id, chapter_index)
        if not chapter:
            return False
        
        await db.delete(chapter)
        await db.flush()
        return True
