"""
RAG 索引可视化调试 API：向量切片分页/语义搜索、图谱导出。
只读接口，供 Index Inspector 前端使用。
路径与 collection 名与 index_ops 完全一致，故直接复用其解析函数。
"""
import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.services.novel_service import NovelService
from src.core.database import get_db
from src.rag import index_ops

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inspector", tags=["inspector"])


def _get_collection(novel_name: str):
    """返回该小说对应的 Chroma 集合，与 index_ops 使用同一 path/collection 解析。"""
    from src.rag.indexer import VectorIndexer
    chroma_path, cn = index_ops.get_chroma_path_and_collection_name(novel_name)
    chroma_path.mkdir(parents=True, exist_ok=True)
    indexer = VectorIndexer(chroma_path, collection_name=cn)
    return indexer.collection


def _run_semantic_search(novel_name: str, query: str, top_k: int) -> List[Dict[str, Any]]:
    """同步：语义搜索，返回 Top-K 及 distance。"""
    from src.rag.retriever import VectorRetriever
    if not query or not query.strip():
        return []
    try:
        coll = _get_collection(novel_name)
        retriever = VectorRetriever(coll)
        items = retriever.retrieve(query, top_k=top_k)
        return [
            {
                "text": it["text"],
                "metadata": it.get("metadata") or {},
                "distance": it.get("distance", 0.0),
                "novel_name": novel_name,
            }
        for it in items]
    except Exception as e:
        logger.warning("inspector semantic search %s: %s", novel_name, e)
        return []


def _run_list_chunks(novel_name: str, limit: int, offset: int) -> List[Dict[str, Any]]:
    """同步：按 (chapter_num, chunk_index) 排序后分页返回向量切片。Chroma 无 offset，取整表后切片。"""
    try:
        coll = _get_collection(novel_name)
        data = coll.get(include=["documents", "metadatas"], limit=5000)
        ids = data.get("ids") or []
        docs = data.get("documents") or []
        metadatas = data.get("metadatas") or [{}] * len(ids)
        rows = []
        for i, doc_id in enumerate(ids):
            meta = metadatas[i] if i < len(metadatas) else {}
            ch = meta.get("chapter_num")
            if ch is not None:
                try:
                    ch = int(ch)
                except (TypeError, ValueError):
                    ch = 0
            else:
                ch = 0
            idx = int(meta.get("chunk_index", 0)) if meta.get("chunk_index") is not None else 0
            text = docs[i] if i < len(docs) else ""
            rows.append((ch, idx, text, meta, doc_id))
        rows.sort(key=lambda x: (x[0], x[1]))
        page = rows[offset : offset + limit]
        return [
            {
                "text": r[2],
                "metadata": r[3],
                "distance": None,
                "novel_name": novel_name,
                "id": r[4],
            }
        for r in page]
    except Exception as e:
        logger.warning("inspector list chunks %s: %s", novel_name, e)
        return []


class VectorChunkItem(BaseModel):
    text: str
    metadata: Optional[Dict[str, Any]] = None
    distance: Optional[float] = None
    novel_name: str
    id: Optional[str] = None


@router.get("/vector/chunks", response_model=List[VectorChunkItem])
async def get_vector_chunks(
    novel_id: str = Query(..., description="小说 id，用于限定集合"),
    q: Optional[str] = Query(None, description="有则语义搜索 Top-K，无则按顺序分页列表"),
    top_k: int = Query(20, ge=1, le=100, description="语义搜索时返回数量"),
    limit: int = Query(50, ge=1, le=200, description="列表模式每页条数"),
    offset: int = Query(0, ge=0, description="列表模式偏移"),
    db: AsyncSession = Depends(get_db),
):
    """向量透视：语义搜索返回 Top-K+Distance，无 q 时按 chapter_num/chunk_index 分页列表。"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    novel_name = novel.title
    if q and q.strip():
        raw = await asyncio.to_thread(_run_semantic_search, novel_name, q.strip(), top_k)
    else:
        raw = await asyncio.to_thread(_run_list_chunks, novel_name, limit, offset)
    out = []
    for it in raw:
        meta = it.get("metadata") or {}
        ch = meta.get("chapter_num")
        if ch is not None and not isinstance(ch, int):
            try:
                ch = int(ch)
            except (TypeError, ValueError):
                ch = None
        out.append(
            VectorChunkItem(
                text=it.get("text", ""),
                metadata=meta if isinstance(meta, dict) else None,
                distance=it.get("distance"),
                novel_name=it.get("novel_name", novel_name),
                id=it.get("id"),
            )
        )
    return out


class GraphNode(BaseModel):
    id: str
    label: Optional[str] = None
    type: Optional[str] = None  # Person/Location/Item/Concept/Organization/Event，前端着色
    status: Optional[str] = None  # Alive|Dead、入门阶段|精通 等
    description: Optional[str] = None  # 简短画像


class EdgeProperties(BaseModel):
    """边的时空与上下文属性：何时、何地、何种状态、佐证。"""
    chapter: Optional[int] = None
    location: Optional[str] = None
    state: Optional[str] = None
    quote: Optional[str] = None
    context: Optional[str] = None


class GraphLink(BaseModel):
    source: str
    target: str
    relation: Optional[str] = None
    properties: Optional[EdgeProperties] = None  # 时空与上下文，有则填


class GraphExport(BaseModel):
    nodes: List[GraphNode]
    links: List[GraphLink]


@router.get("/graph", response_model=GraphExport)
async def get_graph_export(
    novel_id: str = Query(..., description="小说 id"),
    db: AsyncSession = Depends(get_db),
):
    """图谱导出：返回该小说知识图谱的 nodes + links，供力导向图渲染。"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        from src.rag.graph_store import NetworkXGraphStore
        from src.core.config import GRAPH_STORE_BASE
        store = NetworkXGraphStore(persist_path=str(GRAPH_STORE_BASE), novel_id=novel_id)
        store.load()
        nodes, edges = store.get_all()
        def _node(n: dict):
            return GraphNode(
                id=n["id"],
                label=n.get("label") or n["id"],
                type=n.get("type"),
                status=n.get("status"),
                description=n.get("description"),
            )

        def _link(e: dict):
            props = e.get("properties")
            if isinstance(props, dict) and props:
                allowed = {"chapter", "location", "state", "quote", "context"}
                kwargs = {k: props[k] for k in allowed if k in props and props[k] is not None}
                properties = EdgeProperties(**kwargs) if kwargs else None
            else:
                properties = None
            return GraphLink(
                source=e["source"],
                target=e["target"],
                relation=e.get("relation") or "",
                properties=properties,
            )

        return GraphExport(nodes=[_node(n) for n in nodes], links=[_link(e) for e in edges])
    except Exception as e:
        logger.warning("inspector graph export failed: %s", e)
        return GraphExport(nodes=[], links=[])
