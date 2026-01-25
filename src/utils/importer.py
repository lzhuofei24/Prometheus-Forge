import re
import logging
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
from .file_manager import ProjectManager

logger = logging.getLogger(__name__)


class NovelImporter:
    def __init__(self, workspace_root: Path):
        self.project_manager = ProjectManager(workspace_root)
        
        self.chapter_patterns = [
            re.compile(r'^第[一二三四五六七八九十百千万\d]+章\s*(.*?)$', re.MULTILINE),
            re.compile(r'^Chapter\s+[\dIVX]+[\.\s]*(.*?)$', re.MULTILINE | re.IGNORECASE),
            re.compile(r'^第\d+章\s*(.*?)$', re.MULTILINE),
            re.compile(r'^第[零一二三四五六七八九十]+章\s*(.*?)$', re.MULTILINE),
        ]
    
    def _detect_encoding(self, file_path: Path) -> str:
        encodings = ['utf-8', 'gb18030']
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    f.read()
                return encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError(f"无法识别文件编码: {file_path}")
    
    def _find_chapters(self, content: str) -> List[Tuple[int, str, str]]:
        chapters = []
        lines = content.split('\n')
        current_chapter_num = 0
        current_chapter_title = ""
        current_chapter_content = []
        first_chapter_found = False
        
        for i, line in enumerate(lines):
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
        for ch_num, title, ch_content in chapters:
            logger.info(f"  章节 {ch_num} ({title}): {len(ch_content)} 字")
        
        return chapters
    
    def import_novel(self, txt_path: Path, novel_name: str) -> List[Dict]:
        txt_path = Path(txt_path)
        if not txt_path.exists():
            raise FileNotFoundError(f"文件不存在: {txt_path}")
        
        encoding = self._detect_encoding(txt_path)
        
        with open(txt_path, 'r', encoding=encoding) as f:
            content = f.read()
        
        if not content.strip():
            raise ValueError("文件内容为空")
        
        self.project_manager.init_novel(novel_name)
        
        raw_chapters = self._find_chapters(content)
        
        if not raw_chapters:
            raise ValueError("未找到任何章节")
        
        logger.info(f"正则解析完成，共找到 {len(raw_chapters)} 个原始章节")
        
        final_chapters = []
        global_chapter_index = 1
        
        for original_chapter_num, chapter_title, chapter_content in raw_chapters:
            content_length = len(chapter_content)
            chapter_display = f"第{original_chapter_num}章 {chapter_title}" if chapter_title else f"第{original_chapter_num}章"
            
            logger.info(f"处理章节: {chapter_display}, 字数: {content_length}")
            
            final_chapters.append({
                "chapter_num": int(original_chapter_num),
                "title": chapter_title,
                "content": chapter_content,
                "global_index": global_chapter_index
            })
            global_chapter_index += 1
        
        logger.info(f"章节处理完成，最终共 {len(final_chapters)} 个章节（含子章节）")
        
        processed_chapters = final_chapters
        
        results = []
        timestamp = datetime.now().isoformat()
        
        for chapter_info in processed_chapters:
            chapter_num = chapter_info["chapter_num"]
            chapter_title = chapter_info["title"]
            chapter_content = chapter_info["content"]
            global_index = chapter_info["global_index"]
            
            chapter_path = self.project_manager.init_chapter(novel_name, global_index)
            
            content_file = chapter_path / "content.md"
            
            chapter_num_int = int(chapter_num)
            if chapter_title:
                content_with_title = f"# 第{chapter_num_int}章 {chapter_title}\n\n{chapter_content}"
            else:
                content_with_title = f"# 第{chapter_num_int}章\n\n{chapter_content}"
            
            self.project_manager.save_content(content_file, content_with_title)
            
            word_count = len(chapter_content)
            
            meta = {
                "chapter_num": chapter_num,
                "title": chapter_title,
                "status": "draft",
                "word_count": word_count,
                "character_states": {},
                "created_at": timestamp,
                "updated_at": timestamp
            }
            
            meta_file = chapter_path / "meta.json"
            self.project_manager.save_content(meta_file, meta)
            
            results.append({
                "chapter_num": chapter_num,
                "path": str(content_file),
                "word_count": word_count,
                "title": chapter_title
            })
        
        return results
