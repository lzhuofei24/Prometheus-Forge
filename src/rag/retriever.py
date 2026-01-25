"""
检索器模块

从 ChromaDB 中检索相关的文本片段，用于 RAG 查询。
"""

from typing import List, Dict, Any
import chromadb


class VectorRetriever:
    """
    向量检索器
    
    基于查询文本从 ChromaDB 中检索最相关的文本片段。
    """
    
    def __init__(self, collection):
        """
        初始化检索器
        
        Args:
            collection: ChromaDB 集合对象
        """
        self.collection = collection
    
    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        检索相关文本片段
        
        ChromaDB 会自动将查询文本转换为向量，并在集合中搜索最相似的文档。
        
        Args:
            query: 查询文本
            top_k: 返回前 k 个最相关的结果
            
        Returns:
            检索结果列表，每个元素包含：
            - text: 文本内容
            - metadata: 元数据字典
            - distance: 相似度距离（越小越相似）
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            if not query or not query.strip():
                logger.warning("查询文本为空，返回空结果")
                return []
            
            logger.info(f"开始检索: query='{query[:50]}...', top_k={top_k}")
            
            # 使用 ChromaDB 的 query 方法进行相似度搜索
            try:
                logger.info("调用 ChromaDB query")
                if not self.collection:
                    logger.warning("collection 为空，返回空结果")
                    return []
                results = self.collection.query(
                    query_texts=[query],
                    n_results=top_k
                )
                logger.info(f"ChromaDB query 完成，结果类型: {type(results)}")
                if results:
                    logger.info(f"结果 keys: {list(results.keys()) if isinstance(results, dict) else 'N/A'}")
                else:
                    logger.info("ChromaDB 返回空结果")
                    return []
            except Exception as query_error:
                logger.warning(f"ChromaDB query 失败: {str(query_error)}")
                return []
        
            # 格式化返回结果
            logger.info("格式化检索结果")
            retrieved = []
            try:
                if not results:
                    logger.info("results 为空，返回空列表")
                    return []
                    
                if results.get("documents"):
                    documents_list = results["documents"]
                    if documents_list and len(documents_list) > 0 and documents_list[0]:
                        documents = documents_list[0]
                        metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") and results["metadatas"] else [{}] * len(documents)
                        distances = results.get("distances", [[]])[0] if results.get("distances") and results["distances"] else [0.0] * len(documents)
                        
                        for i, doc in enumerate(documents):
                            if doc:
                                retrieved.append({
                                    "text": doc,
                                    "metadata": metadatas[i] if i < len(metadatas) else {},
                                    "distance": distances[i] if i < len(distances) else 0.0
                                })
                    else:
                        logger.info("documents_list 为空")
                else:
                    logger.info("results 中没有 documents 字段")
                
                logger.info(f"检索完成，返回 {len(retrieved)} 个结果")
                return retrieved
            except Exception as format_error:
                logger.warning(f"格式化结果失败: {str(format_error)}")
                return []
        except Exception as e:
            logger.error(f"VectorRetriever.retrieve() 执行失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def retrieve_by_metadata(self, metadata_filter: Dict[str, Any], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        根据元数据过滤检索
        
        使用 ChromaDB 的 where 条件进行元数据过滤。
        支持精确匹配和范围查询。
        
        Args:
            metadata_filter: 元数据过滤条件（字典格式）
                例如：{"novel_name": "test_novel", "chapter_num": 1}
            top_k: 返回前 k 个结果
            
        Returns:
            检索结果列表，格式与 retrieve() 相同
        """
        if not metadata_filter:
            return []
        
        # 使用 ChromaDB 的 get 方法根据元数据过滤
        # ChromaDB 的 where 条件格式：{"field": {"$eq": "value"}} 用于精确匹配
        where_conditions = {}
        for key, value in metadata_filter.items():
            where_conditions[key] = {"$eq": value}
        
        # 获取所有匹配的文档
        results = self.collection.get(
            where=where_conditions,
            limit=top_k
        )
        
        # 格式化返回结果
        retrieved = []
        if results and results.get("ids"):
            documents = results.get("documents", [])
            metadatas = results.get("metadatas", [])
            
            for i, doc_id in enumerate(results["ids"]):
                retrieved.append({
                    "text": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "distance": 0.0  # 元数据过滤不计算相似度距离
                })
        
        return retrieved
    
    def get_collection_stats(self) -> Dict[str, Any]:
        try:
            total_count = self.collection.count()
            
            results = self.collection.get(limit=10000)
            
            novel_names = set()
            if results and results.get("metadatas"):
                for metadata in results["metadatas"]:
                    if metadata and "novel_name" in metadata:
                        novel_names.add(metadata["novel_name"])
            
            return {
                "total_chunks": total_count,
                "novel_count": len(novel_names),
                "novels": list(novel_names)
            }
        except Exception:
            return {
                "total_chunks": 0,
                "novel_count": 0,
                "novels": []
            }