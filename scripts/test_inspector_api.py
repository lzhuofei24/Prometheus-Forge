#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Index Inspector 接口的独立测试脚本：向量透视、图谱导出。
在本地 API 已启动（默认 http://localhost:8000）时运行，无需 pytest/celery。
用法: python scripts/test_inspector_api.py [--base-url http://localhost:8000]

说明：
- 向量透视/图谱导出与 RAG 索引使用统一目录 data/chroma_db/<小说标题>/（见 src.core.config.CHROMA_BASE）。
- 若返回 0 条：该小说尚未做过“添加索引”（POST /retrieval/index），或 Knowledge worker 未执行完任务。
- 图谱 nodes/links 为 0 属正常，除非另有流程向知识图谱（graph_store）写入三元组。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    import requests
except ImportError:
    print("请安装 requests: pip install requests")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000", help="API 根地址")
    ap.add_argument("--novel-id", default=None, help="指定要测试的 novel_id，不传则用列表第一本")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    ok = 0
    fail = 0

    # 1) 获取小说列表与要用的 novel_id
    try:
        r = requests.get(f"{base}/novels", timeout=5)
    except requests.RequestException as e:
        print(f"请求失败（请确认 API 已启动）: {e}")
        sys.exit(2)
    if r.status_code != 200:
        print(f"FAIL 获取小说列表: {r.status_code} {r.text[:200]}")
        fail += 1
        return fail
    novels = r.json()
    if args.novel_id:
        novel_id = args.novel_id
        title = next((n.get("title") for n in novels if n.get("id") == novel_id), None)
        if not title and novels:
            print(f"提示: --novel-id {novel_id} 不在当前列表，仍将用该 id 请求（可能 404）")
    else:
        novel_id = novels[0]["id"] if novels else None
        title = novels[0].get("title") if novels else None
    if not novel_id:
        print("SKIP 无小说，跳过需要 novel_id 的用例")
        return 0
    print(f"使用 novel_id={novel_id} title={title!r}")

    # 2) 向量透视 - 列表模式
    r = requests.get(f"{base}/inspector/vector/chunks", params={"novel_id": novel_id}, timeout=15)
    if r.status_code != 200:
        print(f"FAIL 向量透视(列表) novel_id={novel_id}: {r.status_code} {r.text[:200]}")
        fail += 1
    else:
        body = r.json()
        assert isinstance(body, list), "应返回数组"
        print(f"OK  向量透视(列表) novel_id={novel_id} 返回 {len(body)} 条")
        ok += 1

    # 3) 向量透视 - 语义搜索
    r = requests.get(
        f"{base}/inspector/vector/chunks",
        params={"novel_id": novel_id, "q": "测试", "top_k": 5},
        timeout=15,
    )
    if r.status_code != 200:
        print(f"FAIL 向量透视(搜索) novel_id={novel_id}: {r.status_code} {r.text[:200]}")
        fail += 1
    else:
        body = r.json()
        assert isinstance(body, list), "应返回数组"
        print(f"OK  向量透视(搜索) novel_id={novel_id} 返回 {len(body)} 条")
        ok += 1

    # 4) 图谱导出
    r = requests.get(f"{base}/inspector/graph", params={"novel_id": novel_id}, timeout=10)
    if r.status_code != 200:
        print(f"FAIL 图谱导出 novel_id={novel_id}: {r.status_code} {r.text[:200]}")
        fail += 1
    else:
        body = r.json()
        assert "nodes" in body and "links" in body, "应包含 nodes/links"
        print(f"OK  图谱导出 novel_id={novel_id} nodes={len(body['nodes'])} links={len(body['links'])}")
        ok += 1

    # 5) 缺少 novel_id 时应 422
    r = requests.get(f"{base}/inspector/vector/chunks", timeout=5)
    if r.status_code != 422:
        print(f"FAIL 向量透视缺 novel_id 期望 422 实际 {r.status_code}")
        fail += 1
    else:
        print("OK  向量透视缺 novel_id 返回 422")
        ok += 1

    r = requests.get(f"{base}/inspector/graph", timeout=5)
    if r.status_code != 422:
        print(f"FAIL 图谱导出缺 novel_id 期望 422 实际 {r.status_code}")
        fail += 1
    else:
        print("OK  图谱导出缺 novel_id 返回 422")
        ok += 1

    print()
    if fail:
        print(f"总计: {ok} 通过, {fail} 失败")
        sys.exit(1)
    print(f"总计: {ok} 通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
