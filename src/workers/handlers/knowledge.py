import logging
import json
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager
from src.rag.indexer import VectorIndexer
from src.core.db_service import DatabaseService
from src.core.prompt_loader import resolve_prompt, format_prompt_template

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
        
        workflow_type = state.get("workflow_type")
        entities = self._extract_entities(chapter_content, novel_name, chapter_num, workflow_type=workflow_type)
        triplets = self._extract_triplets(chapter_content, novel_name, chapter_num, workflow_type=workflow_type)
        novel = DatabaseService.get_novel_by_title(novel_name)
        novel_id = novel.id if novel else novel_name
        self._update_graph_store(novel_id, triplets, chapter_num=chapter_num)
        self._update_rag(novel_name, chapter_content, entities, chapter_num)
        
        rolling_summary = self._update_rolling_summary(novel_name, chapter_num, chapter_content, workflow_type=workflow_type)
        
        return {
            "entities_extracted": len(entities.get("characters", [])) + len(entities.get("locations", [])) + len(entities.get("items", [])),
            "rolling_summary": rolling_summary,
            "chapter_indexed": chapter_num
        }

    def _extract_triplets(
        self,
        chapter_content: str,
        novel_name: str,
        chapter_num: int,
        workflow_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """调用 LLM 从文本中抽取 (Entity, Relation, Entity) 三元组，支持 subject_type/object_type 用于图谱节点着色。"""
        try:
            prompt_raw = resolve_prompt("knowledge_extraction", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw) or {}
            # 优先使用 triplet 专用 prompt（含类型、稠密度、动作完整性）
            sys_text = prompt_data.get("triplet_system") or prompt_data.get("system") or ""
            user_tpl = prompt_data.get("triplet_user") or "从以下章节中仅抽取「实体-关系-实体」三元组。\n\n章节内容：\n{chapter_content}"
            user_prompt = format_prompt_template(user_tpl, chapter_content=chapter_content[:2000], chapter_index=chapter_num)
            out_fmt = (
                '\n\n输出 JSON 数组，每项含 subject, subject_type, relation, object, object_type。'
                'subject_type/object_type 取 Person|Item|Concept|Location 之一。'
                '格式示例：[{"subject":"林未","subject_type":"Person","relation":"拥有","object":"基础心法","object_type":"Item"},...]'
            )
            if "subject_type" not in sys_text and "object_type" not in sys_text:
                sys_text += out_fmt
            messages = [
                {"role": "system", "content": sys_text},
                {"role": "user", "content": user_prompt},
            ]
            response = self.llm_client.chat(messages, temperature=0.2, max_tokens=1536)
            from src.utils.json_utils import parse_json_from_response
            raw = parse_json_from_response(response)
            if isinstance(raw, list):
                return [x for x in raw if isinstance(x, dict) and x.get("subject") and x.get("object")]
            if isinstance(raw, dict) and "triplets" in raw:
                return [x for x in (raw.get("triplets") or []) if isinstance(x, dict) and x.get("subject") and x.get("object")]
            return []
        except Exception as e:
            logger.warning("三元组抽取失败: %s", e)
            return []

    def _update_graph_store(self, novel_id: str, triplets: List[Dict[str, Any]], chapter_num: int = 0) -> None:
        """将三元组写入 GraphStore 并持久化；支持节点 type/status/description、边属性 chapter/location/state/quote/context。"""
        if not triplets:
            return
        try:
            from src.rag.graph_store import NetworkXGraphStore
            from src.core.config import GRAPH_STORE_BASE
            store = NetworkXGraphStore(persist_path=str(GRAPH_STORE_BASE), novel_id=novel_id)
            store.load()
            allowed_types = ("person", "item", "concept", "location", "organization", "event")
            for t in triplets:
                s, r, o = str(t.get("subject", "")).strip(), str(t.get("relation", "相关")).strip(), str(t.get("object", "")).strip()
                if not s or not o:
                    continue
                st_raw = (str(t.get("subject_type") or "").strip())[:20]
                ot_raw = (str(t.get("object_type") or "").strip())[:20]
                st = st_raw.capitalize() if st_raw.lower() in allowed_types else ""
                ot = ot_raw.capitalize() if ot_raw.lower() in allowed_types else ""
                subj_meta = {}
                if st:
                    subj_meta["type"] = st
                for key, attr in (("subject_status", "status"), ("subject_description", "description")):
                    v = t.get(key)
                    if isinstance(v, str) and v.strip():
                        subj_meta[attr] = v.strip()[:200]
                obj_meta = {}
                if ot:
                    obj_meta["type"] = ot
                for key, attr in (("object_status", "status"), ("object_description", "description")):
                    v = t.get(key)
                    if isinstance(v, str) and v.strip():
                        obj_meta[attr] = v.strip()[:200]
                edge_meta = {"chapter": chapter_num}
                for k in ("location", "state", "quote", "context"):
                    v = t.get(k)
                    if isinstance(v, str) and v.strip():
                        edge_meta[k] = v.strip()[:300]
                meta = {}
                if subj_meta:
                    meta["subj_meta"] = subj_meta
                if obj_meta:
                    meta["obj_meta"] = obj_meta
                meta["edge_meta"] = edge_meta
                store.upsert_triplet(s, r or "相关", o, meta=meta)
            store.save()
            logger.info("GraphStore 已更新 %d 条三元组", len(triplets))
        except Exception as e:
            logger.warning("GraphStore 更新失败: %s", e)

    def update_graph_for_chapter(
        self,
        novel_id: str,
        novel_name: str,
        chapter_content: str,
        chapter_num: int,
        workflow_type: Optional[str] = None,
    ) -> int:
        """仅做三元组抽取并写入图谱，供「添加索引」等手动入口调用。返回写入的三元组数量。"""
        triplets = self._extract_triplets(chapter_content, novel_name, chapter_num, workflow_type=workflow_type)
        self._update_graph_store(novel_id, triplets, chapter_num=chapter_num)
        return len(triplets)

    def _extract_entities(
        self,
        chapter_content: str,
        novel_name: str,
        chapter_num: int,
        workflow_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Step 1: 实体提取
        调用 LLM 提取本章出现的关键信息
        """
        prompt_raw = resolve_prompt("knowledge_extraction", workflow_type=workflow_type)
        prompt_data = yaml.safe_load(prompt_raw)
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        user_prompt = format_prompt_template(user_template, chapter_content=chapter_content[:2000])

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
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
        将章节内容和实体信息存入 ChromaDB，path/collection 与 index_ops 一致。
        """
        try:
            from src.rag import index_ops
            chroma_path, cn = index_ops.get_chroma_path_and_collection_name(novel_name)
            chroma_path.mkdir(parents=True, exist_ok=True)
            indexer = VectorIndexer(chroma_path, collection_name=cn)
            metadata = {
                "novel_name": index_ops._normalize_novel_name(novel_name),
                "chapter_num": chapter_num,
                "entities": json.dumps(entities, ensure_ascii=False),
            }
            indexer.index_text(chapter_content, metadata=metadata, batch_size=64)
            logger.info(f"章节 {chapter_num} 已索引到 RAG")
        except Exception as e:
            logger.error(f"RAG 更新失败: {e}", exc_info=True)

    def _update_rolling_summary(
        self,
        novel_name: str,
        chapter_num: int,
        chapter_content: str,
        workflow_type: Optional[str] = None,
    ) -> str:
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
                        summary = self._generate_chapter_summary(content, ch_num, workflow_type=workflow_type)
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

    def _generate_chapter_summary(
        self, content: str, chapter_num: int, workflow_type: Optional[str] = None
    ) -> str:
        """生成章节摘要（100字以内）"""
        if len(content) < 200:
            return content[:100]
        
        prompt_raw = resolve_prompt("knowledge_summary", workflow_type=workflow_type)
        prompt_data = yaml.safe_load(prompt_raw)
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        user_prompt = format_prompt_template(user_template, content=content[:1000])

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
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
