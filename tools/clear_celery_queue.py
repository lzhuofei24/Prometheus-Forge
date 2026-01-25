"""
清除 Redis 中的 Celery 任务队列

清除内容：
- text_queue (文本生成任务)
- media_queue (图片/音频生成任务)
- rag_queue (RAG 索引任务)
- celery backend results (任务结果缓存)
"""

import redis
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def clear_celery_queues():
    """清除所有 Celery 队列"""
    
    # 连接到 Redis
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    print("📋 当前队列状态:")
    print("="*60)
    
    queues = ['text_queue', 'media_queue', 'rag_queue']
    total_tasks = 0
    
    for queue in queues:
        count = r.llen(queue)
        total_tasks += count
        print(f"  - {queue}: {count} 个任务")
    
    # 检查 celery backend keys
    celery_keys = r.keys('celery-task-meta-*')
    print(f"  - celery-task-meta: {len(celery_keys)} 个结果缓存")
    
    print("="*60)
    print(f"\n总计: {total_tasks} 个队列任务 + {len(celery_keys)} 个结果缓存\n")
    
    if total_tasks == 0 and len(celery_keys) == 0:
        print("✅ 队列已经是空的，无需清除")
        return
    
    # 清除队列
    print("🗑️  开始清除...")
    
    for queue in queues:
        count = r.llen(queue)
        if count > 0:
            r.delete(queue)
            print(f"  ✅ 已清除 {queue}: {count} 个任务")
    
    # 清除 celery backend results
    if celery_keys:
        for key in celery_keys:
            r.delete(key)
        print(f"  ✅ 已清除 celery-task-meta: {len(celery_keys)} 个结果缓存")
    
    # 清除其他可能的 celery keys
    other_keys = []
    for pattern in ['_kombu.*', 'unacked*', 'unacked_mutex*']:
        other_keys.extend(r.keys(pattern))
    
    if other_keys:
        for key in other_keys:
            r.delete(key)
        print(f"  ✅ 已清除其他 Celery keys: {len(other_keys)} 个")
    
    print("\n✅ 清除完成！")
    
    # 验证清除结果
    print("\n📋 清除后队列状态:")
    print("="*60)
    for queue in queues:
        count = r.llen(queue)
        print(f"  - {queue}: {count} 个任务")
    
    remaining_celery_keys = r.keys('celery-task-meta-*')
    print(f"  - celery-task-meta: {len(remaining_celery_keys)} 个结果缓存")
    print("="*60)


if __name__ == "__main__":
    try:
        clear_celery_queues()
    except redis.ConnectionError:
        print("❌ 无法连接到 Redis，请确保 Redis 服务正在运行")
        print("   提示: docker-compose up -d redis")
    except Exception as e:
        print(f"❌ 清除失败: {e}")
        import traceback
        traceback.print_exc()
