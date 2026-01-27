"""
GraphRAG 混合检索：向量 (ChromaDB) + 图谱 (GraphStore) 合并为上下文字符串。
供 Writer 等节点在生成时增强逻辑连贯性。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_graph_store_for_novel(novel_id: str, persist_root: Optional[str] = None) -> Optional[Any]:
    """按小说 id 返回其 GraphStore，无则返回 None。与 worker/inspector 共用 GRAPH_STORE_BASE。"""
    try:
        from src.rag.graph_store import NetworkXGraphStore
        from src.core.config import GRAPH_STORE_BASE
        root = persist_root if persist_root is not None else str(GRAPH_STORE_BASE)
        g = NetworkXGraphStore(persist_path=root, novel_id=novel_id)
        g.load()
        return g
    except Exception as e:
        logger.debug("get_graph_store_for_novel failed: %s", e)
        return None


def get_vector_retriever_for_novel(novel_id: str, novel_name: str):
    """返回该小说对应的 VectorRetriever（需已建索引），无则返回 None。"""
    try:
        from src.rag.retriever import VectorRetriever
        from src.rag.indexer import VectorIndexer
        import re
        project_root = Path(__file__).resolve().parents[2]
        safe = re.sub(r"[^a-zA-Z0.9._-]", "_", novel_name or novel_id or "default").strip("_") or "default"
        if len(safe) < 3:
            safe = f"novel_{hash(novel_id or novel_name) % 100000}"
        db_path = project_root / "data" / "chroma_db" / safe
        if not db_path.exists():
            return None
        indexer = VectorIndexer(db_path, collection_name=f"{safe}_chapters")
        return VectorRetriever(indexer.collection) if getattr(indexer, "collection", None) else None
    except Exception as e:
        logger.debug("get_vector_retriever_for_novel failed: %s", e)
        return None


def hybrid_retrieve(
    novel_id: str,
    novel_name: str,
    query: str,
    top_k: int = 5,
    graph_depth: int = 1,
    entity_hint: Optional[List[str]] = None,
) -> str:
    """
    向量检索 + 图谱 1-Hop 子图合并为一段上下文字符串。
    entity_hint: 若提供则直接用做图谱查询实体；否则从 query 前 200 字简单切词（或留空不查图）。
    """
    lines: List[str] = []
    # Vector
    retriever = get_vector_retriever_for_novel(novel_id, novel_name)
    if retriever and (query or "").strip():
        try:
            docs = retriever.retrieve((query or "").strip()[:500], top_k=top_k)
            if docs:
                lines.append("# 向量检索相关片段")
                for i, d in enumerate(docs, 1):
                    text = (d.get("text") or "").strip()
                    if text:
                        lines.append(f"## 片段{i}\n{text[:800]}")
        except Exception as e:
            logger.warning("hybrid_retrieve vector failed: %s", e)
    # Graph
    store = get_graph_store_for_novel(novel_id)
    entities = entity_hint or []
    if not entities and (query or "").strip():
        for w in (query or "")[:200].replace("，", " ").replace("。", " ").split():
            if len(w) >= 2 and w.strip():
                entities.append(w.strip())
    if store and entities:
        try:
            nodes, edges = store.get_subgraph(entities[:10], depth=graph_depth)
            if nodes or edges:
                lines.append("# 图谱关系 (1-Hop)")
                for e in edges[:20]:
                    s = e.get("source", "")
                    t = e.get("target", "")
                    r = e.get("relation", "")
                    if s and t:
                        lines.append(f"- {s} --[{r or '关系'}]--> {t}")
        except Exception as e:
            logger.warning("hybrid_retrieve graph failed: %s", e)
    return "\n\n".join(lines) if lines else ""
