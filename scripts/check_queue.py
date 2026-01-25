#!/usr/bin/env python
"""检查 Celery 队列状态"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis
from src.core.celery_config import celery_app

def check_queue_status():
    """检查各个队列的长度"""
    r = redis.Redis(host='localhost', port=6379, db=0)
    
    queues = [
        'architect_pending',
        'writer_pending',
        'critic_pending',
        'media_pending',
        'knowledge_pending',
        'censor_pending',
        'controller_pending',
    ]
    
    print("=" * 60)
    print("队列状态检查")
    print("=" * 60)
    
    for queue in queues:
        length = r.llen(queue)
        if length > 0:
            print(f"✅ {queue}: {length} 个任务等待处理")
            # 显示队列中的前几个任务
            tasks = r.lrange(queue, 0, min(2, length - 1))
            for i, task in enumerate(tasks):
                try:
                    import json
                    task_data = json.loads(task)
                    task_name = task_data.get('headers', {}).get('task', 'unknown')
                    print(f"   [{i+1}] {task_name}")
                except:
                    print(f"   [{i+1}] {task[:100]}...")
        else:
            print(f"⚪ {queue}: 空")
    
    print("=" * 60)
    print("\n任务路由配置:")
    print(f"  architect.* -> {celery_app.conf.task_routes.get('architect.*', {}).get('queue', 'default')}")
    print(f"  writer.* -> {celery_app.conf.task_routes.get('writer.*', {}).get('queue', 'default')}")
    print("=" * 60)

if __name__ == '__main__':
    try:
        check_queue_status()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
