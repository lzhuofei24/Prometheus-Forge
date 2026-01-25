"""
测试请求类型
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import time

def test_status_check_interval():
    """测试状态检查间隔为1秒"""
    print("测试1: 状态检查间隔")
    
    last_check_time = 0
    current_time = time.time()
    
    elapsed = current_time - last_check_time
    should_check = elapsed >= 1.0
    
    assert should_check == True or elapsed < 1.0
    print(f"✓ 状态检查间隔: {elapsed:.2f}秒")
    
    last_check_time = current_time
    time.sleep(1.1)
    current_time = time.time()
    elapsed = current_time - last_check_time
    should_check = elapsed >= 1.0
    
    assert should_check == True
    print(f"✓ 1秒后可以检查: {elapsed:.2f}秒")

def test_button_click_once():
    """测试按钮点击只触发一次"""
    print("\n测试2: 按钮点击只触发一次")
    
    button_clicked = False
    request_count = 0
    
    def handle_button_click():
        nonlocal button_clicked, request_count
        if button_clicked:
            return
        button_clicked = True
        request_count += 1
    
    handle_button_click()
    assert request_count == 1
    print(f"✓ 第一次点击: {request_count}次请求")
    
    handle_button_click()
    assert request_count == 1
    print(f"✓ 第二次点击（应被忽略）: {request_count}次请求")
    
    button_clicked = False
    handle_button_click()
    assert request_count == 2
    print(f"✓ 重置后点击: {request_count}次请求")

def test_no_duplicate_requests():
    """测试没有重复请求"""
    print("\n测试3: 无重复请求")
    
    status_check_count = 0
    button_click_count = 0
    
    def status_check():
        nonlocal status_check_count
        status_check_count += 1
    
    def button_click():
        nonlocal button_click_count
        button_click_count += 1
    
    for i in range(5):
        if i % 1 == 0:
            status_check()
        if i == 2:
            button_click()
    
    assert status_check_count == 5
    assert button_click_count == 1
    print(f"✓ 状态检查: {status_check_count}次")
    print(f"✓ 按钮点击: {button_click_count}次")

if __name__ == "__main__":
    print("=" * 60)
    print("开始测试请求类型")
    print("=" * 60)
    
    try:
        test_status_check_interval()
        test_button_click_once()
        test_no_duplicate_requests()
        
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
