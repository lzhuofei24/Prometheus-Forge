#!/usr/bin/env python
"""测试发送任务到队列"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis
from src.core.celery_config import celery_app

def test_send_task():
    """测试发送任务到队列"""
    print("=" * 60)
    print("测试发送任务到队列")
    print("=" * 60)
    
    # 1. 检查 Redis 连接
    print("\n1. 检查 Redis 连接:")
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("   ✅ Redis 连接成功")
    except Exception as e:
        print(f"   ❌ Redis 连接失败: {e}")
        return
    
    # 2. 检查队列初始状态
    print("\n2. 检查队列初始状态:")
    initial_length = r.llen('architect_pending')
    print(f"   architect_pending 队列长度: {initial_length}")
    
    # 3. 发送测试任务
    print("\n3. 发送测试任务:")
    try:
        result = celery_app.send_task(
            "architect.generate_outline",
            queue="architect_pending",
            args=["test-workflow-123", "测试小说", 1]
        )
        print(f"   ✅ 任务已发送")
        print(f"   任务 ID: {result.id}")
        print(f"   任务名称: architect.generate_outline")
        print(f"   队列: architect_pending")
    except Exception as e:
        print(f"   ❌ 发送任务失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. 检查队列状态
    print("\n4. 检查队列状态（发送后）:")
    import time
    time.sleep(0.5)  # 等待任务进入队列
    new_length = r.llen('architect_pending')
    print(f"   architect_pending 队列长度: {new_length}")
    
    if new_length > initial_length:
        print(f"   ✅ 任务已添加到队列（增加了 {new_length - initial_length} 个任务）")
    else:
        print(f"   ⚠️  队列长度未增加，可能任务未正确发送")
    
    # 5. 检查任务详情
    if new_length > 0:
        print("\n5. 队列中的任务:")
        tasks = r.lrange('architect_pending', 0, min(2, new_length - 1))
        for i, task in enumerate(tasks):
            try:
                import json
                task_data = json.loads(task)
                task_name = task_data.get('headers', {}).get('task', 'unknown')
                task_id = task_data.get('headers', {}).get('id', 'unknown')
                print(f"   [{i+1}] {task_name} (ID: {task_id})")
            except Exception as e:
                print(f"   [{i+1}] 解析失败: {e}")
                print(f"       原始数据: {task[:200]}...")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n提示:")
    print("1. 如果任务已发送但队列长度未增加，可能是任务被立即处理了")
    print("2. 检查 Architect Worker 是否正在运行")
    print("3. 检查浏览器控制台和后端日志，查看是否有错误信息")

if __name__ == '__main__':
    try:
        test_send_task()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
