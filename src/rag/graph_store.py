"""
图存储接口与 NetworkX 实现，用于 GraphRAG「向量+图谱」混合检索。

BaseGraphStore 定义三元组 upsert、子图查询与持久化契约；
NetworkXGraphStore 基于 NetworkX + JSON 文件持久化，预留 Neo4j 等扩展槽位。
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 可选依赖：无 networkx 时仅暴露接口，运行时报错由调用方处理
try:
    import networkx as nx
    _HAS_NX = True
except ImportError:
    nx = None  # type: ignore
    _HAS_NX = False


def _ensure_nx() -> None:
    if not _HAS_NX:
        raise RuntimeError("graph_store 需要 networkx，请安装: pip install networkx")

# 边属性键：时空与上下文（何时、何地、为何），与 Knowledge 抽取、前端展示一致
_EDGE_PROP_KEYS = ("chapter", "location", "state", "quote", "context")


class BaseGraphStore(ABC):
    """图存储抽象：三元组 (subject, relation, object) 的写入与子图查询。"""

    @abstractmethod
    def upsert_triplet(self, subj: str, rel: str, obj: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """插入或更新一条三元组。重复 (subj, rel, obj) 可覆盖或忽略，由实现决定。"""
        pass

    @abstractmethod
    def get_subgraph(
        self,
        entities: List[str],
        depth: int = 1,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        以给定实体为起点，取 depth 跳内的子图。
        Returns:
            (nodes, edges)，nodes 为 [{"id": str, "label": str?, ...}]，edges 为 [{"source": str, "target": str, "relation": str?, ...}]
        """
        pass

    @abstractmethod
    def save(self, path: Optional[str] = None) -> None:
        """持久化到路径（由实现约定默认路径）。"""
        pass

    @abstractmethod
    def load(self, path: Optional[str] = None) -> None:
        """从路径加载（由实现约定默认路径）。"""
        pass


class NetworkXGraphStore(BaseGraphStore):
    """
    基于 NetworkX 的图存储，使用 JSON 文件持久化。
    图结构：有向多图，边属性 "relation" 表示关系类型；节点以字符串 id 存储，可带 label 等属性。
    """

    def __init__(self, persist_path: Optional[str] = None, novel_id: Optional[str] = None):
        _ensure_nx()
        self._g: "nx.MultiDiGraph" = nx.MultiDiGraph()
        self._novel_id = novel_id or "default"
        self._base = Path(persist_path or "data/graph_store")
        self._base.mkdir(parents=True, exist_ok=True)
        self._path = self._base / f"{self._novel_id}.json"

    def _node_key(self, entity: str) -> str:
        return str(entity).strip() or "_"

    def upsert_triplet(self, subj: str, rel: str, obj: str, meta: Optional[Dict[str, Any]] = None) -> None:
        _ensure_nx()
        s, o = self._node_key(subj), self._node_key(obj)
        m = meta or {}
        sm, om, em = m.get("subj_meta") or {}, m.get("obj_meta") or {}, m.get("edge_meta") or {}
        if not self._g.has_node(s):
            self._g.add_node(s, label=s, **sm)
        else:
            self._g.nodes[s].update({k: v for k, v in sm.items() if v is not None and v != ""})
        if not self._g.has_node(o):
            self._g.add_node(o, label=o, **om)
        else:
            self._g.nodes[o].update({k: v for k, v in om.items() if v is not None and v != ""})
        edge_data = {"relation": rel, **{k: em.get(k) for k in _EDGE_PROP_KEYS if em.get(k) is not None}}
        self._g.add_edge(s, o, **edge_data)

    def get_all(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """返回整图的 nodes 与 edges，供前端图谱展示。"""
        _ensure_nx()
        nodes = [
            {
                "id": n,
                "label": self._g.nodes[n].get("label", n),
                "type": self._g.nodes[n].get("type"),
                "status": self._g.nodes[n].get("status"),
                "description": self._g.nodes[n].get("description"),
            }
            for n in self._g.nodes()
        ]
        edges = []
        for u, v, d in self._g.edges(data=True):
            e = {"source": u, "target": v, "relation": d.get("relation", "")}
            props = {k: d.get(k) for k in _EDGE_PROP_KEYS if d.get(k) is not None}
            if props:
                e["properties"] = props
            edges.append(e)
        return nodes, edges

    def get_subgraph(
        self,
        entities: List[str],
        depth: int = 1,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        _ensure_nx()
        if not entities or self._g.order() == 0:
            return [], []

        node_ids = set()
        for e in entities:
            k = self._node_key(e)
            if self._g.has_node(k):
                node_ids.add(k)
            for u, v in nx.bfs_edges(self._g, k, depth_limit=depth):
                node_ids.add(u)
                node_ids.add(v)

        sub = self._g.subgraph(node_ids)
        nodes = [
            {
                "id": n,
                "label": sub.nodes[n].get("label", n),
                "type": sub.nodes[n].get("type"),
                "status": sub.nodes[n].get("status"),
                "description": sub.nodes[n].get("description"),
            }
            for n in sub.nodes()
        ]
        edges = []
        for u, v, d in sub.edges(data=True):
            e = {"source": u, "target": v, "relation": d.get("relation", "")}
            props = {k: d.get(k) for k in _EDGE_PROP_KEYS if d.get(k) is not None}
            if props:
                e["properties"] = props
            edges.append(e)
        return nodes, edges

    def save(self, path: Optional[str] = None) -> None:
        _ensure_nx()
        p = Path(path) if path else self._path
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": [{"id": n, **dict(self._g.nodes[n])} for n in self._g.nodes()],
            "edges": [
                {"source": u, "target": v, **dict(d)}
                for u, v, d in self._g.edges(data=True)
            ],
        }
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, path: Optional[str] = None) -> None:
        _ensure_nx()
        p = Path(path) if path else self._path
        if not p.exists():
            self._g.clear()
            return
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        self._g.clear()
        for n in data.get("nodes", []):
            nid = n.pop("id", None)
            if nid is not None:
                self._g.add_node(nid, **n)
        for e in data.get("edges", []):
            u, v = e.get("source"), e.get("target")
            if u is None or v is None:
                continue
            rest = {k: v for k, v in e.items() if k not in ("source", "target")}
            self._g.add_edge(u, v, relation=rest.get("relation", ""), **{k: rest[k] for k in rest if k != "relation" and rest[k] is not None})
