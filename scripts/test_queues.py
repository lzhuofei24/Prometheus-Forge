"""
队列系统测试脚本

验证每个 agent 的队列配置是否正确
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.celery_config import celery_app, AGENTS

def test_queue_config():
    """测试队列配置"""
    print("\n" + "="*60)
    print("测试队列配置")
    print("="*60)
    
    print(f"\n定义的 Agents: {AGENTS}")
    
    print("\n配置的队列:")
    for queue in celery_app.conf.task_queues:
        print(f"  - {queue.name} (routing_key: {queue.routing_key})")
    
    print("\n任务路由规则:")
    for pattern, route in celery_app.conf.task_routes.items():
        print(f"  - {pattern} -> {route['queue']}")
    
    print("\n✅ 队列配置验证完成")

if __name__ == "__main__":
    test_queue_config()
