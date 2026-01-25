import re
import logging
from pathlib import Path
from typing import List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.services.novel_service import NovelService
from src.api.models import ChapterStatus

logger = logging.getLogger(__name__)


class ImportService:
    def __init__(self):
        self.chapter_patterns = [
            re.compile(r'^第[一二三四五六七八九十百千万\d]+章\s*(.*?)$', re.MULTILINE),
            re.compile(r'^Chapter\s+[\dIVX]+[\.\s]*(.*?)$', re.MULTILINE | re.IGNORECASE),
            re.compile(r'^第\d+章\s*(.*?)$', re.MULTILINE),
            re.compile(r'^第[零一二三四五六七八九十]+章\s*(.*?)$', re.MULTILINE),
        ]
    
    def _detect_encoding(self, content: bytes) -> str:
        encodings = ['utf-8', 'gb18030', 'gbk', 'big5']
        for encoding in encodings:
            try:
                test_content = content.decode(encoding)
                if test_content.strip():
                    return encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        logger.warning("无法识别文件编码，使用 utf-8")
        return 'utf-8'
    
    def _find_chapters(self, content: str) -> List[Tuple[int, str, str]]:
        chapters = []
        lines = content.split('\n')
        current_chapter_num = 0
        current_chapter_title = ""
        current_chapter_content = []
        first_chapter_found = False
        
        for line in lines:
            matched = False
            for pattern in self.chapter_patterns:
                match = pattern.match(line.strip())
                if match:
                    if current_chapter_num == 0 and current_chapter_content:
                        chapter_text = '\n'.join(current_chapter_content).strip()
                        if chapter_text:
                            chapters.append((1, "", chapter_text))
                        current_chapter_content = []
                    
                    if current_chapter_num > 0:
                        chapter_text = '\n'.join(current_chapter_content).strip()
                        if chapter_text:
                            chapters.append((current_chapter_num, current_chapter_title, chapter_text))
                    
                    current_chapter_num += 1
                    current_chapter_title = match.group(1).strip() if match.groups() else ""
                    current_chapter_content = []
                    first_chapter_found = True
                    matched = True
                    break
            
            if not matched:
                current_chapter_content.append(line)
        
        if current_chapter_num > 0:
            chapter_text = '\n'.join(current_chapter_content).strip()
            if chapter_text:
                chapters.append((current_chapter_num, current_chapter_title, chapter_text))
        elif not first_chapter_found and current_chapter_content:
            chapter_text = '\n'.join(current_chapter_content).strip()
            if chapter_text:
                chapters.append((1, "", chapter_text))
        
        logger.info(f"章节解析完成，共 {len(chapters)} 个章节")
        return chapters
    
    async def import_txt_novel(
        self,
        db: AsyncSession,
        file_content: bytes,
        novel_title: str,
        genre: Optional[str] = None
    ) -> dict:
        encoding = self._detect_encoding(file_content)
        content = file_content.decode(encoding)
        
        if not content.strip():
            raise ValueError("文件内容为空")
        
        existing_novel = await NovelService.get_novel_by_title(db, novel_title)
        if existing_novel:
            raise ValueError(f"小说 '{novel_title}' 已存在")
        
        novel = await NovelService.create_novel(
            db,
            title=novel_title,
            genre=genre,
            summary=None
        )
        await db.flush()
        
        chapters = self._find_chapters(content)
        
        if not chapters:
            chapters = [(1, "", content.strip())]
            logger.warning("未找到章节标记，将整个文件作为单个章节")
        
        created_chapters = []
        for chapter_num, chapter_title, chapter_content in chapters:
            if not chapter_content.strip():
                continue
            
            chapter = await NovelService.create_chapter(
                db,
                novel_id=novel.id,
                index=chapter_num,
                title=chapter_title if chapter_title else None
            )
            await db.flush()
            
            await NovelService.save_draft(
                db,
                chapter_id=chapter.id,
                content=chapter_content,
                summary=None,
                critique_data=None
            )
            await db.flush()
            
            await NovelService.update_chapter_status(
                db,
                chapter.id,
                ChapterStatus.PENDING
            )
            await db.flush()
            
            created_chapters.append({
                "index": chapter_num,
                "title": chapter_title,
                "word_count": len(chapter_content)
            })
        
        await db.commit()
        
        return {
            "novel_id": novel.id,
            "novel_title": novel.title,
            "chapters_count": len(created_chapters),
            "chapters": created_chapters
        }
