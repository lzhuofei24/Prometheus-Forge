#!/usr/bin/env python
"""借助「Architect IN (Pending) = 1」场景测试监控接口：Redis 队列长度与 /monitor/resources 返回一致。"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import redis
except ImportError:
    redis = None

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
ARCHITECT_PENDING = "architect_pending"


def get_redis():
    from src.core.app_settings import get_settings
    s = get_settings()
    return redis.Redis(host=s.redis_host, port=s.redis_port, db=s.redis_db, decode_responses=True)


def redis_pending_count(r, queue_name: str) -> int:
    try:
        return int(r.llen(queue_name) or 0)
    except Exception:
        return -1


def seed_one_to_architect_pending():
    """往 architect_pending 放入 1 条裸 JSON（非 Celery 消息），仅用于测 llen。
    Worker 若消费到会报 KeyError('properties') 并崩溃。测完务必用 --cleanup 清掉，或先停 Architect 再 --seed。"""
    r = get_redis()
    r.lpush(ARCHITECT_PENDING, '{"test":"seed_for_monitor_api"}')
    return redis_pending_count(r, ARCHITECT_PENDING)


def fetch_monitor_resources(api_base: str, timeout: int = 10):
    import urllib.request
    api_base = api_base.rstrip("/")
    req = urllib.request.Request(
        f"{api_base}/monitor/resources",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main():
    ap = argparse.ArgumentParser(
        description="测试监控接口：Architect IN (Pending) 与 /monitor/resources 是否一致"
    )
    ap.add_argument(
        "--seed",
        action="store_true",
        help="先往 architect_pending 塞入 1 条，再请求接口核对（测完可配合 --cleanup 删除）",
    )
    ap.add_argument(
        "--cleanup",
        action="store_true",
        help="从 architect_pending 弹出一条后退出（与 --seed 配合使用）",
    )
    ap.add_argument(
        "--drain",
        action="store_true",
        help="清空 architect_pending 整条队列（出现 KeyError('properties') 后可用此恢复）",
    )
    ap.add_argument("--api-base", default=API_BASE, help="Backend 地址，默认 http://127.0.0.1:8000")
    ap.add_argument("--timeout", type=int, default=10, help="请求 /monitor/resources 超时秒数")
    args = ap.parse_args()

    if not redis:
        print("❌ 需要安装 redis 包")
        sys.exit(1)

    api_base = args.api_base.rstrip("/")

    if args.cleanup or args.drain:
        r = get_redis()
        try:
            r.ping()
        except Exception as e:
            print(f"❌ Redis 连接失败: {e}")
            sys.exit(1)
        if args.drain:
            n = r.llen(ARCHITECT_PENDING)
            for _ in range(int(n) or 0):
                r.lpop(ARCHITECT_PENDING)
            print(f"   已清空 {ARCHITECT_PENDING}，共移除 {n} 条。")
        else:
            n = r.lpop(ARCHITECT_PENDING)
            print(f"   architect_pending 弹出一条: {n is not None}")
        return

    print("=" * 60)
    print("监控接口测试：Architect IN (Pending)")
    print("=" * 60)

    # 1) Redis 实际长度
    try:
        r = get_redis()
        r.ping()
    except Exception as e:
        print(f"❌ Redis 连接失败: {e}")
        sys.exit(1)

    redis_count = redis_pending_count(r, ARCHITECT_PENDING)
    print(f"\n1. Redis 中 {ARCHITECT_PENDING} 长度: {redis_count}")

    if args.seed:
        print("   [--seed] 注入 1 条...")
        right_after = seed_one_to_architect_pending()
        redis_count = redis_pending_count(r, ARCHITECT_PENDING)
        print(f"   注入后 Redis 长度: {redis_count} (lpush 后瞬时: {right_after})")
        if right_after == 1 and redis_count == 0:
            print("   （Architect Worker 若在运行，会立即消费该条，故当前长度变为 0，属正常；接口与 Redis 一致即通过）")

    # 2) /monitor/resources 中的 queues.architect_pending
    print(f"\n2. 请求 GET {api_base}/monitor/resources")
    try:
        data = fetch_monitor_resources(api_base, timeout=args.timeout)
    except Exception as e:
        print(f"   ❌ 请求失败: {e}")
        print("   请确认 Backend 已启动（如通过 start_all_tabs.bat）。")
        sys.exit(1)

    stats = data.get("stats") or {}
    queues = stats.get("queues") or {}
    api_count = queues.get(ARCHITECT_PENDING)
    if api_count is None:
        api_count = -1
    else:
        api_count = int(api_count)
    print(f"   返回 stats.queues['{ARCHITECT_PENDING}'] = {api_count}")

    # 3) 结论
    print("\n" + "=" * 60)
    if redis_count == api_count:
        print("✅ 通过：Redis 长度与接口返回值一致")
        if args.seed:
            print("   ⚠ --seed 写入的是非 Celery 消息，若被 Worker 消费会触发 KeyError('properties')。")
            print("   测完请执行: python scripts/test_monitor_pending.py --drain 清空队列。")
    else:
        print("❌ 不一致：Redis 长度 = %s，接口返回 = %s" % (redis_count, api_count))
        print("   请检查 monitor 是否使用 Redis Pipeline 读取同一 Redis。")
    print("=" * 60)


if __name__ == "__main__":
    main()
