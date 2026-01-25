"""
迁移：为 prompt_templates 增加 workflow_type 列，唯一约束改为 (key, workflow_type)。
已存在的行 workflow_type 设为 ''（默认/通用）。
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

db_path = project_root / "data" / "novel_content_db" / "prometheus_forge.db"

if not db_path.exists():
    print(f"数据库文件不存在: {db_path}")
    sys.exit(1)

import sqlite3

print("=" * 60)
print("数据库迁移: prompt_templates 增加 workflow_type")
print("=" * 60)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

try:
    cursor.execute("PRAGMA table_info(prompt_templates)")
    columns = [col[1] for col in cursor.fetchall()]
    if "workflow_type" in columns:
        print("\nworkflow_type 已存在，跳过迁移。")
        conn.close()
        sys.exit(0)

    print("\n创建新表 prompt_templates_new ...")
    cursor.execute("""
        CREATE TABLE prompt_templates_new (
            id INTEGER NOT NULL PRIMARY KEY,
            key VARCHAR(50) NOT NULL,
            workflow_type VARCHAR(50) NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            description VARCHAR(200),
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME,
            updated_at DATETIME,
            UNIQUE (key, workflow_type)
        )
    """)
    print("复制数据并设置 workflow_type='' ...")
    cursor.execute("""
        INSERT INTO prompt_templates_new (id, key, workflow_type, content, description, is_active, created_at, updated_at)
        SELECT id, key, '', content, description, is_active, created_at, updated_at
        FROM prompt_templates
    """)
    print("删除旧表并重命名...")
    cursor.execute("DROP TABLE prompt_templates")
    cursor.execute("ALTER TABLE prompt_templates_new RENAME TO prompt_templates")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_prompt_templates_key ON prompt_templates(key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_prompt_templates_workflow_type ON prompt_templates(workflow_type)")

    conn.commit()
    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)
except Exception as e:
    conn.rollback()
    print(f"\n错误: {e}")
    raise
finally:
    conn.close()
