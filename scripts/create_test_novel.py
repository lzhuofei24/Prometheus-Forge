#!/usr/bin/env python
"""
在数据库中创建一本测试小说（含 1 个章节与正文），用于联调与前端展示。

数据库路径与 API 一致：data/novel_content_db/prometheus_forge.db（可通过 DATABASE_URL 覆盖）。

用法（在项目根目录执行，建议先激活 conda 环境 novel-agent）:
  conda activate novel-agent
  python scripts/create_test_novel.py

  python scripts/create_test_novel.py --title "我的测试书"
  python scripts/create_test_novel.py --force   # 若已存在同标题则仅打印并退出
"""

import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import init_db, AsyncSessionLocal
from src.api.models import Novel, Chapter, ChapterDraft, ChapterStatus  # noqa: F401  # 注册表结构
from src.api.services.novel_service import NovelService


DEFAULT_TITLE = "测试小说"
DEFAULT_GENRE = "玄幻"
DEFAULT_SUMMARY = "用于测试与联调的示例小说，由 create_test_novel 脚本创建。"

CHAPTER_1_TITLE = "第一章 开端"
CHAPTER_1_CONTENT = """秋日的午后，阳光透过梧桐叶洒在青石板上。

少年林未背靠老槐树，手里攥着一本破旧的册子。册子上写着「基础心法」四字，据说是祖上留下的唯一一件与“修行”沾边的东西。

他翻到最后一页，上面只有一句：心随意动，意随脉走。

“心随意动……”林未喃喃重复，试着按照册子前几页的吐纳方式调息。片刻后，小腹处似有一丝热气缓缓升起。他一愣，再试，那丝热气又消失了。

远处传来脚步声。林未迅速把册子塞进怀里，起身拍了拍衣角的土。

“林未，还在琢磨你那本破书呐？”同镇的阿福拎着两尾鱼晃过来，“走，今晚到我家喝鱼汤。”

林未笑了笑，说：“好。”

他心里却还在想那一丝若有若无的热气。或许，那并不只是错觉。

（本章完）
"""


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="在数据库中创建一本测试小说")
    parser.add_argument("--title", type=str, default=DEFAULT_TITLE, help="小说标题")
    parser.add_argument("--genre", type=str, default=DEFAULT_GENRE, help="类型")
    parser.add_argument("--summary", type=str, default=DEFAULT_SUMMARY, help="简介")
    parser.add_argument("--force", action="store_true", help="若已存在同标题小说，先略过创建，仅打印信息")
    args = parser.parse_args()

    title = args.title or DEFAULT_TITLE
    genre = args.genre or DEFAULT_GENRE
    summary = args.summary or DEFAULT_SUMMARY

    print("=" * 60)
    print("📖 创建测试小说并写入数据库")
    print("=" * 60)

    await init_db()
    print("✅ 数据库已初始化/就绪")

    async with AsyncSessionLocal() as db:
        try:
            existing = await NovelService.get_novel_by_title(db, title)
            if existing:
                print(f"⚠️  小说「{title}」已存在 (id={existing.id})")
                if not args.force:
                    print("   使用 --force 可仅初始化库并查看此提示。")
                    return
            else:
                novel = await NovelService.create_novel(db, title=title, genre=genre, summary=summary)
                print(f"✅ 创建小说: {novel.title} (id={novel.id})")

                chapter = await NovelService.create_chapter(
                    db, novel_id=novel.id, index=1, title=CHAPTER_1_TITLE
                )
                print(f"✅ 创建章节: {chapter.title} (index=1)")

                draft = await NovelService.save_draft(
                    db, chapter_id=chapter.id, content=CHAPTER_1_CONTENT
                )
                print(f"✅ 保存正文草稿 v{draft.version}")

                await NovelService.update_chapter_status(db, chapter.id, ChapterStatus.FINISHED)
                print("✅ 章节状态已设为 FINISHED")

                await db.commit()
                print(f"\n📌 小说 id: {novel.id}")
                print(f"   标题: {novel.title}")
                print(f"   章节数: 1")
        except Exception as e:
            print(f"❌ 失败: {e}")
            await db.rollback()
            raise

    print("\n" + "=" * 60)
    print("✅ 测试小说已写入数据库，可在 API / 前端中查看。")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
