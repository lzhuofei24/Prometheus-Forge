"""
GraphRAG 混合检索测试：图谱构建 (NetworkXGraphStore) 与混合检索 (hybrid_retrieve)。

- Test A: 三元组 upsert 后节点与边正确。
- Test B: Mock 向量 + 图存储，hybrid_retrieve 返回同时包含向量片段与图谱关系。
"""
from __future__ import annotations

import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.rag.graph_store import NetworkXGraphStore
from src.rag.hybrid import hybrid_retrieve


# ---------- Test Case A: 图谱构建 (Upsert) ----------


def test_graph_store_upsert_triplet_nodes_and_edges():
    """初始化 NetworkXGraphStore，upsert 三元组，断言存在节点与边。"""
    with tempfile.TemporaryDirectory() as td:
        store = NetworkXGraphStore(persist_path=td, novel_id="test_novel")
        store.upsert_triplet("萧炎", "师徒", "药老")
        store.upsert_triplet("萧炎", "拥有", "玄重尺")
        nodes, edges = store.get_all()
        node_ids = {n["id"] for n in nodes}
        edge_tuples = {(e["source"], e.get("relation", ""), e["target"]) for e in edges}
        assert "萧炎" in node_ids
        assert "药老" in node_ids
        assert "玄重尺" in node_ids
        assert ("萧炎", "师徒", "药老") in edge_tuples
        assert ("萧炎", "拥有", "玄重尺") in edge_tuples


def test_graph_store_get_subgraph():
    """upsert 后 get_subgraph(entities=["萧炎"], depth=1) 应返回萧炎及其 1-hop 邻居与边。"""
    with tempfile.TemporaryDirectory() as td:
        store = NetworkXGraphStore(persist_path=td, novel_id="test_novel")
        store.upsert_triplet("萧炎", "师徒", "药老")
        store.upsert_triplet("萧炎", "拥有", "玄重尺")
        nodes, edges = store.get_subgraph(["萧炎"], depth=1)
        node_ids = {n["id"] for n in nodes}
        assert "萧炎" in node_ids
        assert "药老" in node_ids
        assert "玄重尺" in node_ids
        rels = [(e["source"], e.get("relation", ""), e["target"]) for e in edges]
        assert ("萧炎", "师徒", "药老") in rels
        assert ("萧炎", "拥有", "玄重尺") in rels


# ---------- Test Case B: 混合检索 (Hybrid Retrieval) ----------


def test_hybrid_retrieve_combines_vector_and_graph():
    """Mock 向量检索返回「萧炎很生气」，Mock 图存储返回「萧炎 [师徒] 药老」，断言 hybrid_retrieve 结果同时包含两者。"""
    mock_vector_docs = [{"text": "萧炎很生气"}]
    mock_retriever = MagicMock()
    mock_retriever.retrieve = MagicMock(return_value=mock_vector_docs)

    mock_nodes = [{"id": "萧炎", "label": "萧炎"}, {"id": "药老", "label": "药老"}]
    mock_edges = [{"source": "萧炎", "target": "药老", "relation": "师徒"}]
    mock_store = MagicMock()
    mock_store.get_subgraph = MagicMock(return_value=(mock_nodes, mock_edges))

    with patch("src.rag.hybrid.get_vector_retriever_for_novel", return_value=mock_retriever), \
         patch("src.rag.hybrid.get_graph_store_for_novel", return_value=mock_store):
        out = hybrid_retrieve("n1", "测试小说", "萧炎怎么了", entity_hint=["萧炎"])

    assert "萧炎很生气" in out
    assert "萧炎" in out and "药老" in out and "师徒" in out
