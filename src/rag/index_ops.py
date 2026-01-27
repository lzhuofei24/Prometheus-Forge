"""
RAG 索引增删的同步实现，供 API（asyncio.to_thread）与 knowledge worker 任务调用。
所有索引操作在此处统一打日志，在 knowledge worker 中执行时日志会出现在该 worker 终端。
"""
import hashlib
import logging
import re
import unicodedata
from typing import Optional

from src.core.config import CHROMA_BASE

logger = logging.getLogger(__name__)


def _normalize_novel_name(name: str) -> str:
    """与 inspector 保持一致：路径用 NFC，避免同一书名因编码差异读写不同目录。"""
    return unicodedata.normalize("NFC", (name or "").strip()) or "default"


def _stable_suffix(s: str) -> int:
    """确定性的数字后缀，跨进程一致（Python hash(str) 会随进程变化）。"""
    return int(hashlib.md5((s or "").encode("utf-8")).hexdigest(), 16) % 100000


def _safe_collection_name(novel_name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]", "_", (novel_name or "").strip()).strip("_")
    if not s or len(s) < 3:
        s = f"novel_{_stable_suffix(novel_name)}"
    if not re.match(r"^[a-zA-Z0-9]", s):
        s = f"n_{s}"
    if not re.match(r"[a-zA-Z0-9]$", s):
        s = f"{s}x"
    name = f"{s}_chapters"
    return name if len(name) >= 3 else f"novel_{_stable_suffix(novel_name)}_chapters"


def get_chroma_path_and_collection_name(novel_name: str):
    """返回 (chroma_path, collection_name)，供 inspector/retrieval 与写入逻辑共用，保证读写一致。"""
    key = _normalize_novel_name(novel_name)
    return (CHROMA_BASE / key, _safe_collection_name(key))


def run_index_chapter(novel_name: str, chapter_num: int, content: str) -> None:
    """将一章正文写入 ChromaDB。先删该章旧向量再写入，避免重复添加。"""
    logger.info("[index_ops] 开始添加索引 novel_name=%s chapter_num=%s content_len=%d", novel_name, chapter_num, len(content or ""))
    try:
        from src.rag.indexer import VectorIndexer
        key = _normalize_novel_name(novel_name)
        chroma_path = CHROMA_BASE / key
        chroma_path.mkdir(parents=True, exist_ok=True)
        cn = _safe_collection_name(key)
        indexer = VectorIndexer(chroma_path, collection_name=cn)
        coll = indexer.collection
        # 先删该章已有向量再写入（与 indexer 稳定 id 双保险：旧数据用删，新数据同 id 覆盖）
        data = coll.get(include=["metadatas"])
        ids_to_del = []
        if data and data.get("ids") and data.get("metadatas"):
            try:
                ch_int = int(chapter_num)
            except (TypeError, ValueError):
                ch_int = chapter_num
            for i, meta in enumerate(data["metadatas"]):
                if not meta:
                    continue
                if meta.get("novel_name") != key:
                    continue
                mc = meta.get("chapter_num")
                if mc is not None:
                    try:
                        mc = int(mc)
                    except (TypeError, ValueError):
                        pass
                if mc == ch_int or mc == chapter_num:
                    ids_to_del.append(data["ids"][i])
        if ids_to_del:
            coll.delete(ids=ids_to_del)
            logger.info("[index_ops] 已删除该章旧向量 %d 条，再写入", len(ids_to_del))
        metadata = {"novel_name": key, "chapter_num": chapter_num}
        indexer.index_text(content, metadata=metadata, batch_size=64)
        logger.info("[index_ops] 索引添加完成 novel_name=%s chapter_num=%s", novel_name, chapter_num)
    except Exception as e:
        logger.exception("[index_ops] 索引添加失败 novel_name=%s chapter_num=%s: %s", novel_name, chapter_num, e)
        raise


def run_delete_index(novel_name: str, chapter_num: Optional[int] = None) -> None:
    """删除该小说下某章或全部向量索引。由 knowledge 任务或 API 线程调用。"""
    scope = f"chapter_num={chapter_num}" if chapter_num is not None else "全书"
    logger.info("[index_ops] 开始删除索引 novel_name=%s %s", novel_name, scope)
    try:
        from src.rag.indexer import VectorIndexer
        key = _normalize_novel_name(novel_name)
        chroma_path = CHROMA_BASE / key
        chroma_path.mkdir(parents=True, exist_ok=True)
        cn = _safe_collection_name(key)
        indexer = VectorIndexer(chroma_path, collection_name=cn)
        coll = indexer.collection
        if chapter_num is not None:
            data = coll.get(include=["metadatas"])
            ids_to_del = []
            if data and data.get("ids") and data.get("metadatas"):
                for i, meta in enumerate(data["metadatas"]):
                    if meta and meta.get("novel_name") == key and meta.get("chapter_num") == chapter_num:
                        ids_to_del.append(data["ids"][i])
            if ids_to_del:
                coll.delete(ids=ids_to_del)
                logger.info("[index_ops] 索引删除完成 novel_name=%s chapter_num=%s 删除条数=%d", novel_name, chapter_num, len(ids_to_del))
            else:
                logger.info("[index_ops] 索引删除完成 novel_name=%s chapter_num=%s 无匹配条数", novel_name, chapter_num)
        else:
            data = coll.get(include=[])
            n = len(data.get("ids") or [])
            if data and data.get("ids"):
                coll.delete(ids=data["ids"])
            logger.info("[index_ops] 索引删除完成 novel_name=%s 全书 删除条数=%d", novel_name, n)
    except Exception as e:
        logger.exception("[index_ops] 索引删除失败 novel_name=%s %s: %s", novel_name, scope, e)
        raise
