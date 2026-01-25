"""
清空所有队列的脚本
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.celery_config import celery_app, AGENTS

def purge_all_queues():
    """清空所有 agent 的待消费和已消费队列"""
    print("\n" + "="*60)
    print("清空所有队列")
    print("="*60)
    
    total_purged = 0
    
    for agent in AGENTS:
        for queue_type in ['pending', 'completed']:
            queue_name = f"{agent}_{queue_type}"
            try:
                with celery_app.connection_or_acquire() as conn:
                    channel = conn.default_channel
                    purged = channel.queue_purge(queue_name)
                    print(f"  - {queue_name}: 清空了 {purged} 个消息")
                    total_purged += purged
            except Exception as e:
                print(f"  - {queue_name}: 清空失败 - {e}")
    
    print(f"\n总计清空: {total_purged} 个消息")
    print("✅ 队列清空完成")

if __name__ == "__main__":
    purge_all_queues()
