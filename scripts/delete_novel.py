#!/usr/bin/env python
"""按标题删除数据库中的小说（含章节与草稿）。

用法（在项目根目录执行）:
  python scripts/delete_novel.py
  python scripts/delete_novel.py --title "我的小说"
"""

import asyncio
import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import AsyncSessionLocal
from src.api.services.novel_service import NovelService


async def delete_novel_by_title(title: str):
    """根据标题删除小说"""
    async with AsyncSessionLocal() as db:
        novel = await NovelService.get_novel_by_title(db, title)
        if not novel:
            print(f"❌ 未找到小说: {title}")
            return False

        print(f"📖 找到小说: {novel.title} (ID: {novel.id})")

        chapters = await NovelService.list_chapters(db, novel.id)
        print(f"   章节数量: {len(chapters)}")

        for chapter in chapters:
            drafts = await NovelService.get_draft_history(db, chapter.id)
            print(f"   删除章节 {chapter.index}: {len(drafts)} 个草稿")

        from sqlalchemy import delete
        from src.api.models import ChapterDraft, Chapter, Novel

        for chapter in chapters:
            await db.execute(delete(ChapterDraft).where(ChapterDraft.chapter_id == chapter.id))
            await db.execute(delete(Chapter).where(Chapter.id == chapter.id))

        await db.execute(delete(Novel).where(Novel.id == novel.id))
        await db.commit()

        print(f"✅ 已删除小说: {title}")
        return True


async def main():
    parser = argparse.ArgumentParser(description="按标题删除数据库中的小说")
    parser.add_argument("--title", type=str, default="虚拟世界历险记", help="小说标题")
    args = parser.parse_args()

    title = args.title
    print("=" * 60)
    print(f"删除小说: {title}")
    print("=" * 60)

    success = await delete_novel_by_title(title)

    if success:
        print("\n" + "=" * 60)
        print("✅ 删除完成！")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ 删除失败")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
