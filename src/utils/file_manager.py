"""
文件管理器模块

提供 ProjectManager 类，负责管理小说项目的目录结构和文件操作。
强制执行 workspace/{小说名称}/ 的层级结构，包括全局设定区和动态章节区。
"""

from pathlib import Path
from typing import Optional, Dict, Any, List
import json
import logging


class ProjectManager:
    """
    项目管理器
    
    负责创建和管理小说项目的目录结构，提供统一的文件操作接口。
    所有生成的内容都存储在 workspace/{novel_name}/ 目录下。
    """
    
    def __init__(self, workspace_root: Path):
        """
        初始化项目管理器
        
        Args:
            workspace_root: workspace 目录的根路径
        """
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
    
    def init_novel(self, name: str) -> Path:
        """
        初始化小说项目文件夹结构
        
        创建以下目录结构：
        workspace/{name}/
        ├── global/          # 全局设定区
        │   ├── bios.json
        │   ├── world.md
        │   └── relation_graph.json
        └── chapters/        # 动态章节区
        
        Args:
            name: 小说名称
            
        Returns:
            小说项目的根路径
        """
        novel_root = self.workspace_root / name
        novel_root.mkdir(parents=True, exist_ok=True)
        
        # 创建全局设定区
        global_dir = novel_root / "global"
        global_dir.mkdir(exist_ok=True)
        
        # 初始化全局设定文件（如果不存在）
        if not (global_dir / "bios.json").exists():
            self.save_content(global_dir / "bios.json", {})
        
        if not (global_dir / "world.md").exists():
            self.save_content(global_dir / "world.md", "# 世界观设定\n\n")
        
        if not (global_dir / "relation_graph.json").exists():
            self.save_content(global_dir / "relation_graph.json", {})
        
        # 创建章节目录
        chapters_dir = novel_root / "chapters"
        chapters_dir.mkdir(exist_ok=True)
        
        return novel_root
    
    def get_chapter_path(self, novel: str, chapter_num: int) -> Path:
        """
        获取章节目录路径
        
        使用 3 位数字补零格式（001, 002, ...）
        
        Args:
            novel: 小说名称
            chapter_num: 章节编号（从 1 开始）
            
        Returns:
            章节目录的 Path 对象，例如：workspace/{novel}/chapters/chapter_001
        """
        novel_root = self.workspace_root / novel
        chapter_name = f"chapter_{chapter_num:03d}"
        return novel_root / "chapters" / chapter_name
    
    def init_chapter(self, novel: str, chapter_num: int) -> Path:
        """
        初始化章节目录和文件
        
        创建章节目录并初始化以下文件：
        - outline.md: 本章大纲
        - content.md: 本章正文
        - meta.json: 本章元数据
        
        Args:
            novel: 小说名称
            chapter_num: 章节编号
            
        Returns:
            章节目录的 Path 对象
        """
        chapter_path = self.get_chapter_path(novel, chapter_num)
        chapter_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化文件（如果不存在）
        if not (chapter_path / "outline.md").exists():
            self.save_content(chapter_path / "outline.md", f"# 第 {chapter_num} 章 大纲\n\n")
        
        if not (chapter_path / "content.md").exists():
            self.save_content(chapter_path / "content.md", f"# 第 {chapter_num} 章\n\n")
        
        if not (chapter_path / "meta.json").exists():
            meta = {
                "chapter_num": chapter_num,
                "title": "",
                "status": "draft",
                "word_count": 0,
                "character_states": {},
                "created_at": "",
                "updated_at": ""
            }
            self.save_content(chapter_path / "meta.json", meta)
        
        return chapter_path
    
    def save_content(self, file_path: Path, content: Any, mode: str = "w") -> None:
        """
        保存内容到文件
        
        根据文件扩展名自动选择保存格式：
        - .json: JSON 格式
        - .md, .txt: 文本格式
        - 其他: 文本格式
        
        Args:
            file_path: 文件路径
            content: 要保存的内容（字符串或字典/列表）
            mode: 文件打开模式（默认 'w'）
        """
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if file_path.suffix == ".json":
            with open(file_path, mode, encoding="utf-8") as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            with open(file_path, mode, encoding="utf-8") as f:
                if isinstance(content, str):
                    f.write(content)
                else:
                    f.write(str(content))
    
    def load_content(self, file_path: Path) -> Any:
        """
        从文件加载内容
        
        根据文件扩展名自动选择加载格式：
        - .json: 解析为字典/列表
        - 其他: 作为文本字符串返回
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容（字符串或字典/列表）
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        if file_path.suffix == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
    
    def get_global_settings_path(self, novel: str) -> Path:
        """
        获取全局设定目录路径
        
        Args:
            novel: 小说名称
            
        Returns:
            全局设定目录的 Path 对象
        """
        return self.workspace_root / novel / "global"
    
    def list_chapters(self, novel: str) -> list[int]:
        """
        列出所有已存在的章节编号
        
        Args:
            novel: 小说名称
            
        Returns:
            章节编号列表（已排序）
        """
        chapters_dir = self.workspace_root / novel / "chapters"
        if not chapters_dir.exists():
            return []
        
        chapter_nums = []
        for item in chapters_dir.iterdir():
            if item.is_dir() and item.name.startswith("chapter_"):
                try:
                    num = int(item.name.split("_")[1])
                    chapter_nums.append(num)
                except (ValueError, IndexError):
                    continue
        
        return sorted(chapter_nums)
    
    def get_next_chapter_num(self, novel: str) -> int:
        """
        获取下一个章节编号
        
        Args:
            novel: 小说名称
            
        Returns:
            下一个章节编号（如果没有任何章节，返回 1）
        """
        existing = self.list_chapters(novel)
        return max(existing) + 1 if existing else 1
    
    def index_novel_content(self, novel_name: str, indexer=None) -> Dict[str, Any]:
        from src.rag.indexer import VectorIndexer
        import time
        
        logger = logging.getLogger(__name__)
        novel_root = self.workspace_root / novel_name
        
        if not novel_root.exists():
            logger.error(f"[索引] 小说不存在: {novel_name}")
            return {"indexed_chapters": 0, "total_chunks": 0, "error": "小说不存在"}
        
        start_time = time.time()
        logger.info(f"[索引] ==================== 开始索引小说: {novel_name} ====================")
        
        persist_dir = self.workspace_root.parent / "data" / "novel_content_db"
        logger.info(f"[索引] 向量数据库路径: {persist_dir}")
        
        # 复用传入的 indexer 或创建新的
        if indexer is None:
            indexer_start = time.time()
            indexer = VectorIndexer(persist_directory=persist_dir, collection_name="novel_content")
            indexer_elapsed = time.time() - indexer_start
            logger.info(f"[索引] 向量索引器初始化完成，耗时 {indexer_elapsed:.2f}s")
        else:
            logger.info(f"[索引] 使用缓存的向量索引器（跳过初始化）")
        
        chapters = self.list_chapters(novel_name)
        total_chapters = len(chapters)
        logger.info(f"[索引] 待索引章节数: {total_chapters}")
        
        if total_chapters == 0:
            logger.warning(f"[索引] 小说 {novel_name} 没有章节，跳过索引")
            return {"indexed_chapters": 0, "total_chunks": 0, "error": "没有章节"}
        
        indexed_chapters = 0
        total_chunks = 0
        skipped_chapters = 0
        failed_chapters = []
        
        for idx, chapter_num in enumerate(chapters, 1):
            chapter_start = time.time()
            logger.info(f"[索引] ========== 处理章节 {idx}/{total_chapters}: 第{chapter_num}章 ==========")
            
            try:
                chapter_path = self.get_chapter_path(novel_name, chapter_num)
                content_file = chapter_path / "content.md"
                
                if not content_file.exists():
                    logger.warning(f"[索引] 章节 {chapter_num}: content.md 不存在，跳过")
                    skipped_chapters += 1
                    continue
                
                load_start = time.time()
                content = self.load_content(content_file)
                load_elapsed = time.time() - load_start
                
                if not content or len(content.strip()) < 100:
                    logger.warning(f"[索引] 章节 {chapter_num}: 内容过短 ({len(content)} 字符)，跳过")
                    skipped_chapters += 1
                    continue
                
                logger.info(f"[索引] 章节 {chapter_num}: 内容加载完成 ({len(content)} 字符)，耗时 {load_elapsed:.2f}s")
                
                metadata = {
                    "novel_name": novel_name,
                    "chapter_num": chapter_num,
                    "source_type": "chapter_content"
                }
                
                chunks_before = indexer.collection.count()
                logger.debug(f"[索引] 章节 {chapter_num}: 索引前 chunks 数量 = {chunks_before}")
                
                index_start = time.time()
                indexer.index_text(content, metadata=metadata)
                index_elapsed = time.time() - index_start
                
                chunks_after = indexer.collection.count()
                chapter_chunks = chunks_after - chunks_before
                total_chunks += chapter_chunks
                indexed_chapters += 1
                
                chapter_elapsed = time.time() - chapter_start
                logger.info(f"[索引] 章节 {chapter_num}: ✅ 索引完成，新增 {chapter_chunks} 个chunks，耗时 {chapter_elapsed:.2f}s (加载 {load_elapsed:.2f}s + 索引 {index_elapsed:.2f}s)")
                
                # 立即释放本章节的内存（激进策略）
                del content, metadata
                import gc
                gc.collect()
                gc.collect()  # 双重回收
                gc.collect(2)  # 全量回收
                
                # 给系统时间清理内存
                import time
                time.sleep(0.02)  # 每章后暂停20ms
                
            except Exception as e:
                chapter_elapsed = time.time() - chapter_start
                logger.error(f"[索引] 章节 {chapter_num}: ❌ 索引失败，耗时 {chapter_elapsed:.2f}s")
                logger.error(f"[索引] 错误详情: {type(e).__name__}: {str(e)}")
                import traceback
                logger.debug(f"[索引] 堆栈跟踪:\n{traceback.format_exc()}")
                failed_chapters.append(chapter_num)
                continue
        
        total_elapsed = time.time() - start_time
        logger.info(f"[索引] ==================== 索引完成 ====================")
        logger.info(f"[索引] 小说: {novel_name}")
        logger.info(f"[索引] 总章节数: {total_chapters}")
        logger.info(f"[索引] 成功索引: {indexed_chapters} 章")
        logger.info(f"[索引] 跳过: {skipped_chapters} 章")
        logger.info(f"[索引] 失败: {len(failed_chapters)} 章 {failed_chapters if failed_chapters else ''}")
        logger.info(f"[索引] 总 chunks: {total_chunks}")
        logger.info(f"[索引] 总耗时: {total_elapsed:.2f}s")
        logger.info(f"[索引] 平均: {total_elapsed/indexed_chapters:.2f}s/章" if indexed_chapters > 0 else "[索引] 无有效章节")
        logger.info(f"[索引] ====================================================")
        
        return {
            "indexed_chapters": indexed_chapters,
            "total_chunks": total_chunks,
            "skipped_chapters": skipped_chapters,
            "failed_chapters": failed_chapters,
            "indexer": indexer  # 返回 indexer 供后续复用
        }
    
    def delete_novel_index(self, novel_name: str, indexer=None) -> Dict[str, Any]:
        """
        删除指定小说的所有索引
        
        Args:
            novel_name: 小说名称
            indexer: 可选的 VectorIndexer 实例（用于复用）
            
        Returns:
            删除结果字典
        """
        from src.rag.indexer import VectorIndexer
        
        logger = logging.getLogger(__name__)
        logger.info(f"[删除索引] 开始删除小说索引: {novel_name}")
        
        persist_dir = self.workspace_root.parent / "data" / "novel_content_db"
        
        try:
            # 复用传入的 indexer 或创建新的
            if indexer is None:
                indexer = VectorIndexer(persist_directory=persist_dir, collection_name="novel_content")
            
            # 获取该小说的所有索引
            results = indexer.collection.get(
                where={"novel_name": {"$eq": novel_name}},
                limit=10000
            )
            
            if not results or not results.get("ids"):
                logger.warning(f"[删除索引] 小说 {novel_name} 没有索引记录")
                return {"success": True, "deleted_count": 0, "message": "没有索引记录"}
            
            ids_to_delete = results["ids"]
            deleted_count = len(ids_to_delete)
            
            logger.info(f"[删除索引] 找到 {deleted_count} 个索引片段，开始删除...")
            
            # 批量删除
            indexer.collection.delete(ids=ids_to_delete)
            
            logger.info(f"[删除索引] ✅ 删除完成: {deleted_count} 个片段")
            
            return {
                "success": True,
                "deleted_count": deleted_count,
                "message": f"成功删除 {deleted_count} 个索引片段"
            }
            
        except Exception as e:
            logger.error(f"[删除索引] ❌ 删除失败: {str(e)}")
            import traceback
            logger.debug(f"[删除索引] 堆栈跟踪:\n{traceback.format_exc()}")
            return {
                "success": False,
                "deleted_count": 0,
                "error": str(e)
            }
    
    def get_index_status(self, novel_name: str, indexer=None) -> Dict[str, Any]:
        """
        获取小说索引状态
        
        Args:
            novel_name: 小说名称
            indexer: 可选的 VectorIndexer 实例（用于复用）
            
        Returns:
            索引状态字典
        """
        from src.rag.indexer import VectorIndexer
        
        persist_dir = self.workspace_root.parent / "data" / "novel_content_db"
        
        try:
            # 复用传入的 indexer 或创建新的
            if indexer is None:
                indexer = VectorIndexer(persist_directory=persist_dir, collection_name="novel_content")
            
            results = indexer.collection.get(
                where={"novel_name": {"$eq": novel_name}},
                limit=10000
            )
            
            chunk_count = len(results.get("ids", [])) if results else 0
            
            return {
                "indexed": chunk_count > 0,
                "chunk_count": chunk_count
            }
        except Exception:
            return {
                "indexed": False,
                "chunk_count": 0
            }
    
    def search_similar_content(
        self,
        query_text: str,
        novel_name: Optional[str] = None,
        top_k: int = 10,
        threshold: float = 0.5,
        indexer=None
    ) -> List[Dict[str, Any]]:
        """
        检索相似内容
        
        Args:
            query_text: 查询文本
            novel_name: 小说名称（可选）
            top_k: 返回结果数量
            threshold: 相似度阈值
            indexer: 可选的 VectorIndexer 实例（用于复用）
            
        Returns:
            检索结果列表
        """
        from src.rag.indexer import VectorIndexer
        from src.rag.retriever import VectorRetriever
        
        logger = logging.getLogger(__name__)
        
        if not query_text or len(query_text.strip()) < 10:
            return []
        
        persist_dir = self.workspace_root.parent / "data" / "novel_content_db"
        
        try:
            # 复用传入的 indexer 或创建新的
            if indexer is None:
                indexer = VectorIndexer(persist_directory=persist_dir, collection_name="novel_content")
            retriever = VectorRetriever(indexer.collection)
            
            if novel_name:
                results = indexer.collection.query(
                    query_texts=[query_text],
                    n_results=top_k * 2,
                    where={"novel_name": {"$eq": novel_name}}
                )
            else:
                results = indexer.collection.query(
                    query_texts=[query_text],
                    n_results=top_k * 2
                )
            
            formatted_results = []
            
            if results and results.get("documents") and results["documents"][0]:
                documents = results["documents"][0]
                metadatas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]
                
                for i, doc in enumerate(documents):
                    distance = distances[i] if i < len(distances) else 1.0
                    similarity = 1 - distance
                    
                    if similarity < threshold:
                        continue
                    
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    
                    preview = doc[:300] + "..." if len(doc) > 300 else doc
                    
                    formatted_results.append({
                        "text": doc,
                        "novel_name": metadata.get("novel_name", "未知"),
                        "chapter_num": metadata.get("chapter_num", 0),
                        "chunk_index": metadata.get("chunk_index", 0),
                        "similarity": round(similarity, 3),
                        "preview": preview
                    })
            
            formatted_results.sort(key=lambda x: x["similarity"], reverse=True)
            
            return formatted_results[:top_k]
            
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return []
