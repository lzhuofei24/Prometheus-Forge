from sqlalchemy import create_engine, select, and_, update
from sqlalchemy.orm import sessionmaker, selectinload
from sqlalchemy.pool import QueuePool
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import os
from pathlib import Path
from src.api.models import Novel, Chapter, ChapterDraft, ChapterStatus, PendingWrite, PendingWriteStatus, NovelSetting

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{Path(__file__).parent.parent.parent / 'data' / 'novel_content_db' / 'prometheus_forge.db'}"
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class DatabaseService:
    _cache_service = None
    
    @classmethod
    def set_cache_service(cls, cache_service):
        cls._cache_service = cache_service

    @staticmethod
    def get_or_create_novel(title: str, genre: Optional[str] = None, summary: Optional[str] = None) -> Novel:
        with SessionLocal() as db:
            novel = db.execute(select(Novel).where(Novel.title == title)).scalar_one_or_none()
            if not novel:
                novel = Novel(
                    id=str(uuid.uuid4()),
                    title=title,
                    genre=genre,
                    summary=summary,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(novel)
                db.commit()
                db.refresh(novel)
            return novel

    @staticmethod
    def get_novel_by_title(title: str) -> Optional[Novel]:
        with SessionLocal() as db:
            return db.execute(select(Novel).where(Novel.title == title)).scalar_one_or_none()

    @staticmethod
    def list_novels(order_by_updated: bool = True) -> List[Novel]:
        """列出所有小说，用于替代工作区目录扫描。"""
        with SessionLocal() as db:
            q = select(Novel)
            if order_by_updated:
                q = q.order_by(Novel.updated_at.desc())
            return list(db.execute(q).scalars().all())

    @staticmethod
    def get_or_create_chapter(novel_id: str, index: int, title: Optional[str] = None) -> Chapter:
        with SessionLocal() as db:
            chapter = db.execute(
                select(Chapter).where(and_(Chapter.novel_id == novel_id, Chapter.index == index))
            ).scalar_one_or_none()
            
            if not chapter:
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
                db.commit()
                db.refresh(chapter)
            return chapter

    @staticmethod
    def get_chapter_by_novel_and_index(novel_id: str, index: int) -> Optional[Chapter]:
        with SessionLocal() as db:
            return db.execute(
                select(Chapter)
                .where(and_(Chapter.novel_id == novel_id, Chapter.index == index))
                .options(selectinload(Chapter.drafts))
            ).scalar_one_or_none()

    @staticmethod
    def list_chapters(novel_id: str) -> List[Chapter]:
        with SessionLocal() as db:
            result = db.execute(
                select(Chapter)
                .where(Chapter.novel_id == novel_id)
                .order_by(Chapter.index.asc())
                .options(selectinload(Chapter.drafts))
            )
            return list(result.scalars().all())

    @staticmethod
    def get_chapter_with_active_draft(novel_id: str, chapter_index: int):
        with SessionLocal() as db:
            result = db.execute(
                select(Chapter, ChapterDraft)
                .outerjoin(ChapterDraft, and_(
                    ChapterDraft.chapter_id == Chapter.id,
                    ChapterDraft.is_active == True
                ))
                .where(and_(
                    Chapter.novel_id == novel_id,
                    Chapter.index == chapter_index
                ))
            ).first()
            return result

    @staticmethod
    def get_chapter_outline(novel_id: str, chapter_index: int) -> Optional[str]:
        if DatabaseService._cache_service:
            cached = DatabaseService._cache_service.get_chapter_outline(novel_id, chapter_index)
            if cached:
                return cached
        
        result = DatabaseService.get_chapter_with_active_draft(novel_id, chapter_index)
        if not result:
            return None
        
        chapter, draft = result
        if draft and draft.summary:
            if chapter.active_draft_id != draft.id:
                with SessionLocal() as db:
                    # 在新的会话中重新查询 chapter，避免会话不一致的问题
                    chapter_in_db = db.execute(
                        select(Chapter).where(Chapter.id == chapter.id)
                    ).scalar_one()
                    chapter_in_db.active_draft_id = draft.id
                    db.commit()
            if DatabaseService._cache_service:
                DatabaseService._cache_service.set_chapter_outline(novel_id, chapter_index, draft.summary)
            return draft.summary
        return None

    @staticmethod
    def save_outline(novel_id: str, chapter_index: int, outline: str) -> ChapterDraft:
        # 先确保章节存在
        DatabaseService.get_or_create_chapter(novel_id, chapter_index)
        
        with SessionLocal() as db:
            # 在新的会话中重新查询 chapter，避免会话不一致的问题
            chapter = db.execute(
                select(Chapter).where(and_(Chapter.novel_id == novel_id, Chapter.index == chapter_index))
            ).scalar_one()
            
            new_version = chapter.latest_version + 1

            if chapter.active_draft_id:
                db.execute(
                    update(ChapterDraft)
                    .where(ChapterDraft.id == chapter.active_draft_id)
                    .values(is_active=False)
                )

            new_draft = ChapterDraft(
                id=str(uuid.uuid4()),
                chapter_id=chapter.id,
                version=new_version,
                summary=outline,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.add(new_draft)
            chapter.active_draft_id = new_draft.id
            chapter.latest_version = new_version
            chapter.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(new_draft)
            
            if DatabaseService._cache_service:
                DatabaseService._cache_service.set_chapter_outline(novel_id, chapter_index, outline)
            
            return new_draft

    @staticmethod
    def get_chapter_content(novel_id: str, chapter_index: int) -> Optional[str]:
        if DatabaseService._cache_service:
            cached = DatabaseService._cache_service.get_chapter_content(novel_id, chapter_index)
            if cached:
                return cached
        
        result = DatabaseService.get_chapter_with_active_draft(novel_id, chapter_index)
        if not result:
            return None
        
        chapter, draft = result
        if draft and draft.content:
            if chapter.active_draft_id != draft.id:
                with SessionLocal() as db:
                    # 在新的会话中重新查询 chapter，避免会话不一致的问题
                    chapter_in_db = db.execute(
                        select(Chapter).where(Chapter.id == chapter.id)
                    ).scalar_one()
                    chapter_in_db.active_draft_id = draft.id
                    db.commit()
            if DatabaseService._cache_service:
                DatabaseService._cache_service.set_chapter_content(novel_id, chapter_index, draft.content)
            return draft.content
        return None

    @staticmethod
    def get_chapters_with_drafts(novel_id: str, chapter_indices: List[int]) -> Dict[int, Dict[str, Any]]:
        with SessionLocal() as db:
            results = db.execute(
                select(Chapter, ChapterDraft)
                .outerjoin(ChapterDraft, and_(
                    ChapterDraft.chapter_id == Chapter.id,
                    ChapterDraft.is_active == True
                ))
                .where(and_(
                    Chapter.novel_id == novel_id,
                    Chapter.index.in_(chapter_indices)
                ))
            ).all()
            
            result_dict = {}
            for chapter, draft in results:
                result_dict[chapter.index] = {
                    "chapter": chapter,
                    "draft": draft,
                    "content": draft.content if draft else None,
                    "outline": draft.summary if draft else None
                }
            return result_dict

    @staticmethod
    def save_content(novel_id: str, chapter_index: int, content: str, critique_data: Optional[Dict[str, Any]] = None) -> ChapterDraft:
        # 先确保章节存在
        DatabaseService.get_or_create_chapter(novel_id, chapter_index)
        
        with SessionLocal() as db:
            # 在新的会话中重新查询 chapter，避免会话不一致的问题
            chapter = db.execute(
                select(Chapter).where(and_(Chapter.novel_id == novel_id, Chapter.index == chapter_index))
            ).scalar_one()
            new_version = chapter.latest_version + 1

            if chapter.active_draft_id:
                db.execute(
                    update(ChapterDraft)
                    .where(ChapterDraft.id == chapter.active_draft_id)
                    .values(is_active=False)
                )

            new_draft = ChapterDraft(
                id=str(uuid.uuid4()),
                chapter_id=chapter.id,
                version=new_version,
                content=content,
                critique_data=critique_data,
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.add(new_draft)
            chapter.active_draft_id = new_draft.id
            chapter.latest_version = new_version
            chapter.status = ChapterStatus.WRITING
            chapter.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(new_draft)
            
            if DatabaseService._cache_service:
                DatabaseService._cache_service.set_chapter_content(novel_id, chapter_index, content)
            
            return new_draft

    @staticmethod
    def update_chapter_status(novel_id: str, chapter_index: int, status: ChapterStatus):
        with SessionLocal() as db:
            chapter = db.execute(
                select(Chapter).where(
                    and_(Chapter.novel_id == novel_id, Chapter.index == chapter_index)
                )
            ).scalar_one_or_none()
            if not chapter:
                return
            chapter.status = status
            chapter.updated_at = datetime.utcnow()
            db.commit()

    @staticmethod
    def update_chapter_title(novel_id: str, chapter_index: int, title: Optional[str]) -> None:
        """更新章节标题。"""
        with SessionLocal() as db:
            chapter = db.execute(
                select(Chapter).where(
                    and_(Chapter.novel_id == novel_id, Chapter.index == chapter_index)
                )
            ).scalar_one_or_none()
            if chapter:
                chapter.title = title
                chapter.updated_at = datetime.utcnow()
                db.commit()

    @staticmethod
    def delete_chapter_by_index(novel_id: str, chapter_index: int) -> bool:
        """按小说 id 与章节序号删除章节，返回是否删除成功。"""
        with SessionLocal() as db:
            chapter = db.execute(
                select(Chapter).where(
                    and_(Chapter.novel_id == novel_id, Chapter.index == chapter_index)
                )
            ).scalar_one_or_none()
            if not chapter:
                return False
            db.delete(chapter)
            db.commit()
            return True

    @staticmethod
    def get_chapters_content_batch(novel_id: str, chapter_indices: List[int]) -> Dict[int, Optional[str]]:
        results = DatabaseService.get_chapters_with_drafts(novel_id, chapter_indices)
        return {idx: data.get("content") for idx, data in results.items()}

    @staticmethod
    def add_pending_write(
        write_type: str,
        novel_id: str,
        chapter_index: int,
        payload: Dict[str, Any],
        workflow_id: Optional[str] = None,
        source_agent: Optional[str] = None,
        workflow_type: Optional[str] = None,
    ) -> str:
        """提交待审批写入，由审批助手通过后再落库。workflow_type 为启动形式（generate_chapter/outline_only 等）。返回 pending id。"""
        with SessionLocal() as db:
            pw = PendingWrite(
                id=str(uuid.uuid4()),
                write_type=write_type,
                novel_id=novel_id,
                chapter_index=chapter_index,
                payload=payload,
                workflow_id=workflow_id,
                workflow_type=workflow_type,
                source_agent=source_agent,
                status=PendingWriteStatus.PENDING.value,
                created_at=datetime.utcnow(),
            )
            db.add(pw)
            db.commit()
            db.refresh(pw)
            return pw.id

    @staticmethod
    def get_novel_setting(novel_id: str, key: str) -> Optional[str]:
        """从 novel_settings 表读取单条设定，key 如 bios, world, relation_graph。"""
        with SessionLocal() as db:
            row = db.execute(
                select(NovelSetting.value).where(
                    and_(NovelSetting.novel_id == novel_id, NovelSetting.key == key)
                )
            ).scalar_one_or_none()
            return row if row is not None else None

    @staticmethod
    def get_novel_global_settings(novel_id: str) -> Dict[str, Any]:
        """返回小说全局设定 {bios, world, story_summary, relations}，仅从 DB 读取，无则返回空。"""
        import json
        bios_raw = DatabaseService.get_novel_setting(novel_id, "bios")
        world = DatabaseService.get_novel_setting(novel_id, "world") or ""
        story_summary = DatabaseService.get_novel_setting(novel_id, "story_summary") or ""
        relations_raw = DatabaseService.get_novel_setting(novel_id, "relation_graph")
        try:
            bios = json.loads(bios_raw) if bios_raw else []
        except Exception:
            bios = []
        try:
            relations = json.loads(relations_raw) if relations_raw else {}
        except Exception:
            relations = {}
        return {"bios": bios, "world": world, "story_summary": story_summary, "relations": relations}

    @staticmethod
    def set_novel_setting(novel_id: str, key: str, value: str) -> None:
        """写入或更新 novel_settings。"""
        with SessionLocal() as db:
            row = db.execute(
                select(NovelSetting).where(
                    and_(NovelSetting.novel_id == novel_id, NovelSetting.key == key)
                )
            ).scalar_one_or_none()
            if row:
                row.value = value
                row.updated_at = datetime.utcnow()
            else:
                db.add(NovelSetting(
                    id=str(uuid.uuid4()),
                    novel_id=novel_id,
                    key=key,
                    value=value,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                ))
            db.commit()
