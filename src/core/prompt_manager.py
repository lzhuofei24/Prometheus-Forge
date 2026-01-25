import os
import logging

mirror_sources = [
    "https://hf-mirror.com",
    "https://huggingface.co",
]

if not os.getenv("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = mirror_sources[0]

os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "300"

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import Optional

class PromptRouter:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PromptRouter, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if PromptRouter._initialized:
            return

        db_path = os.path.join(os.path.dirname(__file__), '../../data/chroma_db')
        os.makedirs(db_path, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(anonymized_telemetry=False)
        )

        self.collection = self.client.get_or_create_collection(
            name="prompt_templates",
            metadata={"hnsw:space": "cosine"}
        )

        self._encoder = None

        PromptRouter._initialized = True
    
    @property
    def encoder(self):
        """延迟加载 encoder，避免模块导入时下载模型"""
        if self._encoder is None:
            logger = logging.getLogger(__name__)
            
            model_name = 'BAAI/bge-small-zh-v1.5'
            hf_endpoint = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
            
            logger.info(f"使用 HuggingFace 镜像: {hf_endpoint}")
            logger.info(f"正在加载 sentence-transformers 模型 ({model_name})...")
            
            for attempt in range(3):
                try:
                    import time
                    if attempt > 0:
                        wait_time = 2 ** attempt
                        logger.info(f"重试 {attempt + 1}/3，等待 {wait_time} 秒...")
                        time.sleep(wait_time)
                        
                        if attempt == 1:
                            logger.info("尝试切换到官方源...")
                            os.environ["HF_ENDPOINT"] = "https://huggingface.co"
                        elif attempt == 2:
                            logger.info("尝试切换回镜像源...")
                            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                    
                    self._encoder = SentenceTransformer(model_name)
                    logger.info("模型加载成功")
                    break
                except Exception as e:
                    if attempt == 2:
                        logger.error(f"模型加载失败（已重试3次）: {e}")
                        logger.error("\n解决方案:")
                        logger.error("1. 检查网络连接，可能需要使用代理")
                        logger.error("2. 设置代理: export HTTP_PROXY=http://your-proxy:port")
                        logger.error("3. 手动下载模型:")
                        logger.error(f"   git clone https://hf-mirror.com/{model_name} ~/.cache/huggingface/hub/models--{model_name.replace('/', '--')}")
                        logger.error("4. 或使用其他镜像源，修改代码中的 mirror_sources 列表")
                        raise
                    else:
                        logger.warning(f"加载失败，将重试: {e}")
        return self._encoder

    def add_template(self, name: str, description: str, full_content: str):
        embedding = self.encoder.encode(description).tolist()
        
        try:
            self.collection.add(
                embeddings=[embedding],
                documents=[full_content],
                metadatas=[{
                    "name": name,
                    "description": description,
                    "full_content": full_content
                }],
                ids=[name]
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"添加模板失败: {e}")
            raise

    def get_best_prompt(self, query: str) -> Optional[str]:
        query_embedding = self.encoder.encode(query).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=1
        )
        
        if results['documents'] and len(results['documents'][0]) > 0:
            return results['documents'][0][0]
        
        return None
    
    def list_templates(self):
        """列出所有模板"""
        try:
            all_items = self.collection.get()
            if all_items is None:
                return {'ids': [], 'metadatas': [], 'documents': []}
            if not isinstance(all_items, dict):
                return {'ids': [], 'metadatas': [], 'documents': []}
            if 'ids' not in all_items:
                all_items['ids'] = []
            if 'metadatas' not in all_items:
                all_items['metadatas'] = []
            if 'documents' not in all_items:
                all_items['documents'] = []
            return all_items
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"获取模板列表失败: {e}")
            return {'ids': [], 'metadatas': [], 'documents': []}
    
    def delete_template(self, template_id: str):
        """删除模板"""
        try:
            self.collection.delete(ids=[template_id])
            return True
        except Exception as e:
            return False
