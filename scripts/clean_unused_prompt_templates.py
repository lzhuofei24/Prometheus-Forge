#!/usr/bin/env python
"""查询数据库中的提示词模板，删除「系统未使用」的 key。

系统使用的 key 以 src.api.routers.prompts.EXPECTED_KEYS 为准；
本脚本与 seed_prompt_templates 使用相同列表，保证一致。

用法（项目根目录执行）:
  python scripts/clean_unused_prompt_templates.py

数据库默认: data/novel_content_db/prometheus_forge.db
可通过环境变量 DATABASE_URL 指定（sqlite:/// 或 sqlite+aiosqlite:///）。
"""

import os
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
default_db = project_root / "data" / "novel_content_db" / "prometheus_forge.db"

# 与 src.api.routers.prompts 以及 seed_prompt_templates 一致
EXPECTED_KEYS = [
    "fiction_system",
    "writing",
    "critique",
    "critique_handler",
    "extraction",
    "plot_check",
    "style_check",
    "character_check",
    "censor",
    "architect",
    "writer_builder",
    "knowledge_extraction",
    "knowledge_summary",
    "media_prompt_engineering",
]


def _db_path() -> Path:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("sqlite+aiosqlite:///"):
        p = url.replace("sqlite+aiosqlite:///", "", 1)
        return Path(p) if os.path.isabs(p) else (project_root / p)
    if url.startswith("sqlite:///"):
        p = url.replace("sqlite:///", "", 1)
        return Path(p) if os.path.isabs(p) else (project_root / p)
    return default_db


def main() -> None:
    db_path = _db_path()
    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute("SELECT id, key FROM prompt_templates ORDER BY key")
        rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        if "no such table" in str(e).lower():
            print("表 prompt_templates 不存在，无需清理。")
            conn.close()
            return
        raise

    expected = set(EXPECTED_KEYS)
    to_delete = [r["key"] for r in rows if r["key"] not in expected]
    to_keep = [r["key"] for r in rows if r["key"] in expected]

    print("=" * 60)
    print("提示词模板清理：删除系统未使用的 key")
    print("=" * 60)
    print(f"\n系统使用的 key（共 {len(EXPECTED_KEYS)} 个）: {', '.join(EXPECTED_KEYS)}")
    print(f"数据库中当前共 {len(rows)} 条记录。")

    if not to_delete:
        print("\n无需删除：所有记录均在预期 key 中。")
        print(f"保留: {', '.join(to_keep) if to_keep else '(无)'}")
        conn.close()
        return

    print(f"\n将删除的 key（共 {len(to_delete)} 个）: {', '.join(to_delete)}")
    for k in to_delete:
        cur.execute("DELETE FROM prompt_templates WHERE key = ?", (k,))
    deleted = cur.rowcount
    conn.commit()
    print(f"已删除 {len(to_delete)} 条。")

    cur.execute("SELECT key FROM prompt_templates ORDER BY key")
    remaining = [r["key"] for r in cur.fetchall()]
    print(f"删除后保留的 key（共 {len(remaining)} 个）: {', '.join(remaining)}")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
