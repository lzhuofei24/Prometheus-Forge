import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("="*60)
print("清理数据库")
print("="*60)

print("\n1. 清理 Redis (db=0) - 状态管理")
print("-"*60)
try:
    import redis
    r0 = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    old_queues = ['text_queue', 'media_queue', 'rag_queue']
    workflows = []
    stats_keys = []
    
    keys = r0.keys('*')
    
    for k in keys:
        if k.startswith('workflow:'):
            workflows.append(k)
        elif k.startswith('stats:'):
            stats_keys.append(k)
    
    deleted_queues = 0
    for q in old_queues:
        if q in keys:
            if r0.type(q) == 'list':
                length = r0.llen(q)
                r0.delete(q)
                print(f"  删除 {q}: {length} 个消息")
                deleted_queues += 1
            else:
                r0.delete(q)
                print(f"  删除 {q}")
                deleted_queues += 1
    
    print(f"\n删除工作流: {len(workflows)} 个")
    for k in workflows:
        r0.delete(k)
    
    print(f"删除统计: {len(stats_keys)} 个")
    for k in stats_keys:
        r0.delete(k)
    
    remaining = len(r0.keys('*'))
    print(f"\n剩余键数: {remaining}")
    
except Exception as e:
    print(f"清理失败: {e}")

print("\n\n2. 清理 Redis (db=1) - Celery Backend")
print("-"*60)
try:
    r1 = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
    keys = r1.keys('*')
    celery_results = [k for k in keys if k.startswith('celery-task-meta-')]
    
    print(f"删除 Celery 任务结果: {len(celery_results)} 个")
    for k in celery_results:
        r1.delete(k)
    
    remaining = len(r1.keys('*'))
    print(f"剩余键数: {remaining}")
    
except Exception as e:
    print(f"清理失败: {e}")

print("\n\n3. ChromaDB")
print("-"*60)
try:
    import chromadb
    chroma_path = project_root / "data" / "novel_content_db"
    if chroma_path.exists():
        client = chromadb.PersistentClient(path=str(chroma_path))
        collections = client.list_collections()
        print(f"发现集合: {len(collections)} 个")
        for col in collections:
            count = col.count()
            print(f"  删除集合 {col.name}: {count} 条记录")
            client.delete_collection(col.name)
    else:
        print("ChromaDB 路径不存在")
except Exception as e:
    print(f"清理失败: {e}")

print("\n\n4. SQLite")
print("-"*60)
sqlite_path = project_root / "data" / "novel_content_db" / "prometheus_forge.db"
if sqlite_path.exists():
    print(f"文件: {sqlite_path}")
    try:
        import sqlite3
        conn = sqlite3.connect(str(sqlite_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"清空表: {len(tables)} 个")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]};")
            count = cursor.fetchone()[0]
            cursor.execute(f"DELETE FROM {table[0]};")
            print(f"  已清空 {table[0]}: {count} 条记录")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"清理失败: {e}")
else:
    print("文件不存在")

print("\n" + "="*60)
print("清理完成")
