"""创建 system_concepts 表并写入默认概念（若表已存在则跳过建表）。"""
import os
import sys
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timezone

project_root = Path(__file__).parent.parent
default_sqlite = f"sqlite:///{project_root / 'data' / 'novel_content_db' / 'prometheus_forge.db'}"
db_url = os.getenv("DATABASE_URL", default_sqlite).strip()
if "sqlite" in db_url:
    db_path = project_root / "data" / "novel_content_db" / "prometheus_forge.db"
else:
    print("仅支持 SQLite；其他库请手动建表 system_concepts 并插入默认概念")
    sys.exit(0)

if not db_path.exists():
    print(f"数据库不存在: {db_path}")
    sys.exit(1)

DEFAULTS = [
    ("flow_type", "流程类型", "如「生成新章节」「仅生成大纲」等，表示一种任务流程的模板。在流程监控中切换的是流程类型。", "workflow", 10),
    ("run", "运行", "一次具体的任务执行，有唯一运行 ID。一次「运行」属于某种「流程类型」。", "workflow", 20),
    ("start_form", "启动形式", "与「流程类型」同义，偏重「以何种方式启动」的含义。", "approval", 30),
    ("workflow_monitor", "流程监控", "用于查看各环节队列、拓扑与调度的页面。", "nav", 40),
    ("pending_write", "待审批写入", "Agent 产出的大纲或正文在落库前需用户审批的记录。", "approval", 50),
]

def main():
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_concepts'")
    if not cur.fetchone():
        cur.execute("""
            CREATE TABLE system_concepts (
                id VARCHAR(36) PRIMARY KEY,
                key VARCHAR(64) NOT NULL UNIQUE,
                label VARCHAR(128) NOT NULL,
                description TEXT,
                scope VARCHAR(64),
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS ix_system_concepts_key ON system_concepts(key)")
        conn.commit()
        print("已创建 system_concepts 表")
    for key, label, desc, scope, order in DEFAULTS:
        cur.execute("SELECT 1 FROM system_concepts WHERE key = ?", (key,))
        if not cur.fetchone():
            uid = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "INSERT INTO system_concepts (id, key, label, description, scope, sort_order, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (uid, key, label, desc, scope, order, now, now),
            )
            print(f"  插入概念: {key} -> {label}")
    conn.commit()
    conn.close()
    print("迁移完成")

if __name__ == "__main__":
    main()
