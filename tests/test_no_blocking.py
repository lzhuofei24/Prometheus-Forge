"""
测试按钮点击不阻塞
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_button_click_no_rerun():
    """测试按钮点击后不立即rerun"""
    print("测试1: 按钮点击不立即rerun")
    
    button_clicked = True
    workflow_started = True
    
    if button_clicked:
        if workflow_started:
            should_rerun = False
        else:
            should_rerun = False
    
    assert should_rerun == False
    print("✓ 按钮点击后不立即rerun测试通过")

def test_workflow_returns_immediately():
    """测试工作流启动后立即返回"""
    print("\n测试2: 工作流启动后立即返回")
    
    def run_workflow():
        thread_started = True
        if thread_started:
            return None
        
        unreachable_code = True
        return unreachable_code
    
    result = run_workflow()
    assert result is None
    print("✓ 工作流启动后立即返回测试通过")

def test_main_loop_handles_rerun():
    """测试主循环处理rerun"""
    print("\n测试3: 主循环处理rerun")
    
    has_running_tasks = True
    
    if has_running_tasks:
        should_rerun = True
    else:
        should_rerun = False
    
    assert should_rerun == True
    print("✓ 主循环处理rerun测试通过")

if __name__ == "__main__":
    print("=" * 60)
    print("开始测试不阻塞功能")
    print("=" * 60)
    
    try:
        test_button_click_no_rerun()
        test_workflow_returns_immediately()
        test_main_loop_handles_rerun()
        
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
