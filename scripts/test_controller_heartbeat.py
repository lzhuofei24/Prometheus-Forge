#!/usr/bin/env python
"""测试 Controller Worker 是否已启动：检查 Redis 心跳与监控 API 的 controller.online"""
import sys
import os
import time
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis

HEARTBEAT_KEY = "system:controller:heartbeat"
HEARTBEAT_TTL = 30
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")


def get_redis():
    return redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)


def test_redis_heartbeat():
    """检查 Redis 中是否存在 Controller 心跳"""
    try:
        r = get_redis()
        r.ping()
    except Exception as e:
        print(f"❌ Redis 连接失败: {e}")
        return False, None
    ok = bool(r.exists(HEARTBEAT_KEY))
    val = r.get(HEARTBEAT_KEY) if ok else None
    return ok, val


def write_heartbeat():
    """写入一次心跳（用于验证「有心跳时 API 是否显示在线」）"""
    try:
        r = get_redis()
        r.ping()
        r.setex(HEARTBEAT_KEY, HEARTBEAT_TTL, str(time.time()))
        print(f"   已写入 {HEARTBEAT_KEY} (TTL={HEARTBEAT_TTL}s)")
        return True
    except Exception as e:
        print(f"❌ 写入心跳失败: {e}")
        return False


def test_monitor_api(api_base=None, timeout=8):
    """请求 /monitor/resources 并检查 stats.controller.online"""
    api_base = api_base or API_BASE
    try:
        import urllib.request
        import json
        req = urllib.request.Request(
            f"{api_base}/monitor/resources",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        return None
    stats = data.get("stats") or {}
    ctrl = stats.get("controller") or {}
    return ctrl.get("online")


def main():
    ap = argparse.ArgumentParser(description="测试 Controller Worker 是否已启动（Redis 心跳 + 监控 API）")
    ap.add_argument("--write-heartbeat", action="store_true", help="仅写入一次心跳，用于验证 API 是否会显示在线")
    ap.add_argument("--api-base", default=None, help="监控 API 根地址，默认 http://127.0.0.1:8000")
    args = ap.parse_args()
    api_base = (args.api_base or API_BASE).rstrip("/")

    print("=" * 60)
    print("Controller Worker 系统已启动？")
    print("=" * 60)

    if args.write_heartbeat:
        print("\n[--write-heartbeat] 写入心跳键...")
        if write_heartbeat():
            print("请再执行本脚本（不加 --write-heartbeat）或在浏览器打开 Central Controller Dashboard 查看是否显示在线。")
        return

    # 1. Redis 心跳
    print("\n1. Redis 心跳键:", HEARTBEAT_KEY)
    ok, val = test_redis_heartbeat()
    if ok:
        print(f"   ✅ 存在, value={val}")
    else:
        print("   ❌ 不存在（Controller run_loop 未在写心跳或未启动）")

    # 2. 监控 API
    print(f"\n2. 监控 API: GET {api_base}/monitor/resources")
    api_online = test_monitor_api(api_base=api_base)
    if api_online is True:
        print("   ✅ stats.controller.online == true")
    elif api_online is False:
        print("   ❌ stats.controller.online == false")
    else:
        print("   ⚠️ 未取到 controller.online 或请求失败（Backend 未起或超时）")

    # 3. 结论
    print("\n" + "=" * 60)
    if ok and api_online is True:
        print("结论: Controller Worker 系统已启动 ✅")
    elif ok and api_online is not True:
        print("结论: Redis 有心跳但 API 未返回在线 → 请重启 Backend，并确认 monitor 使用 heartbeat 判定。")
    elif not ok and api_online is True:
        print("结论: API 显示在线但 Redis 无心跳 → 可能用了旧逻辑或缓存。")
    else:
        print("结论: Controller Worker 未检测到在线。")
        print("  - 请先运行 start_all_workers.bat 或单独启动 Controller Worker。")
        print("  - 确认 Controller 进程已加载带心跳的 run_loop（重启 Controller 窗口生效）。")
        print("  - 若需仅验证「API 是否按心跳显示在线」，可先执行: python scripts/test_controller_heartbeat.py --write-heartbeat")
    print("=" * 60)


if __name__ == "__main__":
    main()
