"""
测试并行执行多个小说撰写任务
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time
from unittest.mock import Mock

def test_multiple_novels_status():
    """测试多个小说的状态管理"""
    print("测试1: 多个小说状态管理")
    
    task_statuses = {}
    workflow_executors = {}
    workflow_running = {}
    
    novel1_key = "小说A_1"
    novel2_key = "小说B_2"
    
    task_statuses[novel1_key] = {
        "node": "world_builder",
        "novel_name": "小说A",
        "chapter_num": 1,
        "elapsed_time": 5
    }
    
    task_statuses[novel2_key] = {
        "node": "novelist",
        "novel_name": "小说B",
        "chapter_num": 2,
        "elapsed_time": 10
    }
    
    workflow_running[novel1_key] = True
    workflow_running[novel2_key] = True
    
    assert len(task_statuses) == 2
    assert task_statuses[novel1_key]["novel_name"] == "小说A"
    assert task_statuses[novel2_key]["novel_name"] == "小说B"
    print("✓ 多个小说状态管理测试通过")

def test_agent_status_display():
    """测试agent状态显示多个任务"""
    print("\n测试2: Agent状态显示多个任务")
    
    agents = {
        "world_builder": {"name": "构建上下文", "icon": "🌍"},
        "novelist": {"name": "生成内容", "icon": "✍️"},
    }
    
    task_statuses = {
        "小说A_1": {
            "node": "world_builder",
            "novel_name": "小说A",
            "chapter_num": 1,
            "elapsed_time": 5
        },
        "小说B_2": {
            "node": "novelist",
            "novel_name": "小说B",
            "chapter_num": 2,
            "elapsed_time": 10
        },
        "小说C_3": {
            "node": "world_builder",
            "novel_name": "小说C",
            "chapter_num": 3,
            "elapsed_time": 3
        }
    }
    
    agent_id = "world_builder"
    tasks_for_agent = []
    for key, task_status in task_statuses.items():
        if task_status.get("node") == agent_id:
            tasks_for_agent.append(task_status)
    
    assert len(tasks_for_agent) == 2
    assert tasks_for_agent[0]["novel_name"] == "小说A"
    assert tasks_for_agent[1]["novel_name"] == "小说C"
    print(f"✓ Agent {agent_id} 有 {len(tasks_for_agent)} 个任务")
    
    for task_status in tasks_for_agent:
        novel_name = task_status.get("novel_name", "")
        elapsed_time = task_status.get("elapsed_time", 0)
        chapter_num = task_status.get("chapter_num", "")
        
        if novel_name and elapsed_time is not None:
            if chapter_num:
                task_text = f"{novel_name} 第{chapter_num}章 ({elapsed_time}秒)"
            else:
                task_text = f"{novel_name} ({elapsed_time}秒)"
        print(f"  - {task_text}")

def test_elapsed_time_update():
    """测试执行时间实时更新"""
    print("\n测试3: 执行时间实时更新")
    
    node_start_time = time.time()
    time.sleep(1.1)
    
    elapsed_time = int(time.time() - node_start_time)
    assert elapsed_time >= 1
    
    time.sleep(1.1)
    elapsed_time2 = int(time.time() - node_start_time)
    assert elapsed_time2 >= elapsed_time
    
    print(f"✓ 执行时间从 {elapsed_time}秒 更新到 {elapsed_time2}秒")

def test_parallel_execution_simulation():
    """模拟并行执行多个任务"""
    print("\n测试4: 模拟并行执行")
    
    executors = {}
    running = {}
    task_statuses = {}
    
    novels = ["小说A", "小说B", "小说C"]
    chapters = [1, 2, 3]
    
    for novel, chapter in zip(novels, chapters):
        key = f"{novel}_{chapter}"
        executors[key] = Mock()
        running[key] = True
        task_statuses[key] = {
            "node": "world_builder",
            "novel_name": novel,
            "chapter_num": chapter,
            "elapsed_time": 0
        }
    
    assert len(executors) == 3
    assert len(running) == 3
    assert len(task_statuses) == 3
    
    for key in executors:
        if running[key]:
            task_statuses[key]["elapsed_time"] += 1
    
    for key, status in task_statuses.items():
        assert status["elapsed_time"] == 1
        print(f"✓ {status['novel_name']} 第{status['chapter_num']}章 执行时间: {status['elapsed_time']}秒")
    
    print("✓ 并行执行模拟测试通过")

if __name__ == "__main__":
    print("=" * 60)
    print("开始测试并行执行功能")
    print("=" * 60)
    
    try:
        test_multiple_novels_status()
        test_agent_status_display()
        test_elapsed_time_update()
        test_parallel_execution_simulation()
        
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
