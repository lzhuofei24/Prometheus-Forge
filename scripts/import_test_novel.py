#!/usr/bin/env python
"""
从 txt 文件导入一篇测试小说到数据库（自动按「第X章」分章）。

用法（在项目根目录执行，建议先激活 conda 环境 novel-agent）:
  conda activate novel-agent
  python scripts/import_test_novel.py --file tests/fixtures/test_novel.txt --title "虚拟世界历险记"
  python scripts/import_test_novel.py --file path/to/your.txt --title "我的小说" [--genre "科幻"]
"""
import argparse
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.core.database import init_db, AsyncSessionLocal
from src.api.models import Novel, Chapter, ChapterDraft, ChapterStatus  # noqa: F401
from src.api.services.novel_service import NovelService
from src.api.services.import_service import ImportService


async def main():
    parser = argparse.ArgumentParser(description="从 txt 导入测试小说到数据库")
    parser.add_argument("--file", "-f", type=str, required=True, help="txt 文件路径")
    parser.add_argument("--title", "-t", type=str, required=True, help="小说标题")
    parser.add_argument("--genre", "-g", type=str, default=None, help="类型，如 玄幻/科幻")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        print(f"❌ 文件不存在: {path}")
        sys.exit(1)
    if path.suffix.lower() != ".txt":
        print("❌ 仅支持 .txt 文件")
        sys.exit(1)

    print("=" * 60)
    print("📖 从 txt 导入测试小说")
    print("=" * 60)

    await init_db()
    print("✅ 数据库已就绪")

    content = path.read_bytes()
    async with AsyncSessionLocal() as db:
        try:
            svc = ImportService()
            result = await svc.import_txt_novel(
                db=db,
                file_content=content,
                novel_title=args.title.strip(),
                genre=args.genre,
            )
            await db.commit()
            print(f"✅ 小说: {result['novel_title']} (id={result['novel_id']})")
            print(f"✅ 章节数: {result['chapters_count']}")
            print(f"\n📌 novel_id: {result['novel_id']}")
        except ValueError as e:
            print(f"❌ {e}")
            await db.rollback()
            sys.exit(1)
        except Exception as e:
            print(f"❌ 导入失败: {e}")
            await db.rollback()
            raise

    print("=" * 60)
    print("✅ 导入完成，可在 API / 前端中查看。")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
