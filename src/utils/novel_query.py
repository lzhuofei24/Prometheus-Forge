"""
小说与章节查询：全部来自数据库，不再依赖工作区文件。
原 workspace 下的列表、目录、正文、大纲、设定均由 DatabaseService 提供。
"""
from pathlib import Path
from typing import List, Dict, Optional, Any
import json


def _get_db():
    from src.core.db_service import DatabaseService
    return DatabaseService


class NovelQuery:
    """从数据库查询小说列表、章节目录、正文、大纲与全局设定。不再使用 workspace_root。"""

    def __init__(self, workspace_root: Optional[Path] = None):
        """保留 workspace_root 参数仅为兼容旧调用，实际未使用；所有数据来自 DB。"""
        self._db = _get_db()

    def list_novels(self) -> List[str]:
        """小说名列表（按更新时间倒序）。"""
        novels = self._db.list_novels()
        return [n.title for n in novels]

    def get_novel_info(self, novel_name: str) -> Dict[str, Any]:
        """小说详情：name, chapters, chapter_count, bios, world, relations。"""
        novel = self._db.get_novel_by_title(novel_name)
        if not novel:
            return {}
        settings = self._db.get_novel_global_settings(novel.id)
        chapters = self._db.list_chapters(novel.id)
        indices = [c.index for c in chapters]
        return {
            "name": novel_name,
            "chapters": indices,
            "chapter_count": len(indices),
            "bios": settings.get("bios") or [],
            "world": settings.get("world") or "",
            "relations": settings.get("relations") or {},
        }

    def get_chapter_info(self, novel_name: str, chapter_num: int) -> Dict[str, Any]:
        """章节详情：chapter_num, outline, content, critique, meta。"""
        novel = self._db.get_novel_by_title(novel_name)
        if not novel:
            return {}
        result = self._db.get_chapter_with_active_draft(novel.id, chapter_num)
        if not result:
            return {
                "chapter_num": chapter_num,
                "outline": "",
                "content": "",
                "critique": "",
                "meta": {"title": "", "status": "unknown", "word_count": 0, "chapter_num": chapter_num},
            }
        chapter, draft = result
        content = (draft.content or "") if draft else ""
        outline = (draft.summary or "") if draft else ""
        critique_data = (draft.critique_data if draft else None) or {}
        if isinstance(critique_data, dict):
            critique = json.dumps(critique_data, ensure_ascii=False, indent=2)
        else:
            critique = str(critique_data) if critique_data else ""
        meta = {
            "title": (chapter.title or ""),
            "status": getattr(chapter.status, "value", str(chapter.status)) if hasattr(chapter, "status") else "unknown",
            "word_count": len(content),
            "chapter_num": chapter_num,
        }
        return {
            "chapter_num": chapter_num,
            "outline": outline,
            "content": content,
            "critique": critique,
            "meta": meta,
        }

    def get_chapters_summary(self, novel_name: str) -> List[Dict[str, Any]]:
        """章节目录摘要：chapter_num, title, status, word_count, outline_preview, folder_index。"""
        novel = self._db.get_novel_by_title(novel_name)
        if not novel:
            return []
        chapters = self._db.list_chapters(novel.id)
        summary = []
        for ch in chapters:
            outline = self._db.get_chapter_outline(novel.id, ch.index) or ""
            content = self._db.get_chapter_content(novel.id, ch.index) or ""
            outline_preview = (outline[:100] + "...") if len(outline) > 100 else outline
            summary.append({
                "chapter_num": ch.index,
                "title": ch.title or "",
                "status": getattr(ch.status, "value", str(ch.status)) if hasattr(ch, "status") else "unknown",
                "word_count": len(content),
                "outline_preview": outline_preview,
                "folder_index": ch.index,
            })
        return summary
