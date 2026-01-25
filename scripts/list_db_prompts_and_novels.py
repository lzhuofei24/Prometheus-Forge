#!/usr/bin/env python
"""查看数据库中所有提示词模板和小说（含章节数）。

仅使用标准库 sqlite3，不依赖项目内会加载异步引擎的模块。
用法（在项目根目录执行）:
  python scripts/list_db_prompts_and_novels.py

数据库默认: data/novel_content_db/prometheus_forge.db
可通过环境变量 DATABASE_URL 指定，如: sqlite:///./data/novel_content_db/prometheus_forge.db
"""

import os
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
default_db = project_root / "data" / "novel_content_db" / "prometheus_forge.db"


def _db_path():
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("sqlite:///"):
        p = url.replace("sqlite:///", "", 1)
        return Path(p) if os.path.isabs(p) else (project_root / p)
    return default_db


def main():
    print("=" * 60)
    print("数据库内容查看：提示词模板 & 小说")
    print("=" * 60)

    db_path = _db_path()
    if not db_path.exists():
        print(f"\n数据库文件不存在: {db_path}")
        print("请先启动过 API 或执行初始化以创建数据库。")
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
    except Exception as e:
        print(f"\n无法连接数据库: {e}")
        sys.exit(1)

    try:
        # ---------- 提示词模板 ----------
        print("\n【提示词模板】 prompt_templates")
        print("-" * 50)
        try:
            cur.execute(
                "SELECT id, key, content, description, is_active FROM prompt_templates ORDER BY key"
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                print("  (表 prompt_templates 不存在)")
                rows = []
            else:
                raise
        if rows:
            for i, r in enumerate(rows, 1):
                key = r["key"]
                active = "启用" if (r["is_active"] is None or r["is_active"]) else "停用"
                desc = f" — {r['description']}" if r["description"] else ""
                print(f"  {i}. key={key!r} {active}{desc}")
                if r["content"]:
                    s = r["content"][:80] + "…" if len(r["content"]) > 80 else r["content"]
                    print(f"      内容预览: {s}")
        else:
            print("  (无记录)")

        # ---------- 小说与章节数 ----------
        print("\n【小说】 novels")
        print("-" * 50)
        try:
            cur.execute("SELECT id, title, genre, summary FROM novels ORDER BY created_at DESC")
            novels = cur.fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                print("  (表 novels 不存在)")
                novels = []
            else:
                raise
        if novels:
            for n in novels:
                cur.execute("SELECT COUNT(*) as cnt FROM chapters WHERE novel_id = ?", (n["id"],))
                num_ch = cur.fetchone()["cnt"]
                print(f"  id: {n['id']}")
                print(f"  标题: {n['title']}")
                if n["genre"]:
                    print(f"  类型: {n['genre']}")
                if n["summary"]:
                    s = n["summary"][:60] + "…" if len(n["summary"]) > 60 else n["summary"]
                    print(f"  简介: {s}")
                print(f"  章节数: {num_ch}")
                print()
        else:
            print("  (无记录)")

    finally:
        conn.close()

    print("=" * 60)
    print("完毕")
    print("=" * 60)


if __name__ == "__main__":
    main()
