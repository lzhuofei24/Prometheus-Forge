#!/usr/bin/env python
"""测试 Agent 禁用/启用功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis
import time
from src.core.celery_config import celery_app

def test_agent_disable():
    """测试 agent 禁用/启用功能。所有 agent 初始状态为禁用。"""
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    def is_disabled(a):
        v = redis_client.get(f"agent:{a}:disabled")
        return (v or "1") == "1"
    
    AGENTS = ['architect', 'writer', 'critic', 'media', 'knowledge', 'censor']
    
    print("=" * 60)
    print("Agent 禁用/启用功能测试（初始状态：全部禁用）")
    print("=" * 60)
    
    # 1. 检查当前状态
    print("\n1. 检查当前 Agent 状态:")
    for agent in AGENTS:
        status = "已禁用" if is_disabled(agent) else "已启用"
        print(f"   {agent:12} : {status}")
    
    # 2. 测试禁用
    print("\n2. 测试禁用 Architect:")
    redis_client.set("agent:architect:disabled", "1")
    print(f"   设置后状态: {'已禁用' if is_disabled('architect') else '已启用'}")
    
    # 3. 测试启用
    print("\n3. 测试启用 Architect:")
    redis_client.set("agent:architect:disabled", "0")
    print(f"   设置后状态: {'已禁用' if is_disabled('architect') else '已启用'}")
    
    # 4. 批量测试所有 agent
    print("\n4. 批量禁用所有 Agent:")
    for agent in AGENTS:
        redis_client.set(f"agent:{agent}:disabled", "1")
        print(f"   {agent:12} : {'已禁用' if is_disabled(agent) else '已启用'}")
    
    print("\n5. 批量启用所有 Agent:")
    for agent in AGENTS:
        redis_client.set(f"agent:{agent}:disabled", "0")
        print(f"   {agent:12} : {'已禁用' if is_disabled(agent) else '已启用'}")
    
    # 6. 测试任务阻塞逻辑
    print("\n6. 测试任务阻塞逻辑:")
    print("   禁用 Architect 后，发送一个测试任务...")
    redis_client.set("agent:architect:disabled", "1")
    
    # 发送一个测试任务（如果任务系统可用）
    try:
        result = celery_app.send_task(
            "architect.generate_outline",
            queue="architect_pending",
            args=["test-workflow-id", "测试小说", 1]
        )
        print(f"   任务已发送: {result.id}")
        print("   注意: 任务应该会阻塞在队列中，每30秒重试一次")
        print("   当 agent 被启用后，任务会自动开始处理")
    except Exception as e:
        print(f"   无法发送任务（这是正常的，如果 worker 未运行）: {e}")
    
    # 恢复为禁用（与初始状态一致）
    redis_client.set("agent:architect:disabled", "1")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n提示:")
    print("1. 所有 agent 初始状态为禁用，需在工作流监控页点击「启用」后再处理任务")
    print("2. 禁用后任务会阻塞在待消费队列中，每30秒重试；启用后自动开始处理")
    print("3. Redis: agent:{name}:disabled = \"0\" 启用，\"1\" 或无 key 为禁用")

if __name__ == '__main__':
    try:
        test_agent_disable()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
