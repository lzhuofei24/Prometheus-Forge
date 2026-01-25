import sys
from pathlib import Path
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("="*60)
print("数据库内容检查")
print("="*60)

print("\n1. Redis (db=0) - 状态管理")
print("-"*60)
try:
    import redis
    r0 = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    keys = r0.keys('*')
    print(f"总键数: {len(keys)}")
    
    workflows = [k for k in keys if k.startswith('workflow:')]
    stats = [k for k in keys if k.startswith('stats:')]
    token_stats = [k for k in keys if k.startswith('token_stats:')]
    queues = [k for k in keys if 'queue' in k.lower() or any(agent in k for agent in ['architect', 'writer', 'critic', 'media', 'knowledge'])]
    other = [k for k in keys if k not in workflows + stats + token_stats + queues]
    
    print(f"\n工作流: {len(workflows)}")
    for k in sorted(workflows)[:10]:
        if ':state' in k:
            state = r0.hgetall(k)
            print(f"  {k}: {len(state)} 个字段")
        elif ':audit' in k:
            logs = r0.lrange(k, 0, -1)
            print(f"  {k}: {len(logs)} 条日志")
        else:
            val = r0.get(k)
            print(f"  {k}: {val}")
    
    print(f"\n统计: {len(stats)}")
    for k in sorted(stats):
        val = r0.get(k)
        print(f"  {k}: {val}")
    
    print(f"\nToken统计: {len(token_stats)}")
    for k in sorted(token_stats)[:10]:
        data = r0.hgetall(k)
        print(f"  {k}: {data}")
    
    print(f"\n队列相关: {len(queues)}")
    for k in sorted(queues)[:20]:
        if r0.type(k) == 'list':
            length = r0.llen(k)
            print(f"  {k}: {length} 个消息")
        else:
            val = r0.get(k)
            print(f"  {k}: {val}")
    
    if other:
        print(f"\n其他: {len(other)}")
        for k in sorted(other)[:10]:
            val = r0.get(k)
            print(f"  {k}: {val}")
    
except Exception as e:
    print(f"连接失败: {e}")

print("\n\n2. Redis (db=1) - Celery Backend")
print("-"*60)
try:
    r1 = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
    keys = r1.keys('*')
    print(f"总键数: {len(keys)}")
    
    celery_results = [k for k in keys if k.startswith('celery-task-meta-')]
    other = [k for k in keys if k not in celery_results]
    
    print(f"\nCelery任务结果: {len(celery_results)}")
    for k in sorted(celery_results)[:10]:
        val = r1.get(k)
        if val:
            try:
                data = json.loads(val)
                status = data.get('status', 'unknown')
                print(f"  {k}: {status}")
            except:
                print(f"  {k}: {val[:50]}...")
    
    if other:
        print(f"\n其他: {len(other)}")
        for k in sorted(other)[:10]:
            val = r1.get(k)
            print(f"  {k}: {val}")
    
except Exception as e:
    print(f"连接失败: {e}")

print("\n\n3. ChromaDB")
print("-"*60)
try:
    import chromadb
    chroma_path = project_root / "data" / "novel_content_db"
    if chroma_path.exists():
        client = chromadb.PersistentClient(path=str(chroma_path))
        collections = client.list_collections()
        print(f"集合数: {len(collections)}")
        for col in collections:
            count = col.count()
            print(f"  {col.name}: {count} 条记录")
            if count > 0:
                sample = col.peek(limit=1)
                if sample['ids']:
                    print(f"    示例ID: {sample['ids'][0]}")
except Exception as e:
    print(f"检查失败: {e}")

print("\n\n4. SQLite")
print("-"*60)
sqlite_path = project_root / "data" / "novel_content_db" / "prometheus_forge.db"
if sqlite_path.exists():
    print(f"文件存在: {sqlite_path}")
    print(f"文件大小: {sqlite_path.stat().st_size / 1024:.2f} KB")
    try:
        import sqlite3
        conn = sqlite3.connect(str(sqlite_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"表数: {len(tables)}")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]};")
            count = cursor.fetchone()[0]
            print(f"  {table[0]}: {count} 条记录")
        conn.close()
    except Exception as e:
        print(f"读取失败: {e}")
else:
    print("文件不存在")

print("\n" + "="*60)
