import logging
import json
from typing import Dict, Any, List
from pathlib import Path
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager
from src.rag.indexer import VectorIndexer
from src.core.db_service import DatabaseService

logger = logging.getLogger(__name__)


class KnowledgeHandler(BaseAgentHandler):
    """
    档案员 Agent：负责维护世界观一致性的 RAG 记忆系统
    
    流程：
    1. 实体提取：从章节内容中提取关键信息（新角色、状态变更、新地点/物品）
    2. RAG 更新：将信息存入 ChromaDB 向量数据库
    3. 摘要更新：更新 Redis 中的 rolling_summary（最近 5 章的精简摘要）
    """
    
    def __init__(self, state_manager, dispatcher, llm_client: LLMClient, file_manager: ProjectManager):
        super().__init__(state_manager, dispatcher)
        self.llm_client = llm_client
        self.file_manager = file_manager

    def _process(self, workflow_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        核心处理逻辑：更新知识库
        
        Args:
            workflow_id: 工作流 ID
            input_data: 包含 chapter_content（已定稿的章节）
        """
        state = self.state_manager.get_state(workflow_id)
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        
        chapter_content = input_data.get("chapter_content") or state.get("draft_content", "")
        
        if not chapter_content:
            raise ValueError("必须提供 chapter_content")
        
        entities = self._extract_entities(chapter_content, novel_name, chapter_num)
        
        self._update_rag(novel_name, chapter_content, entities, chapter_num)
        
        rolling_summary = self._update_rolling_summary(novel_name, chapter_num, chapter_content)
        
        return {
            "entities_extracted": len(entities.get("characters", [])) + len(entities.get("locations", [])) + len(entities.get("items", [])),
            "rolling_summary": rolling_summary,
            "chapter_indexed": chapter_num
        }

    def _extract_entities(self, chapter_content: str, novel_name: str, chapter_num: int) -> Dict[str, Any]:
        """
        Step 1: 实体提取
        调用 LLM 提取本章出现的关键信息
        """
        extraction_prompt = f"""
你是一位专业的小说档案员。请从以下章节内容中提取关键信息。

**章节内容**：
{chapter_content[:2000]}

**提取要求**：
1. **新登场角色**：如果本章出现了新角色，记录其姓名、描述、性格特征
2. **角色状态变更**：如果已有角色发生了重大变化（如突破、受伤、获得新能力、性格转变），记录变更内容
3. **新地点/物品**：如果出现了新的重要地点或物品，记录其名称和描述

**输出格式**（严格 JSON）：
{{
  "characters": [
    {{
      "name": "角色名",
      "description": "角色描述",
      "status_change": "状态变更（如有）"
    }}
  ],
  "locations": [
    {{
      "name": "地点名",
      "description": "地点描述"
    }}
  ],
  "items": [
    {{
      "name": "物品名",
      "description": "物品描述"
    }}
  ]
}}

如果没有相关内容，返回空数组。
"""

        messages = [
            {"role": "system", "content": "You are a professional novel archivist. Extract key information from chapter content in JSON format."},
            {"role": "user", "content": extraction_prompt}
        ]

        response = self.llm_client.chat(messages, temperature=0.3, max_tokens=1024)
        
        from src.utils.json_utils import parse_json_from_response
        try:
            entities = parse_json_from_response(response)
            logger.info(f"提取到 {len(entities.get('characters', []))} 个角色，{len(entities.get('locations', []))} 个地点，{len(entities.get('items', []))} 个物品")
            return entities
        except Exception as e:
            logger.warning(f"实体提取失败: {e}")
            return {"characters": [], "locations": [], "items": []}

    def _update_rag(self, novel_name: str, chapter_content: str, entities: Dict[str, Any], chapter_num: int) -> None:
        """
        Step 2: RAG 更新
        将章节内容和实体信息存入 ChromaDB
        """
        try:
            project_root = Path(__file__).parent.parent.parent.parent
            chroma_db_path = project_root / "data" / "chroma_db" / novel_name
            chroma_db_path.mkdir(parents=True, exist_ok=True)
            
            import re
            safe_novel_name = re.sub(r'[^a-zA-Z0-9._-]', '_', novel_name)
            safe_novel_name = safe_novel_name.strip('_')
            
            if not safe_novel_name or len(safe_novel_name) < 3:
                novel_hash = abs(hash(novel_name)) % 100000
                safe_novel_name = f"novel_{novel_hash}"
            
            if not re.match(r'^[a-zA-Z0-9]', safe_novel_name):
                safe_novel_name = f"n_{safe_novel_name}"
            
            if not re.match(r'[a-zA-Z0-9]$', safe_novel_name):
                safe_novel_name = f"{safe_novel_name}x"
            
            collection_name = f"{safe_novel_name}_chapters"
            if len(collection_name) < 3:
                novel_hash = abs(hash(novel_name)) % 100000
                collection_name = f"novel_{novel_hash}_chapters"
            
            indexer = VectorIndexer(chroma_db_path, collection_name=collection_name)
            
            metadata = {
                "novel_name": novel_name,
                "chapter_num": chapter_num,
                "entities": json.dumps(entities, ensure_ascii=False)
            }
            
            indexer.index_text(chapter_content, metadata=metadata, batch_size=64)
            logger.info(f"章节 {chapter_num} 已索引到 RAG")
        except Exception as e:
            logger.error(f"RAG 更新失败: {e}", exc_info=True)

    def _update_rolling_summary(self, novel_name: str, chapter_num: int, chapter_content: str) -> str:
        """
        Step 3: 摘要更新
        更新最近 5 章的精简摘要
        """
        try:
            novel = DatabaseService.get_novel_by_title(novel_name)
            if not novel:
                return ""
            
            chapters = DatabaseService.list_chapters(novel.id)
            recent_chapters = sorted([ch.index for ch in chapters if ch.index <= chapter_num], reverse=True)[:5]
            
            if not recent_chapters:
                return ""
            
            contents = DatabaseService.get_chapters_content_batch(novel.id, recent_chapters)
            
            summaries = []
            for ch_num in reversed(recent_chapters):
                try:
                    content = contents.get(ch_num)
                    if content:
                        summary = self._generate_chapter_summary(content, ch_num)
                        summaries.append(f"第{ch_num}章：{summary}")
                except Exception as e:
                    logger.warning(f"加载第{ch_num}章摘要失败: {e}")
            
            rolling_summary = "\n".join(summaries)
            
            self.state_manager.redis_client.set(
                f"novel:{novel_name}:rolling_summary",
                rolling_summary
            )
            
            return rolling_summary
        except Exception as e:
            logger.error(f"摘要更新失败: {e}")
            return ""

    def _generate_chapter_summary(self, content: str, chapter_num: int) -> str:
        """生成章节摘要（100字以内）"""
        if len(content) < 200:
            return content[:100]
        
        summary_prompt = f"""
请用一句话（50字以内）概括以下章节的主要内容：

{content[:1000]}

只返回概括文字，不要其他内容。
"""

        messages = [
            {"role": "system", "content": "You are a professional summarizer. Summarize chapter content in one sentence (within 50 Chinese characters)."},
            {"role": "user", "content": summary_prompt}
        ]

        try:
            response = self.llm_client.chat(messages, temperature=0.3, max_tokens=128)
            return response.strip()[:100]
        except Exception as e:
            logger.warning(f"摘要生成失败: {e}")
            return content[:100]

    def _get_source(self) -> EventSource:
        return EventSource.AGENT_KNOWLEDGE

    def _get_completion_event_type(self) -> EventType:
        return EventType.KNOWLEDGE_UPDATED
