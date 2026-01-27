"""
Index Inspector 与索引相关 API 的测试：向量透视、图谱导出、添加/删除索引（入队）。
需要安装 celery 才能加载 app（与 conftest 一致）。
"""
from __future__ import annotations

import pytest
pytest.importorskip("celery")

from httpx import AsyncClient
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_inspector_vector_chunks_requires_novel_id(async_client: AsyncClient):
    """GET /inspector/vector/chunks 缺少 novel_id 时应为 422。"""
    r = await async_client.get("/inspector/vector/chunks")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_inspector_vector_chunks_list_mode(async_client: AsyncClient, db_session):
    """GET /inspector/vector/chunks 列表模式：有 novel_id 时返回数组。"""
    from src.api.models import Novel
    from datetime import datetime
    import uuid

    novel = Novel(
        id=str(uuid.uuid4()),
        title="InspectorTestNovel",
        genre=None,
        summary=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(novel)
    await db_session.commit()
    novel_id = novel.id

    r = await async_client.get("/inspector/vector/chunks", params={"novel_id": novel_id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    # 未建索引时可为空
    assert all("text" in x and "novel_name" in x for x in body) or len(body) == 0


@pytest.mark.asyncio
async def test_inspector_vector_chunks_search_mode(async_client: AsyncClient, db_session):
    """GET /inspector/vector/chunks 语义搜索模式：带 q 时返回数组。"""
    from src.api.models import Novel
    from datetime import datetime
    import uuid

    novel = Novel(
        id=str(uuid.uuid4()),
        title="InspectorSearchNovel",
        genre=None,
        summary=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(novel)
    await db_session.commit()

    r = await async_client.get(
        "/inspector/vector/chunks",
        params={"novel_id": novel.id, "q": "测试查询", "top_k": 5},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)


@pytest.mark.asyncio
async def test_inspector_graph_requires_novel_id(async_client: AsyncClient):
    """GET /inspector/graph 缺少 novel_id 时应为 422。"""
    r = await async_client.get("/inspector/graph")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_inspector_graph_returns_nodes_links(async_client: AsyncClient, db_session):
    """GET /inspector/graph 返回标准图结构 nodes/links。"""
    from src.api.models import Novel
    from datetime import datetime
    import uuid

    novel = Novel(
        id=str(uuid.uuid4()),
        title="InspectorGraphNovel",
        genre=None,
        summary=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(novel)
    await db_session.commit()

    r = await async_client.get("/inspector/graph", params={"novel_id": novel.id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "nodes" in body and "links" in body
    assert isinstance(body["nodes"], list)
    assert isinstance(body["links"], list)


@pytest.mark.asyncio
async def test_retrieval_add_index_queued(async_client: AsyncClient, db_session):
    """POST /retrieval/index 提交到 knowledge 队列，返回 success 与 queued。"""
    from src.api.models import Novel, Chapter, ChapterDraft, ChapterStatus
    from datetime import datetime
    import uuid

    novel = Novel(
        id=str(uuid.uuid4()),
        title="AddIndexTestNovel",
        genre=None,
        summary=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(novel)
    await db_session.flush()
    ch = Chapter(
        id=str(uuid.uuid4()),
        novel_id=novel.id,
        index=1,
        title="第一章",
        status=ChapterStatus.PENDING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(ch)
    await db_session.flush()
    draft = ChapterDraft(
        id=str(uuid.uuid4()),
        chapter_id=ch.id,
        content="第一章正文内容，用于索引测试。",
        summary="",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(draft)
    await db_session.commit()

    with patch("src.api.routers.retrieval._enqueue_add_index") as mock_enqueue:
        mock_enqueue.return_value = MagicMock(id="task-123")
        r = await async_client.post(
            "/retrieval/index",
            json={"novel_id": novel.id, "chapter_index": 1},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("success") is True
    assert data.get("queued") is True
    assert data.get("task_id") == "task-123"


@pytest.mark.asyncio
async def test_retrieval_delete_index_queued(async_client: AsyncClient, db_session):
    """DELETE /retrieval/index 提交到 knowledge 队列，返回 success 与 queued。"""
    from src.api.models import Novel
    from datetime import datetime
    import uuid

    novel = Novel(
        id=str(uuid.uuid4()),
        title="DeleteIndexTestNovel",
        genre=None,
        summary=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(novel)
    await db_session.commit()

    with patch("src.api.routers.retrieval._enqueue_delete_index") as mock_enqueue:
        mock_enqueue.return_value = MagicMock(id="task-456")
        r = await async_client.delete(
            "/retrieval/index",
            params={"novel_id": novel.id, "chapter_index": 1},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("success") is True
    assert data.get("queued") is True
