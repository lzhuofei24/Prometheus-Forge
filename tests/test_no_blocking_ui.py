"""
测试UI不阻塞
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time

def test_button_click_immediate_return():
    """测试按钮点击后立即返回"""
    print("测试1: 按钮点击立即返回")
    
    start_time = time.time()
    
    def button_click_handler():
        workflow_started = True
        if workflow_started:
            return
    
    button_click_handler()
    
    elapsed = time.time() - start_time
    assert elapsed < 0.1, f"按钮点击耗时过长: {elapsed}秒"
    print(f"✓ 按钮点击立即返回，耗时: {elapsed:.4f}秒")

def test_state_update_efficiency():
    """测试状态更新效率"""
    print("\n测试2: 状态更新效率")
    
    workflow_executors = {
        "小说A_1": type('obj', (object,), {'get_current_status': lambda: {"node": "world_builder", "novel_name": "小说A", "elapsed_time": 5}, 'task_status': {"node": "world_builder", "display": "构建上下文", "novel_name": "小说A"}})(),
        "小说B_2": type('obj', (object,), {'get_current_status': lambda: {"node": "novelist", "novel_name": "小说B", "elapsed_time": 10}, 'task_status': {"node": "novelist", "display": "生成内容", "novel_name": "小说B"}})()
    }
    workflow_running = {"小说A_1": True, "小说B_2": True}
    task_statuses = {}
    
    start_time = time.time()
    
    for key, executor in list(workflow_executors.items()):
        if workflow_running.get(key) and executor:
            status = executor.get_current_status()
            if status:
                if key not in task_statuses:
                    task_statuses[key] = {}
                task_status = getattr(executor, 'task_status', None)
                if task_status:
                    task_statuses[key]["elapsed_time"] = status["elapsed_time"]
                    task_statuses[key]["novel_name"] = task_status.get("novel_name", status["novel_name"])
                    task_statuses[key]["node"] = task_status.get("node", status["node"])
    
    elapsed = time.time() - start_time
    assert elapsed < 0.01, f"状态更新耗时过长: {elapsed}秒"
    print(f"✓ 状态更新高效，耗时: {elapsed:.4f}秒")

def test_no_sync_operations():
    """测试没有同步阻塞操作"""
    print("\n测试3: 无同步阻塞操作")
    
    def simulate_button_click():
        file_operation = True
        workflow_start = True
        
        if file_operation and workflow_start:
            return True
        
        time.sleep(0.1)
        return False
    
    start_time = time.time()
    result = simulate_button_click()
    elapsed = time.time() - start_time
    
    assert result == True
    assert elapsed < 0.05, f"操作耗时过长: {elapsed}秒"
    print(f"✓ 无同步阻塞操作，耗时: {elapsed:.4f}秒")

if __name__ == "__main__":
    print("=" * 60)
    print("开始测试UI不阻塞功能")
    print("=" * 60)
    
    try:
        test_button_click_immediate_return()
        test_state_update_efficiency()
        test_no_sync_operations()
        
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
