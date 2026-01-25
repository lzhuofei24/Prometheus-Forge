#!/usr/bin/env python
"""
迁移脚本：从文件系统迁移到数据库

将 workspace/ 目录下的所有小说和章节数据迁移到 SQLite/PostgreSQL 数据库。
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
import re
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import init_db, AsyncSessionLocal
from src.api.models import Novel, Chapter, ChapterDraft, ChapterStatus
from src.api.services.novel_service import NovelService
from src.utils.file_manager import ProjectManager
from src.core.config import Settings


def extract_chapter_number(chapter_path: Path) -> Optional[int]:
    """从路径中提取章节号"""
    chapter_name = chapter_path.name
    match = re.search(r'chapter[_\s]*(\d+)', chapter_name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    match = re.search(r'(\d+)', chapter_name)
    if match:
        return int(match.group(1))
    
    return None


def load_novel_metadata(novel_path: Path) -> Dict[str, Any]:
    """加载小说元数据"""
    metadata = {
        "title": novel_path.name,
        "genre": None,
        "summary": None
    }
    
    novel_yaml = novel_path / "novel.yaml"
    if novel_yaml.exists():
        try:
            with open(novel_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                metadata.update({
                    "title": data.get("title", novel_path.name),
                    "genre": data.get("genre"),
                    "summary": data.get("summary")
                })
        except Exception as e:
            print(f"警告: 无法解析 {novel_yaml}: {e}")
    
    return metadata


async def migrate_novel(novel_path: Path, db: AsyncSessionLocal):
    """迁移单个小说"""
    novel_name = novel_path.name
    print(f"\n处理小说: {novel_name}")
    
    metadata = load_novel_metadata(novel_path)
    
    existing_novel = await NovelService.get_novel_by_title(db, metadata["title"])
    if existing_novel:
        print(f"  小说已存在，跳过: {metadata['title']}")
        return existing_novel
    
    novel = await NovelService.create_novel(
        db,
        title=metadata["title"],
        genre=metadata["genre"],
        summary=metadata["summary"]
    )
    print(f"  ✅ 创建小说: {novel.title} (ID: {novel.id})")
    
    chapters_dir = novel_path / "chapters"
    if not chapters_dir.exists():
        print(f"  无章节目录，跳过")
        await db.commit()
        return novel
    
    chapter_dirs = sorted(
        [d for d in chapters_dir.iterdir() if d.is_dir()],
        key=lambda p: extract_chapter_number(p) or 0
    )
    
    for chapter_dir in chapter_dirs:
        chapter_num = extract_chapter_number(chapter_dir)
        if not chapter_num:
            print(f"  ⚠️  无法提取章节号: {chapter_dir.name}")
            continue
        
        outline_path = chapter_dir / "outline.md"
        content_path = chapter_dir / "content.md"
        meta_path = chapter_dir / "meta.json"
        
        if not content_path.exists() and not outline_path.exists():
            print(f"  ⚠️  章节 {chapter_num} 无内容，跳过")
            continue
        
        chapter = await NovelService.get_chapter_by_novel_and_index(
            db, novel.id, chapter_num
        )
        
        if not chapter:
            title = None
            if meta_path.exists():
                try:
                    meta = ProjectManager(project_root / "workspace").load_content(meta_path)
                    title = meta.get("title")
                except:
                    pass
            
            chapter = await NovelService.create_chapter(
                db,
                novel_id=novel.id,
                index=chapter_num,
                title=title
            )
            print(f"  ✅ 创建章节 {chapter_num}: {chapter.title or '无标题'}")
        
        outline_content = None
        if outline_path.exists():
            outline_content = ProjectManager(project_root / "workspace").load_content(outline_path)
        
        content = None
        if content_path.exists():
            content = ProjectManager(project_root / "workspace").load_content(content_path)
        
        critique_data = None
        if meta_path.exists():
            try:
                meta = ProjectManager(project_root / "workspace").load_content(meta_path)
                if "critique_score" in meta or "critique_comments" in meta:
                    critique_data = {
                        "score": meta.get("critique_score"),
                        "comments": meta.get("critique_comments"),
                        "advice": meta.get("actionable_feedback")
                    }
            except:
                pass
        
        if content or outline_content:
            draft = await NovelService.save_draft(
                db,
                chapter_id=chapter.id,
                content=content,
                summary=outline_content,
                critique_data=critique_data
            )
            print(f"    ✅ 保存草稿 v{draft.version}")
            
            if meta_path.exists():
                try:
                    meta = ProjectManager(project_root / "workspace").load_content(meta_path)
                    status_str = meta.get("status", "draft")
                    status_map = {
                        "draft": ChapterStatus.PENDING,
                        "writing": ChapterStatus.WRITING,
                        "finished": ChapterStatus.FINISHED,
                        "completed": ChapterStatus.FINISHED,
                        "failed": ChapterStatus.FAILED
                    }
                    status = status_map.get(status_str, ChapterStatus.PENDING)
                    await NovelService.update_chapter_status(db, chapter.id, status)
                except:
                    pass
    
    await db.commit()
    return novel


async def main():
    """主迁移函数"""
    print("=" * 80)
    print("📦 开始迁移：从文件系统到数据库")
    print("=" * 80)
    
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    workspace_root = Path(config.paths.workspace)
    
    if not workspace_root.exists():
        print(f"❌ 工作区目录不存在: {workspace_root}")
        return
    
    await init_db()
    print("✅ 数据库初始化完成")
    
    novel_dirs = [
        d for d in workspace_root.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ]
    
    if not novel_dirs:
        print("⚠️  未找到小说目录")
        return
    
    print(f"\n找到 {len(novel_dirs)} 个小说目录")
    
    async with AsyncSessionLocal() as db:
        for novel_path in novel_dirs:
            try:
                await migrate_novel(novel_path, db)
            except Exception as e:
                print(f"❌ 迁移失败 {novel_path.name}: {e}")
                import traceback
                traceback.print_exc()
                await db.rollback()
    
    print("\n" + "=" * 80)
    print("✅ 迁移完成！")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
