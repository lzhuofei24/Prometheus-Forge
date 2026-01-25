#!/usr/bin/env python
"""清除当前存在的数据流：Redis 工作流状态、队列、统计与 Celery 结果。不触碰 SQLite/Chroma 等业务库。

用法（在项目根目录执行）:
  python scripts/clear_data_flow.py

依赖：Redis 运行在 localhost:6379，与 celery_config / StateManager 一致。
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# 与 celery_config、controller 一致
REDIS_HOST = "localhost"
REDIS_PORT = 6379
BROKER_DB = 0
BACKEND_DB = 1

AGENTS = ["architect", "writer", "critic", "media", "knowledge", "censor"]
QUEUE_KEYS = [f"{a}_pending" for a in AGENTS] + [f"{a}_completed" for a in AGENTS] + ["controller_pending"]


def main():
    import redis

    print("=" * 60)
    print("清除数据流（仅 Redis 状态 / 队列 / Celery 结果）")
    print("=" * 60)

    # 1. Redis db=0：工作流、锁、统计、队列
    print("\n1. Redis (db=0) - 工作流状态、锁、统计、队列")
    print("-" * 60)
    try:
        r0 = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=BROKER_DB, decode_responses=True)
        deleted = 0

        for pattern in ["workflow:*", "workflow:lock:*", "stats:*", "token_stats:*"]:
            keys = list(r0.scan_iter(match=pattern))
            if keys:
                r0.delete(*keys)
                deleted += len(keys)
                print(f"  删除 {pattern}: {len(keys)} 个键")

        for q in QUEUE_KEYS:
            if r0.exists(q):
                n = r0.llen(q) if r0.type(q) == "list" else 1
                r0.delete(q)
                deleted += 1
                print(f"  删除队列 {q}: {n} 条消息")

        print(f"\n  db=0 共删除/清空 {deleted} 个键")
        print(f"  剩余键数: {len(r0.keys('*'))}")
    except Exception as e:
        print(f"  清理失败: {e}")

    # 2. Redis db=1：Celery 任务结果
    print("\n2. Redis (db=1) - Celery 任务结果")
    print("-" * 60)
    try:
        r1 = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=BACKEND_DB, decode_responses=True)
        keys = list(r1.scan_iter(match="celery-task-meta-*"))
        if keys:
            r1.delete(*keys)
            print(f"  删除 celery-task-meta-*: {len(keys)} 个")
        else:
            print("  无 Celery 结果键")
        print(f"  剩余键数: {len(r1.keys('*'))}")
    except Exception as e:
        print(f"  清理失败: {e}")

    print("\n" + "=" * 60)
    print("数据流清除完成（未动 SQLite / Chroma）")
    print("=" * 60)


if __name__ == "__main__":
    main()
