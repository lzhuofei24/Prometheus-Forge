import sys
from pathlib import Path
import sqlite3

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

db_path = project_root / "data" / "novel_content_db" / "prometheus_forge.db"

if not db_path.exists():
    print(f"数据库文件不存在: {db_path}")
    sys.exit(1)

print("="*60)
print("数据库迁移: 添加缓存字段")
print("="*60)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

try:
    cursor.execute("PRAGMA table_info(chapters)")
    columns = [col[1] for col in cursor.fetchall()]
    
    print(f"\n当前 chapters 表字段: {columns}")
    
    if "active_draft_id" not in columns:
        print("\n添加 active_draft_id 字段...")
        cursor.execute("ALTER TABLE chapters ADD COLUMN active_draft_id VARCHAR(36)")
        print("✓ active_draft_id 已添加")
    else:
        print("\nactive_draft_id 字段已存在，跳过")
    
    if "latest_version" not in columns:
        print("\n添加 latest_version 字段...")
        cursor.execute("ALTER TABLE chapters ADD COLUMN latest_version INTEGER DEFAULT 0")
        print("✓ latest_version 已添加")
    else:
        print("\nlatest_version 字段已存在，跳过")
    
    print("\n创建索引...")
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapter_novel_status ON chapters(novel_id, \"index\", status)")
        print("✓ idx_chapter_novel_status 已创建")
    except Exception as e:
        print(f"索引可能已存在: {e}")
    
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_draft_chapter_active_version ON chapter_drafts(chapter_id, is_active, version)")
        print("✓ idx_draft_chapter_active_version 已创建")
    except Exception as e:
        print(f"索引可能已存在: {e}")
    
    print("\n更新现有数据...")
    cursor.execute("""
        UPDATE chapters 
        SET latest_version = (
            SELECT COALESCE(MAX(version), 0) 
            FROM chapter_drafts 
            WHERE chapter_drafts.chapter_id = chapters.id
        )
    """)
    updated = cursor.rowcount
    print(f"✓ 更新了 {updated} 个章节的 latest_version")
    
    cursor.execute("""
        UPDATE chapters 
        SET active_draft_id = (
            SELECT id 
            FROM chapter_drafts 
            WHERE chapter_drafts.chapter_id = chapters.id 
            AND chapter_drafts.is_active = 1 
            LIMIT 1
        )
    """)
    updated = cursor.rowcount
    print(f"✓ 更新了 {updated} 个章节的 active_draft_id")
    
    conn.commit()
    print("\n" + "="*60)
    print("迁移完成！")
    print("="*60)
    
except Exception as e:
    conn.rollback()
    print(f"\n错误: {e}")
    raise
finally:
    conn.close()
