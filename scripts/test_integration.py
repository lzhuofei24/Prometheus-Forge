#!/usr/bin/env python
"""
前后端联调测试脚本

测试关键 API 接口是否正常工作。
"""

import requests
import json
import time
from typing import Dict, Any

API_BASE_URL = "http://localhost:8000"


def test_health_check():
    """测试健康检查接口"""
    print("=" * 60)
    print("测试 1: 健康检查")
    print("=" * 60)
    
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=5)
        response.raise_for_status()
        data = response.json()
        print(f"✅ 健康检查通过: {data}")
        return True
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return False


def test_start_workflow():
    """测试启动工作流"""
    print("\n" + "=" * 60)
    print("测试 2: 启动工作流")
    print("=" * 60)
    
    try:
        payload = {
            "novel_name": "测试小说",
            "chapter_num": 1
        }
        response = requests.post(
            f"{API_BASE_URL}/workflow/start",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        print(f"✅ 工作流启动成功: {data}")
        workflow_id = data.get("workflow_id")
        return workflow_id
    except Exception as e:
        print(f"❌ 工作流启动失败: {e}")
        if hasattr(e, 'response'):
            print(f"   响应内容: {e.response.text}")
        return None


def test_get_workflow_state(workflow_id: str):
    """测试获取工作流状态"""
    print("\n" + "=" * 60)
    print("测试 3: 获取工作流状态")
    print("=" * 60)
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/workflow/{workflow_id}/state",
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        print(f"✅ 状态获取成功:")
        print(f"   工作流ID: {data.get('workflow_id')}")
        print(f"   小说名称: {data.get('novel_name')}")
        print(f"   章节号: {data.get('chapter_num')}")
        print(f"   状态: {data.get('status')}")
        return True
    except Exception as e:
        print(f"❌ 状态获取失败: {e}")
        return False


def test_get_workflow_trace(workflow_id: str):
    """测试获取工作流追踪"""
    print("\n" + "=" * 60)
    print("测试 4: 获取工作流追踪")
    print("=" * 60)
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/workflow/{workflow_id}/trace",
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        logs = data.get("logs", [])
        print(f"✅ 追踪获取成功: 共 {len(logs)} 条日志")
        for i, log in enumerate(logs[:3], 1):
            print(f"   日志 {i}: [{log.get('timestamp', '')[:19]}] {log.get('event_type')} ({log.get('source')})")
        if len(logs) > 3:
            print(f"   ... 还有 {len(logs) - 3} 条日志")
        return True
    except Exception as e:
        print(f"❌ 追踪获取失败: {e}")
        return False


def test_monitor_resources():
    """测试监控资源接口"""
    print("\n" + "=" * 60)
    print("测试 5: 监控资源")
    print("=" * 60)
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/monitor/resources",
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        stats = data.get("stats", {})
        queues = stats.get("queues", {})
        print(f"✅ 监控数据获取成功:")
        print(f"   文本队列: {queues.get('text_queue', 0)}")
        print(f"   媒体队列: {queues.get('media_queue', 0)}")
        print(f"   RAG队列: {queues.get('rag_queue', 0)}")
        return True
    except Exception as e:
        print(f"❌ 监控数据获取失败: {e}")
        if hasattr(e, 'response'):
            print(f"   响应内容: {e.response.text}")
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Prometheus Forge 前后端联调测试")
    print("=" * 60)
    print(f"\nAPI 地址: {API_BASE_URL}")
    print("请确保后端服务已启动: uvicorn src.api.main:app --reload --port 8000")
    print("\n")
    
    results = []
    
    results.append(("健康检查", test_health_check()))
    
    if not results[-1][1]:
        print("\n❌ 后端服务未启动，请先启动后端服务")
        return
    
    workflow_id = test_start_workflow()
    results.append(("启动工作流", workflow_id is not None))
    
    if workflow_id:
        time.sleep(0.5)
        results.append(("获取工作流状态", test_get_workflow_state(workflow_id)))
        results.append(("获取工作流追踪", test_get_workflow_trace(workflow_id)))
    
    results.append(("监控资源", test_monitor_resources()))
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status}: {name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    print(f"\n总计: {passed_count}/{total_count} 通过")


if __name__ == "__main__":
    main()
