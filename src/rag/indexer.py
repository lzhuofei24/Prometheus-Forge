"""
向量索引器模块

负责将文本切片并存入 ChromaDB 向量数据库。
"""

import os
import re
import logging
import gc
from pathlib import Path

# 设置本地模型缓存目录
project_root = Path(__file__).parent.parent.parent
models_dir = project_root / "models"
models_dir.mkdir(exist_ok=True)

if not os.getenv("SENTENCE_TRANSFORMERS_HOME"):
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(models_dir)

# 检查本地是否已有模型缓存
model_cache_exists = (models_dir / "BAAI_bge-small-zh-v1.5").exists() or \
                     (models_dir / "models--BAAI--bge-small-zh-v1.5").exists()

# 如果本地有缓存，强制离线模式（避免网络检查）
if model_cache_exists:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
else:
    # 本地没有缓存，允许下载（但使用镜像）
    os.environ["HF_HUB_OFFLINE"] = "0"
    if not os.getenv("HF_ENDPOINT"):
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "300"
from typing import List, Dict, Any
import sys
from contextlib import redirect_stderr
from io import StringIO
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils import embedding_functions

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    # 如果没有 tqdm，提供一个简单的替代
    def tqdm(iterable, desc="", total=None):
        return iterable


class VectorIndexer:
    """
    向量索引器
    
    将文本分块并存储到 ChromaDB 中，用于后续的 RAG 检索。
    """
    
    def __init__(self, persist_directory: Path, collection_name: str = "novel_chunks"):
        """
        初始化向量索引器
        
        Args:
            persist_directory: ChromaDB 持久化目录
            collection_name: 集合名称
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        # 初始化 ChromaDB 客户端
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=ChromaSettings(anonymized_telemetry=False),
            tenant="default_tenant",
            database="default_database"
        )
        
        # 尝试使用不同的嵌入函数（按优先级）
        embedding_function = None
        
        # 优先级1: 尝试使用 SentenceTransformer（离线模式）
        try:
            logger = logging.getLogger(__name__)
            model_name = "BAAI/bge-small-zh-v1.5"
            
            # 仅尝试一次离线加载，不重试网络
            try:
                with redirect_stderr(StringIO()):
                    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                        model_name=model_name
                    )
                logger.info(f"✅ 离线加载模型成功: {model_name}")
            except Exception as e:
                logger.warning(f"⚠️ 离线加载模型失败（将使用默认函数）: {e}")
        except Exception:
            pass
        
        # 优先级2: 如果 SentenceTransformer 失败，尝试使用默认函数
        if embedding_function is None:
            try:
                embedding_function = embedding_functions.DefaultEmbeddingFunction()
            except Exception:
                pass
        
        # 优先级3: 如果都失败，使用 None（ChromaDB 会使用默认的 ONNX 函数）
        # 如果 ONNX 也失败，会在实际使用时抛出错误
        
        # 获取或创建集合
        try:
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=embedding_function,
                metadata={"description": "小说文本切片集合"}
            )
        except ValueError as e:
            if "sentence_transformers" in str(e) or "embedding function" in str(e).lower():
                try:
                    self.client.delete_collection(name=collection_name)
                except Exception:
                    pass
                self.collection = self.client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=embedding_function,
                    metadata={"description": "小说文本切片集合"}
                )
            else:
                raise
    
    def chunk_text(self, text: str, chunk_size: int = 100, chunk_overlap: int = 20) -> List[str]:
        """
        将文本分块（保留完整句子）
        
        智能分块策略：
        1. 按句子分割（。！？.!?等标点）
        2. 将句子逐个添加到chunk，直到接近chunk_size
        3. 保持句子完整性，不在句子中间切开
        4. 即使单句超过chunk_size，也保持完整
        
        Args:
            text: 原始文本
            chunk_size: 目标块大小（字符数，软限制）
            chunk_overlap: 重叠大小（字符数）
            
        Returns:
            文本块列表
        """
        import re
        
        if not text or not text.strip():
            return []
        
        # 按句子分割（保留标点符号）
        # 匹配中文和英文句子结束标点
        sentence_pattern = r'([^。！？\.\!\?]+[。！？\.\!\?]+)'
        sentences = re.findall(sentence_pattern, text)
        
        # 如果没有匹配到句子（可能文本没有标点），将整个文本作为一个句子
        if not sentences:
            sentences = [text.strip()]
        else:
            # 清理句子（去除首尾空白）
            sentences = [s.strip() for s in sentences if s.strip()]
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            # 如果当前chunk为空，直接添加这个句子（无论长度）
            if not current_chunk:
                current_chunk = sentence
            # 如果添加这个句子后不超过chunk_size，添加
            elif len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += sentence
            # 否则保存当前chunk，开始新chunk
            else:
                chunks.append(current_chunk)
                current_chunk = sentence
        
        # 保存最后一个chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        # 如果需要重叠且有多个chunk
        if chunk_overlap > 0 and len(chunks) > 1:
            overlapped_chunks = [chunks[0]]
            
            for i in range(1, len(chunks)):
                prev_chunk = chunks[i - 1]
                current_chunk = chunks[i]
                
                # 从前一个chunk末尾提取重叠内容（尽量按句子边界）
                if len(prev_chunk) > chunk_overlap:
                    # 尝试找到重叠区域内的最后一个句子边界
                    overlap_start = len(prev_chunk) - chunk_overlap
                    overlap_text = prev_chunk[overlap_start:]
                    
                    # 寻找重叠区域内的第一个句子开始位置
                    sentence_start_pattern = r'[。！？\.\!\?]+'
                    match = re.search(sentence_start_pattern, overlap_text)
                    if match:
                        # 从句子边界开始重叠
                        overlap_text = overlap_text[match.end():]
                    
                    overlapped_chunk = overlap_text + current_chunk
                else:
                    # 如果前一个chunk太短，使用整个chunk作为重叠
                    overlapped_chunk = prev_chunk + current_chunk
                
                overlapped_chunks.append(overlapped_chunk)
            
            return overlapped_chunks
        
        return chunks
    
    def index_text(self, text: str, metadata: Dict[str, Any] = None, batch_size: int = 128) -> None:
        """
        将文本索引到向量数据库（分批处理以控制内存使用）
        
        ChromaDB 会自动处理向量嵌入，我们只需要：
        1. 分块文本
        2. 为每个块生成唯一 ID
        3. 分批存储到 ChromaDB（避免内存溢出）
        
        Args:
            text: 要索引的文本
            metadata: 元数据字典（可选，会应用到所有块）
            batch_size: 每批处理的块数量（默认64，可根据内存调整）
        """
        if not text or not text.strip():
            return
        
        logger = logging.getLogger(__name__)
        
        # 1. 分块文本
        chunks = self.chunk_text(text)
        
        if not chunks:
            logger.warning("文本分块后为空，跳过索引")
            return
        
        total_chunks = len(chunks)
        logger.info(f"开始索引文本，共 {total_chunks} 个块，批次大小: {batch_size}")
        
        # 2. 准备基础元数据
        base_metadata = metadata.copy() if metadata else {}
        # 若有 novel_name + chapter_num，使用稳定 id，同章重复写入会覆盖，避免重复块
        use_stable_id = (
            base_metadata.get("novel_name") is not None
            and base_metadata.get("chapter_num") is not None
        )
        if use_stable_id:
            _sn = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", str(base_metadata.get("novel_name", "")))[:48]
            _ch = base_metadata.get("chapter_num")
        else:
            existing_count = self.collection.count()
        
        # 3. 分批处理
        successful_batches = 0
        failed_batches = 0
        
        # 使用 tqdm 显示进度（如果可用）
        batch_iterator = range(0, total_chunks, batch_size)
        if TQDM_AVAILABLE:
            batch_iterator = tqdm(batch_iterator, desc="索引批次", unit="batch")
        
        for batch_start in batch_iterator:
            batch_end = min(batch_start + batch_size, total_chunks)
            current_batch = chunks[batch_start:batch_end]
            
            # 为当前批次生成数据
            batch_ids = []
            batch_documents = []
            batch_metadatas = []
            
            for i, chunk in enumerate(current_batch):
                global_index = batch_start + i
                chunk_id = f"{_sn}_ch{_ch}_{global_index}" if use_stable_id else f"chunk_{existing_count + global_index}"
                batch_ids.append(chunk_id)
                batch_documents.append(chunk)
                
                # 为每个块添加块索引信息
                chunk_metadata = base_metadata.copy()
                chunk_metadata["chunk_index"] = global_index
                chunk_metadata["total_chunks"] = total_chunks
                batch_metadatas.append(chunk_metadata)
            
            # 4. 写入当前批次到 ChromaDB
            try:
                self.collection.add(
                    documents=batch_documents,
                    metadatas=batch_metadatas,
                    ids=batch_ids
                )
                successful_batches += 1
                logger.debug(f"批次 {batch_start}-{batch_end} 写入成功")
            except Exception as e:
                failed_batches += 1
                logger.error(f"批次 {batch_start}-{batch_end} 写入失败: {str(e)}")
                # 不中断流程，继续处理下一批
                continue
            finally:
                # 5. 释放内存（关键步骤）
                del batch_ids, batch_documents, batch_metadatas, current_batch
                gc.collect()
        
        # 6. 最终清理
        del chunks
        gc.collect()
        
        logger.info(f"索引完成: 成功 {successful_batches} 批，失败 {failed_batches} 批，共 {total_chunks} 个块")
    
    def clear_collection(self) -> None:
        """
        清空集合中的所有数据
        
        注意：这会删除集合中的所有文档，操作不可逆。
        """
        # 获取所有文档的 ID
        results = self.collection.get()
        if results and results.get("ids"):
            # 删除所有文档
            self.collection.delete(ids=results["ids"])
