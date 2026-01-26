"""
检索与索引 API：向量检索、列出已索引章节、添加/删除索引。
复用 RAG（ChromaDB）与 Knowledge 的索引逻辑，仅支持手动调用，不进入工作流。
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.services.novel_service import NovelService
from src.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retrieval", tags=["retrieval"])

_project_root = Path(__file__).resolve().parent.parent.parent.parent
_chroma_base = _project_root / "data" / "chroma_db"


def _safe_collection_name(novel_name: str) -> str:
    """与 KnowledgeHandler._update_rag 保持一致"""
    s = re.sub(r"[^a-zA-Z0-9._-]", "_", novel_name).strip("_")
    if not s or len(s) < 3:
        s = f"novel_{abs(hash(novel_name)) % 100000}"
    if not re.match(r"^[a-zA-Z0-9]", s):
        s = f"n_{s}"
    if not re.match(r"[a-zA-Z0-9]$", s):
        s = f"{s}x"
    name = f"{s}_chapters"
    return name if len(name) >= 3 else f"novel_{abs(hash(novel_name)) % 100000}_chapters"


def _get_indexer_and_collection(novel_name: str):
    """返回 (VectorIndexer, collection) 用于该小说，调用方在同步线程中使用。"""
    from src.rag.indexer import VectorIndexer
    chroma_path = _chroma_base / novel_name
    chroma_path.mkdir(parents=True, exist_ok=True)
    cn = _safe_collection_name(novel_name)
    indexer = VectorIndexer(chroma_path, collection_name=cn)
    return indexer, indexer.collection


def _list_indexed_novel_dirs() -> List[str]:
    """返回已存在 Chroma 目录的小说名（目录名即 novel_name/title）。"""
    if not _chroma_base.exists():
        return []
    return [d.name for d in _chroma_base.iterdir() if d.is_dir()]


def _indexed_chapters_for_novel(novel_name: str) -> List[int]:
    """返回该小说下已索引的 chapter_num 列表。"""
    try:
        _, coll = _get_indexer_and_collection(novel_name)
        data = coll.get(include=["metadatas"])
        if not data or not data.get("metadatas"):
            return []
        seen = set()
        for meta in data["metadatas"]:
            if meta and "chapter_num" in meta:
                seen.add(int(meta["chapter_num"]))
        return sorted(seen)
    except Exception as e:
        logger.warning("_indexed_chapters_for_novel %s: %s", novel_name, e)
        return []


def _run_index_chapter(novel_name: str, chapter_num: int, content: str) -> None:
    """同步执行：将一章内容写入 RAG（仅索引，无实体抽取/摘要）。"""
    from src.rag.indexer import VectorIndexer
    indexer, _ = _get_indexer_and_collection(novel_name)
    metadata = {"novel_name": novel_name, "chapter_num": chapter_num}
    indexer.index_text(content, metadata=metadata, batch_size=64)


def _run_delete_index(novel_name: str, chapter_num: Optional[int]) -> None:
    """同步执行：删除该小说下某章的索引，或整本小说的索引。"""
    _, coll = _get_indexer_and_collection(novel_name)
    if chapter_num is not None:
        # Chroma where: chapter_num 可能存为 int
        ids_to_del = []
        data = coll.get(include=["metadatas"])
        if data and data.get("ids") and data.get("metadatas"):
            for i, meta in enumerate(data["metadatas"]):
                if meta and meta.get("novel_name") == novel_name and meta.get("chapter_num") == chapter_num:
                    ids_to_del.append(data["ids"][i])
        if ids_to_del:
            coll.delete(ids=ids_to_del)
    else:
        data = coll.get(include=[])
        if data and data.get("ids"):
            coll.delete(ids=data["ids"])


def _run_search(query: str, novel_name: Optional[str], top_k: int) -> List[dict]:
    """同步执行：向量检索。novel_name 为 None 时扫所有已知小说并合并结果。"""
    from src.rag.retriever import VectorRetriever
    if not query or not query.strip():
        return []
    results = []
    if novel_name:
        try:
            _, coll = _get_indexer_and_collection(novel_name)
            retriever = VectorRetriever(coll)
            for item in retriever.retrieve(query, top_k=top_k):
                item["novel_name"] = novel_name
                results.append(item)
        except Exception as e:
            logger.warning("search in novel %s: %s", novel_name, e)
    else:
        for name in _list_indexed_novel_dirs():
            try:
                _, coll = _get_indexer_and_collection(name)
                retriever = VectorRetriever(coll)
                for item in retriever.retrieve(query, top_k=min(top_k, 20)):
                    item["novel_name"] = name
                    results.append(item)
            except Exception as e:
                logger.debug("search in novel %s: %s", name, e)
        # 按 distance 排序后取前 top_k
        results.sort(key=lambda x: x.get("distance", 1e9))
        results = results[:top_k]
    return results


class SearchResponseItem(BaseModel):
    text: str
    novel_name: str
    chapter_num: Optional[int] = None
    distance: float
    metadata: Optional[dict] = None


class IndexedNovel(BaseModel):
    novel_id: str
    novel_title: str
    chapters: List[int]


class AddIndexBody(BaseModel):
    novel_id: str
    chapter_index: int


@router.get("/search", response_model=List[SearchResponseItem])
async def search(
    q: str = Query(..., min_length=1),
    novel_id: Optional[str] = Query(None, description="限定在该小说内检索，不传则全库"),
    top_k: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """向量检索：按 query 在已索引内容中检索相似片段。"""
    novel_name = None
    if novel_id:
        novel = await NovelService.get_novel_by_id(db, novel_id)
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        novel_name = novel.title
    raw = await asyncio.to_thread(_run_search, q, novel_name, top_k)
    out = []
    for item in raw:
        meta = item.get("metadata") or {}
        ch = meta.get("chapter_num") if isinstance(meta, dict) else None
        if ch is not None:
            try:
                ch = int(ch)
            except (TypeError, ValueError):
                ch = None
        out.append(
            SearchResponseItem(
                text=item.get("text", ""),
                novel_name=item.get("novel_name", ""),
                chapter_num=ch,
                distance=float(item.get("distance", 0)),
                metadata=meta if isinstance(meta, dict) else None,
            )
        )
    return out


@router.get("/indexed", response_model=List[IndexedNovel])
async def list_indexed(db: AsyncSession = Depends(get_db)):
    """列出所有已建索引的小说及其已索引章节号。"""
    dirs = await asyncio.to_thread(_list_indexed_novel_dirs)
    out = []
    for title in dirs:
        chapters = await asyncio.to_thread(_indexed_chapters_for_novel, title)
        novel = await NovelService.get_novel_by_title(db, title)
        novel_id = novel.id if novel else ""
        out.append(IndexedNovel(novel_id=novel_id, novel_title=title, chapters=chapters))
    return out


@router.post("/index", response_model=dict)
async def add_index(
    body: AddIndexBody,
    db: AsyncSession = Depends(get_db),
):
    """为指定小说的指定章节建立索引（仅写入 RAG，无实体/摘要）。"""
    novel = await NovelService.get_novel_by_id(db, body.novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    chapter = await NovelService.get_chapter_by_novel_and_index(db, body.novel_id, body.chapter_index)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    content_res = await NovelService.get_chapter_content(db, chapter.id)
    content = (content_res.get("content") or "") if content_res else ""
    if not (content or "").strip():
        raise HTTPException(status_code=400, detail="Chapter has no content to index")
    await asyncio.to_thread(
        _run_index_chapter,
        novel.title,
        body.chapter_index,
        content,
    )
    return {"success": True, "novel_title": novel.title, "chapter_index": body.chapter_index}


@router.delete("/index", response_model=dict)
async def delete_index(
    novel_id: str = Query(...),
    chapter_index: Optional[int] = Query(None, description="不传则删除该小说下全部索引"),
    db: AsyncSession = Depends(get_db),
):
    """删除指定小说下某章的索引，或该小说下全部索引。"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    await asyncio.to_thread(_run_delete_index, novel.title, chapter_index)
    return {"success": True, "novel_title": novel.title, "chapter_index": chapter_index}
