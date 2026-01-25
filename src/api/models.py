from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey, DateTime, JSON, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from src.core.database import Base


class ChapterStatus(str, enum.Enum):
    PENDING = "pending"
    WRITING = "writing"
    REVISING = "revising"
    FINISHED = "finished"
    FAILED = "failed"


class Novel(Base):
    __tablename__ = "novels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False, index=True)
    genre = Column(String(100), nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    chapters = relationship("Chapter", back_populates="novel", cascade="all, delete-orphan", order_by="Chapter.index")


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    index = Column(Integer, nullable=False)
    title = Column(String(255), nullable=True)
    status = Column(SQLEnum(ChapterStatus), default=ChapterStatus.PENDING, nullable=False, index=True)
    active_draft_id = Column(
        String(36),
        ForeignKey("chapter_drafts.id", use_alter=True, name="fk_chapter_active_draft_id"),
        nullable=True,
        index=True,
    )
    latest_version = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    novel = relationship("Novel", back_populates="chapters")
    drafts = relationship("ChapterDraft", back_populates="chapter", primaryjoin="Chapter.id == ChapterDraft.chapter_id", cascade="all, delete-orphan", order_by="ChapterDraft.version.desc()")
    active_draft = relationship("ChapterDraft", foreign_keys=[active_draft_id], post_update=True)

    __table_args__ = (
        Index("idx_chapter_novel_index", "novel_id", "index"),
        Index("idx_chapter_novel_status", "novel_id", "index", "status"),
    )


class ChapterDraft(Base):
    __tablename__ = "chapter_drafts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chapter_id = Column(String(36), ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    critique_data = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chapter = relationship("Chapter", back_populates="drafts", foreign_keys=[chapter_id])

    __table_args__ = (
        Index("idx_draft_chapter_active", "chapter_id", "is_active"),
        Index("idx_draft_chapter_version", "chapter_id", "version"),
        Index("idx_draft_chapter_active_version", "chapter_id", "is_active", "version"),
    )


class PendingWriteStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PendingWrite(Base):
    """Agent 待审批写入：写入须经用户审批后再落库。"""
    __tablename__ = "pending_writes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    write_type = Column(String(32), nullable=False, index=True)  # outline | content
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_index = Column(Integer, nullable=False, index=True)
    payload = Column(JSON, nullable=False)  # { "content"?: str, "summary"?: str, "critique_data"?: dict }
    workflow_id = Column(String(64), nullable=True, index=True)
    source_agent = Column(String(64), nullable=True)
    status = Column(
        String(16), default=PendingWriteStatus.PENDING.value, nullable=False, index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("idx_pending_novel_chapter", "novel_id", "chapter_index"),)


class NovelSetting(Base):
    """小说全局设定（替代 workspace 下的 global/），key 如 bios, world, relation_graph。"""
    __tablename__ = "novel_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    novel_id = Column(String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(64), nullable=False, index=True)
    value = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (Index("idx_novel_setting_novel_key", "novel_id", "key", unique=True),)
