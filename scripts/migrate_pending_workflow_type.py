"""为 pending_writes 表添加 workflow_type 列（用于审批助手按「启动形式」筛选）。"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

default_sqlite = f"sqlite:///{project_root / 'data' / 'novel_content_db' / 'prometheus_forge.db'}"
db_url = (os.getenv("DATABASE_URL") or default_sqlite).strip()
if "sqlite" in db_url:
    # sqlite+aiosqlite:///./data/novel_content_db/prometheus_forge.db
    db_path = project_root / "data" / "novel_content_db" / "prometheus_forge.db"
else:
    print("仅支持 SQLite 迁移，当前 DATABASE_URL 非 sqlite，请手动为 pending_writes 添加 workflow_type VARCHAR(64) NULL")
    sys.exit(0)

if not db_path.exists():
    print(f"数据库文件不存在: {db_path}")
    sys.exit(1)

import sqlite3

print("=" * 60)
print("数据库迁移: pending_writes 添加 workflow_type")
print("=" * 60)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

try:
    cursor.execute("PRAGMA table_info(pending_writes)")
    columns = [col[1] for col in cursor.fetchall()]

    if "workflow_type" not in columns:
        print("\n添加 workflow_type 字段...")
        cursor.execute("ALTER TABLE pending_writes ADD COLUMN workflow_type VARCHAR(64) NULL")
        conn.commit()
        print("✓ workflow_type 已添加")
    else:
        print("\nworkflow_type 字段已存在，跳过")

    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_pending_writes_workflow_type ON pending_writes(workflow_type)")
        conn.commit()
        print("✓ ix_pending_writes_workflow_type 已创建/存在")
    except Exception as e:
        print(f"索引可能已存在: {e}")

    conn.commit()
    print("\n迁移完成")
finally:
    conn.close()
