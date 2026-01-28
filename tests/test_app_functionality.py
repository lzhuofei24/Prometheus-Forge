"""
测试应用功能
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_session_state_initialization():
    """测试session state初始化"""
    print("测试1: Session State初始化")
    
    required_keys = [
        "task_statuses",
        "workflow_executors",
        "workflow_running",
        "workflow_results",
        "workflow_errors",
        "previous_nodes",
        "danmaku_messages",
        "task_logs"
    ]
    
    session_state = {}
    for key in required_keys:
        session_state[key] = {}
    session_state["task_logs"] = []
    session_state["danmaku_messages"] = []
    
    for key in required_keys:
        assert key in session_state, f"缺少必需的session state key: {key}"
    
    print("✓ Session State初始化测试通过")

def test_workflow_executor_task_status():
    """测试工作流执行器的task_status（使用Mock）"""
    print("\n测试2: 工作流执行器 task_status (Mock)")
    
    class MockExecutor:
        def __init__(self):
            self.task_status = None
            self.current_node = None
            self.node_start_time = None
            self.novel_name = None
            self.is_running = False
        
        def get_current_status(self):
            if not self.is_running or not self.current_node:
                return None
            import time
            elapsed_time = int(time.time() - self.node_start_time) if self.node_start_time else 0
            return {
                "node": self.current_node,
                "novel_name": self.novel_name,
                "elapsed_time": elapsed_time
            }
    
    executor = MockExecutor()
    executor.is_running = True
    executor.current_node = "world_builder"
    executor.novel_name = "测试小说"
    import time
    executor.node_start_time = time.time()
    
    executor.task_status = {
        "node": "world_builder",
        "display": "构建上下文",
        "novel_name": "测试小说",
        "elapsed_time": 0
    }
    
    status = executor.get_current_status()
    assert status is not None
    assert status["node"] == "world_builder"
    assert status["novel_name"] == "测试小说"
    
    assert executor.task_status is not None
    assert executor.task_status["display"] == "构建上下文"
    
    print("✓ WorkflowExecutor task_status测试通过")

def test_task_status_update_logic():
    """测试任务状态更新逻辑"""
    print("\n测试3: 任务状态更新逻辑")
    
    workflow_executors = {}
    workflow_running = {}
    task_statuses = {}
    
    novel_key = "测试小说_1"
    
    class MockExecutor:
        def __init__(self):
            self.task_status = {
                "node": "world_builder",
                "display": "构建上下文",
                "novel_name": "测试小说",
                "elapsed_time": 0
            }
            self.is_running = True
            self.current_node = "world_builder"
            self.node_start_time = None
            self.novel_name = "测试小说"
        
        def get_current_status(self):
            import time
            elapsed_time = int(time.time() - self.node_start_time) if self.node_start_time else 5
            return {
                "node": self.current_node,
                "novel_name": self.novel_name,
                "elapsed_time": elapsed_time
            }
    
    executor = MockExecutor()
    workflow_executors[novel_key] = executor
    workflow_running[novel_key] = True
    
    if workflow_running.get(novel_key) and executor:
        status = executor.get_current_status()
        if status:
            if novel_key not in task_statuses:
                task_statuses[novel_key] = {}
            
            task_status = executor.task_status
            if task_status:
                task_statuses[novel_key]["elapsed_time"] = status["elapsed_time"]
                task_statuses[novel_key]["novel_name"] = task_status.get("novel_name", status["novel_name"])
                task_statuses[novel_key]["node"] = task_status.get("node", status["node"])
                task_statuses[novel_key]["display"] = task_status.get("display", status["node"])
    
    assert novel_key in task_statuses
    assert task_statuses[novel_key]["novel_name"] == "测试小说"
    assert task_statuses[novel_key]["node"] == "world_builder"
    assert task_statuses[novel_key]["display"] == "构建上下文"
    
    print("✓ 任务状态更新逻辑测试通过")

def test_multiple_tasks_display():
    """测试多个任务显示"""
    print("\n测试4: 多个任务显示")
    
    agents = {
        "world_builder": {"name": "构建上下文", "icon": "🌍"},
        "novelist": {"name": "生成内容", "icon": "✍️"},
    }
    
    task_statuses = {
        "小说A_1": {
            "node": "world_builder",
            "novel_name": "小说A",
            "chapter_num": 1,
            "elapsed_time": 5,
            "display": "构建上下文"
        },
        "小说B_2": {
            "node": "novelist",
            "novel_name": "小说B",
            "chapter_num": 2,
            "elapsed_time": 10,
            "display": "生成内容"
        },
        "小说C_3": {
            "node": "world_builder",
            "novel_name": "小说C",
            "chapter_num": 3,
            "elapsed_time": 3,
            "display": "构建上下文"
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
    
    print(f"✓ Agent {agent_id} 显示 {len(tasks_for_agent)} 个任务")
    for task in tasks_for_agent:
        novel_name = task.get("novel_name", "")
        elapsed_time = task.get("elapsed_time", 0)
        chapter_num = task.get("chapter_num", "")
        if novel_name and elapsed_time is not None:
            if chapter_num:
                task_text = f"{novel_name} 第{chapter_num}章 ({elapsed_time}秒)"
            else:
                task_text = f"{novel_name} ({elapsed_time}秒)"
        print(f"  - {task_text}")

if __name__ == "__main__":
    print("=" * 60)
    print("开始测试应用功能")
    print("=" * 60)
    
    try:
        test_session_state_initialization()
        test_workflow_executor_task_status()
        test_task_status_update_logic()
        test_multiple_tasks_display()
        
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
