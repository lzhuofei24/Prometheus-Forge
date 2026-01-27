"""
检索与索引 API：向量检索、列出已索引章节、添加/删除索引。
复用 RAG（ChromaDB）与 Knowledge 的索引逻辑，仅支持手动调用，不进入工作流。
"""
import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.services.novel_service import NovelService
from src.core.config import CHROMA_BASE
from src.core.database import get_db
from src.rag import index_ops

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def _get_indexer_and_collection(novel_name: str):
    """返回 (VectorIndexer, collection)，与 index_ops 使用同一 path/collection 解析。"""
    from src.rag.indexer import VectorIndexer
    chroma_path, cn = index_ops.get_chroma_path_and_collection_name(novel_name)
    chroma_path.mkdir(parents=True, exist_ok=True)
    indexer = VectorIndexer(chroma_path, collection_name=cn)
    return indexer, indexer.collection


def _list_indexed_novel_dirs() -> List[str]:
    """返回已存在 Chroma 目录名（与 index_ops 的 path key 一致）。"""
    if not CHROMA_BASE.exists():
        return []
    return [d.name for d in CHROMA_BASE.iterdir() if d.is_dir()]


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


def _enqueue_add_index(novel_id: str, chapter_index: int):
    """将添加索引任务发往 knowledge 队列，由 knowledge worker 执行并打日志。"""
    from src.workers.tasks_new import task_add_index
    return task_add_index.delay(novel_id, chapter_index)


def _enqueue_delete_index(novel_id: str, chapter_index: Optional[int] = None):
    """将删除索引任务发往 knowledge 队列，由 knowledge worker 执行并打日志。"""
    from src.workers.tasks_new import task_delete_index
    return task_delete_index.delay(novel_id, chapter_index)


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


_ENQUEUE_TIMEOUT = 5.0  # 入队等待 Redis/Celery 的超时，避免接口一直挂起


@router.post("/index", response_model=dict)
async def add_index(
    body: AddIndexBody,
    db: AsyncSession = Depends(get_db),
):
    """提交添加索引任务到 knowledge 队列，由 knowledge worker 执行（日志在其终端）。不在本接口拉取正文，避免大章导致超时。"""
    novel = await NovelService.get_novel_by_id(db, body.novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    chapter = await NovelService.get_chapter_by_novel_and_index(db, body.novel_id, body.chapter_index)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    # 不做 get_chapter_content：正文由 worker 内加载，避免大章导致接口读超时
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_enqueue_add_index, body.novel_id, body.chapter_index),
            timeout=_ENQUEUE_TIMEOUT,
        )
        return {"success": True, "queued": True, "task_id": getattr(result, "id", None), "novel_title": novel.title, "chapter_index": body.chapter_index}
    except asyncio.TimeoutError:
        logger.warning("add_index enqueue timeout (redis/celery?) novel_id=%s chapter_index=%s", body.novel_id, body.chapter_index)
        raise HTTPException(status_code=503, detail="Queue busy or Redis unavailable, enqueue timed out. Check Redis and knowledge worker.")
    except Exception as e:
        logger.warning("add_index enqueue failed: %s", e)
        raise HTTPException(status_code=503, detail=f"Enqueue failed: {e}. Check Redis and Celery broker.")


@router.delete("/index", response_model=dict)
async def delete_index(
    novel_id: str = Query(...),
    chapter_index: Optional[int] = Query(None, description="不传则删除该小说下全部索引"),
    db: AsyncSession = Depends(get_db),
):
    """提交删除索引任务到 knowledge 队列，由 knowledge worker 执行（日志在其终端）。"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_enqueue_delete_index, novel_id, chapter_index),
            timeout=_ENQUEUE_TIMEOUT,
        )
        return {"success": True, "queued": True, "task_id": getattr(result, "id", None), "novel_title": novel.title, "chapter_index": chapter_index}
    except asyncio.TimeoutError:
        logger.warning("delete_index enqueue timeout novel_id=%s", novel_id)
        raise HTTPException(status_code=503, detail="Queue busy or Redis unavailable, enqueue timed out. Check Redis and knowledge worker.")
    except Exception as e:
        logger.warning("delete_index enqueue failed: %s", e)
        raise HTTPException(status_code=503, detail=f"Enqueue failed: {e}. Check Redis and Celery broker.")
