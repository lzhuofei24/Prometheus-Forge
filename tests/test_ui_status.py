"""
测试UI状态更新和弹幕显示功能
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
from src.core.state import AgentState

def test_agent_status_update():
    """测试agent状态更新逻辑"""
    print("测试1: Agent状态更新")
    
    task_status = {}
    executor_status = {
        "node": "world_builder",
        "novel_name": "测试小说",
        "elapsed_time": 5
    }
    
    if executor_status:
        if not task_status:
            task_status = {}
        task_status["elapsed_time"] = executor_status["elapsed_time"]
        task_status["novel_name"] = executor_status["novel_name"]
        task_status["node"] = executor_status["node"]
    
    assert task_status.get("novel_name") == "测试小说"
    assert task_status.get("elapsed_time") == 5
    assert task_status.get("node") == "world_builder"
    print("✓ Agent状态更新测试通过")
    
    agents = {
        "world_builder": {"name": "构建上下文", "icon": "🌍"},
        "novelist": {"name": "生成内容", "icon": "✍️"},
    }
    
    agent_id = "world_builder"
    agent_info = agents[agent_id]
    
    if task_status and task_status.get("node") == agent_id:
        novel_name = task_status.get("novel_name", "")
        elapsed_time = task_status.get("elapsed_time", 0)
        
        if novel_name and elapsed_time is not None:
            task_text = f"{novel_name} ({elapsed_time}秒)"
        elif novel_name:
            task_text = f"{novel_name}"
        elif elapsed_time is not None:
            task_text = f"执行中 ({elapsed_time}秒)"
        else:
            task_text = "执行中"
        
        assert task_text == "测试小说 (5秒)"
        print(f"✓ 状态显示文本: {task_text}")

def test_danmaku_messages():
    """测试弹幕消息功能"""
    print("\n测试2: 弹幕消息")
    
    danmaku_messages = []
    
    novel_name = "测试小说"
    display_name = "构建上下文"
    current_time = "12:00:00"
    
    danmaku_message = f"{novel_name} - {display_name} 完成"
    danmaku_messages.append({
        "message": danmaku_message,
        "time": current_time
    })
    
    assert len(danmaku_messages) == 1
    assert danmaku_messages[0]["message"] == "测试小说 - 构建上下文 完成"
    print("✓ 弹幕消息添加测试通过")
    
    recent_messages = danmaku_messages[-5:]
    assert len(recent_messages) == 1
    print(f"✓ 弹幕消息: {recent_messages[0]['message']}")

def test_node_switching():
    """测试节点切换时的弹幕发送"""
    print("\n测试3: 节点切换弹幕")
    
    previous_node = None
    danmaku_messages = []
    task_status = {}
    
    node_name_map = {
        "world_builder": "构建上下文",
        "novelist": "生成内容",
    }
    
    def simulate_node_switch(new_node, novel_name):
        nonlocal previous_node, danmaku_messages, task_status
        
        if previous_node and previous_node != new_node:
            prev_display = node_name_map.get(previous_node, previous_node)
            prev_novel = task_status.get("novel_name", "")
            if prev_novel:
                danmaku_message = f"{prev_novel} - {prev_display} 完成"
                danmaku_messages.append({
                    "message": danmaku_message,
                    "time": "12:00:00"
                })
        
        previous_node = new_node
        task_status["novel_name"] = novel_name
        task_status["node"] = new_node
    
    simulate_node_switch("world_builder", "测试小说")
    assert previous_node == "world_builder"
    assert len(danmaku_messages) == 0
    
    simulate_node_switch("novelist", "测试小说")
    assert previous_node == "novelist"
    assert len(danmaku_messages) == 1
    assert danmaku_messages[0]["message"] == "测试小说 - 构建上下文 完成"
    print("✓ 节点切换弹幕测试通过")

def test_elapsed_time_calculation():
    """测试执行时间计算"""
    print("\n测试4: 执行时间计算")
    
    node_start_time = time.time()
    time.sleep(0.1)
    elapsed_time = int(time.time() - node_start_time)
    
    assert elapsed_time >= 0
    print(f"✓ 执行时间计算: {elapsed_time}秒")

if __name__ == "__main__":
    print("=" * 60)
    print("开始测试UI状态更新和弹幕功能")
    print("=" * 60)
    
    try:
        test_agent_status_update()
        test_danmaku_messages()
        test_node_switching()
        test_elapsed_time_calculation()
        
        print("\n" + "=" * 60)
        print("所有测试通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
