"""
Knowledge Manager Agent - Async Memory Consolidation Engine

Responsibilities:
1. Extract entities and relationships from content
2. Update knowledge graph (graph memory)
3. Update vector database (semantic memory)
4. Generate rolling summaries for context

This agent is the "hippocampus" - it consolidates short-term memory into long-term storage.
Designed to run asynchronously (Fire-and-Forget) to avoid blocking user workflows.
"""

import json
import logging
import yaml
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from src.agents.base_agent import BaseAgent, AgentConfig, AgentError
from src.core.llm import LLMClient
from src.core.prompt_loader import resolve_prompt, format_prompt_template

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """Extracted entity"""
    name: str
    entity_type: str  # "Person", "Location", "Item", "Concept", etc.
    description: Optional[str] = None
    status: Optional[str] = None


@dataclass
class Triplet:
    """Knowledge graph triplet (subject-relation-object)"""
    subject: str
    subject_type: str
    relation: str
    object: str
    object_type: str
    metadata: Dict[str, Any]


class KnowledgeManager(BaseAgent):
    """
    Knowledge Manager Agent - Consolidates content into structured knowledge.

    Usage:
        manager = KnowledgeManager(config, llm_client)
        result = await manager.process({
            "content": "Chapter text...",
            "context": {...},  # Novel name, chapter number, etc.
            "workflow_type": "generate_chapter"
        })

    Output:
        {
            "entities_extracted": int,
            "triplets_extracted": int,
            "summary": str
        }
    """

    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """
        Initialize KnowledgeManager.

        Args:
            config: Agent configuration with entity types, etc.
            llm_client: LLM client for extraction
        """
        super().__init__(config)
        self.llm_client = llm_client

    async def extract_entities(
        self,
        content: str,
        workflow_type: Optional[str] = None
    ) -> List[Entity]:
        """
        Extract entities from content using LLM.

        Args:
            content: Text content to extract from
            workflow_type: Optional workflow type for prompt selection

        Returns:
            List of extracted entities
        """
        try:
            # Load entity extraction prompt
            prompt_raw = resolve_prompt("knowledge_extraction", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw)

            system_prompt = prompt_data.get("system", "")
            user_template = prompt_data.get("user", "")

            user_prompt = format_prompt_template(
                user_template,
                chapter_content=content[:2000]
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.llm_client.chat(messages, temperature=0.3, max_tokens=1024)

            # Parse entities
            from src.utils.json_utils import parse_json_from_response
            result = parse_json_from_response(response)

            entities = []

            # Parse different entity types
            for entity_type in ["characters", "locations", "items", "concepts"]:
                items = result.get(entity_type, [])
                for item in items:
                    if isinstance(item, dict):
                        entities.append(Entity(
                            name=item.get("name", "Unknown"),
                            entity_type=entity_type.rstrip('s').capitalize(),  # "characters" -> "Character"
                            description=item.get("description"),
                            status=item.get("status")
                        ))
                    elif isinstance(item, str):
                        entities.append(Entity(
                            name=item,
                            entity_type=entity_type.rstrip('s').capitalize()
                        ))

            self.log_info(f"Extracted {len(entities)} entities")
            return entities

        except Exception as e:
            self.log_warning(f"Entity extraction failed: {e}")
            return []

    async def extract_triplets(
        self,
        content: str,
        workflow_type: Optional[str] = None
    ) -> List[Triplet]:
        """
        Extract knowledge graph triplets from content.

        Args:
            content: Text content to extract from
            workflow_type: Optional workflow type for prompt selection

        Returns:
            List of extracted triplets
        """
        try:
            # Load triplet extraction prompt
            prompt_raw = resolve_prompt("knowledge_extraction", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw) or {}

            # Prefer triplet-specific prompts
            system_prompt = prompt_data.get("triplet_system") or prompt_data.get("system") or ""
            user_template = prompt_data.get("triplet_user") or "从以下内容中抽取实体-关系-实体三元组。\n\n内容：\n{chapter_content}"

            # Add format instruction if not present
            if "subject_type" not in system_prompt:
                system_prompt += (
                    '\n\n输出 JSON 数组，每项含 subject, subject_type, relation, object, object_type。'
                    'subject_type/object_type 取 Person|Item|Concept|Location 之一。'
                    '格式示例：[{"subject":"张三","subject_type":"Person","relation":"拥有","object":"宝剑","object_type":"Item"},...]'
                )

            user_prompt = format_prompt_template(
                user_template,
                chapter_content=content[:2000]
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.llm_client.chat(messages, temperature=0.2, max_tokens=1536)

            # Parse triplets
            from src.utils.json_utils import parse_json_from_response
            raw = parse_json_from_response(response)

            triplets = []

            # Handle different response formats
            if isinstance(raw, list):
                triplet_list = raw
            elif isinstance(raw, dict) and "triplets" in raw:
                triplet_list = raw.get("triplets", [])
            else:
                triplet_list = []

            # Parse and validate triplets
            for item in triplet_list:
                if not isinstance(item, dict):
                    continue

                subject = item.get("subject", "").strip()
                obj = item.get("object", "").strip()

                if not subject or not obj:
                    continue

                triplets.append(Triplet(
                    subject=subject,
                    subject_type=item.get("subject_type", "Concept").capitalize(),
                    relation=item.get("relation", "相关").strip(),
                    object=obj,
                    object_type=item.get("object_type", "Concept").capitalize(),
                    metadata={
                        "subject_description": item.get("subject_description"),
                        "subject_status": item.get("subject_status"),
                        "object_description": item.get("object_description"),
                        "object_status": item.get("object_status"),
                        "location": item.get("location"),
                        "state": item.get("state"),
                        "quote": item.get("quote"),
                        "context": item.get("context")
                    }
                ))

            self.log_info(f"Extracted {len(triplets)} triplets")
            return triplets

        except Exception as e:
            self.log_warning(f"Triplet extraction failed: {e}")
            return []

    async def update_graph_store(
        self,
        triplets: List[Triplet],
        context: Dict[str, Any]
    ) -> int:
        """
        Update knowledge graph with extracted triplets.

        This is a stub - actual implementation would write to Neo4j or similar.

        Args:
            triplets: Extracted triplets
            context: Context data (novel_id, chapter_num, etc.)

        Returns:
            Number of triplets written
        """
        if not triplets:
            return 0

        self.log_info(f"Updating graph store with {len(triplets)} triplets...")

        # Stub for graph store update
        # TODO: Implement Neo4j integration in Phase 2

        # For now, try to use NetworkXGraphStore if available
        try:
            novel_id = context.get("novel_id")
            chapter_num = context.get("chapter_num", 0)

            if not novel_id:
                self.log_warning("No novel_id in context, skipping graph store update")
                return 0

            from src.rag.graph_store import NetworkXGraphStore
            from src.core.config import GRAPH_STORE_BASE

            store = NetworkXGraphStore(persist_path=str(GRAPH_STORE_BASE), novel_id=novel_id)
            store.load()

            for triplet in triplets:
                subj_meta = {}
                if triplet.subject_type:
                    subj_meta["type"] = triplet.subject_type
                if triplet.metadata.get("subject_description"):
                    subj_meta["description"] = triplet.metadata["subject_description"][:200]
                if triplet.metadata.get("subject_status"):
                    subj_meta["status"] = triplet.metadata["subject_status"][:200]

                obj_meta = {}
                if triplet.object_type:
                    obj_meta["type"] = triplet.object_type
                if triplet.metadata.get("object_description"):
                    obj_meta["description"] = triplet.metadata["object_description"][:200]
                if triplet.metadata.get("object_status"):
                    obj_meta["status"] = triplet.metadata["object_status"][:200]

                edge_meta = {"chapter": chapter_num}
                for key in ["location", "state", "quote", "context"]:
                    value = triplet.metadata.get(key)
                    if value:
                        edge_meta[key] = str(value)[:300]

                meta = {
                    "subj_meta": subj_meta,
                    "obj_meta": obj_meta,
                    "edge_meta": edge_meta
                }

                store.upsert_triplet(
                    triplet.subject,
                    triplet.relation,
                    triplet.object,
                    meta=meta
                )

            store.save()
            self.log_info(f"Graph store updated with {len(triplets)} triplets")
            return len(triplets)

        except Exception as e:
            self.log_warning(f"Graph store update failed: {e}")
            return 0

    async def update_vector_store(
        self,
        content: str,
        entities: List[Entity],
        context: Dict[str, Any]
    ) -> bool:
        """
        Update vector database with content and entities.

        This is a stub - actual implementation would write to ChromaDB.

        Args:
            content: Text content to index
            entities: Extracted entities
            context: Context data (novel_name, chapter_num, etc.)

        Returns:
            Success flag
        """
        self.log_info(f"Updating vector store (content length: {len(content)})...")

        # Stub for vector store update
        # TODO: Implement ChromaDB integration in Phase 2

        # For now, try to use existing VectorIndexer if available
        try:
            novel_name = context.get("novel_name")
            chapter_num = context.get("chapter_num", 0)

            if not novel_name:
                self.log_warning("No novel_name in context, skipping vector store update")
                return False

            from src.rag import index_ops
            from src.rag.indexer import VectorIndexer

            chroma_path, collection_name = index_ops.get_chroma_path_and_collection_name(novel_name)
            chroma_path.mkdir(parents=True, exist_ok=True)

            indexer = VectorIndexer(chroma_path, collection_name=collection_name)

            metadata = {
                "novel_name": index_ops._normalize_novel_name(novel_name),
                "chapter_num": chapter_num,
                "entities": json.dumps(
                    [{"name": e.name, "type": e.entity_type} for e in entities],
                    ensure_ascii=False
                )
            }

            indexer.index_text(content, metadata=metadata, batch_size=64)
            self.log_info("Vector store updated successfully")
            return True

        except Exception as e:
            self.log_warning(f"Vector store update failed: {e}")
            return False

    async def generate_summary(
        self,
        content: str,
        workflow_type: Optional[str] = None
    ) -> str:
        """
        Generate concise summary of content.

        Args:
            content: Text content to summarize
            workflow_type: Optional workflow type for prompt selection

        Returns:
            Summary text
        """
        if len(content) < 200:
            return content[:100]

        try:
            # Load summary prompt
            prompt_raw = resolve_prompt("knowledge_summary", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw)

            system_prompt = prompt_data.get("system", "")
            user_template = prompt_data.get("user", "")

            user_prompt = format_prompt_template(
                user_template,
                content=content[:1000]
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.llm_client.chat(messages, temperature=0.3, max_tokens=128)
            return response.strip()[:100]

        except Exception as e:
            self.log_warning(f"Summary generation failed: {e}")
            return content[:100]

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process knowledge consolidation request.

        Input:
            {
                "content": str,  # Content to process
                "context": Dict,  # Context data (novel_id, chapter_num, etc.)
                "workflow_type": Optional[str]
            }

        Output:
            {
                "entities_extracted": int,
                "triplets_extracted": int,
                "graph_updated": int,
                "vector_updated": bool,
                "summary": str
            }
        """
        self.validate_input(input_data, ["content", "context"])

        content = input_data["content"]
        context = input_data["context"]
        workflow_type = input_data.get("workflow_type")

        self.log_info(f"Processing knowledge consolidation (content length: {len(content)})")

        # Step 1: Extract entities
        entities = await self.extract_entities(content, workflow_type)

        # Step 2: Extract triplets
        triplets = await self.extract_triplets(content, workflow_type)

        # Step 3: Update graph store
        triplets_written = await self.update_graph_store(triplets, context)

        # Step 4: Update vector store
        vector_updated = await self.update_vector_store(content, entities, context)

        # Step 5: Generate summary
        summary = await self.generate_summary(content, workflow_type)

        return {
            "entities_extracted": len(entities),
            "triplets_extracted": len(triplets),
            "graph_updated": triplets_written,
            "vector_updated": vector_updated,
            "summary": summary
        }

    def get_agent_name(self) -> str:
        return "knowledge_manager"


# Backward compatibility with legacy KnowledgeHandler
class KnowledgeHandler:
    """
    Legacy wrapper for KnowledgeManager.

    Maintains compatibility with existing workflow code.
    """

    def __init__(self, state_manager, dispatcher, llm_client: LLMClient, file_manager=None):
        self.state_manager = state_manager
        self.dispatcher = dispatcher
        self.llm_client = llm_client
        self.file_manager = file_manager

        # Create KnowledgeManager with minimal config
        config = AgentConfig(
            scenario_name="novel",
            agent_name="knowledge_manager",
            config_data={}
        )
        self.manager = KnowledgeManager(config, llm_client)

    async def update_knowledge(
        self,
        novel_name: str,
        novel_id: str,
        chapter_num: int,
        chapter_content: str,
        workflow_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update knowledge base with chapter content.

        Args:
            novel_name: Novel title
            novel_id: Novel ID
            chapter_num: Chapter number
            chapter_content: Chapter content
            workflow_type: Optional workflow type

        Returns:
            {
                "entities_extracted": int,
                "rolling_summary": str,
                "chapter_indexed": int
            }
        """
        try:
            result = await self.manager.process({
                "content": chapter_content,
                "context": {
                    "novel_name": novel_name,
                    "novel_id": novel_id,
                    "chapter_num": chapter_num
                },
                "workflow_type": workflow_type
            })

            # Update rolling summary in Redis (legacy behavior)
            try:
                rolling_summary = await self._update_rolling_summary(
                    novel_name,
                    novel_id,
                    chapter_num,
                    workflow_type
                )
            except Exception as e:
                logger.warning(f"Rolling summary update failed: {e}")
                rolling_summary = result.get("summary", "")

            return {
                "entities_extracted": result["entities_extracted"],
                "rolling_summary": rolling_summary,
                "chapter_indexed": chapter_num
            }

        except Exception as e:
            logger.error(f"Knowledge update failed: {e}")
            return {
                "entities_extracted": 0,
                "rolling_summary": "",
                "chapter_indexed": chapter_num
            }

    async def _update_rolling_summary(
        self,
        novel_name: str,
        novel_id: str,
        chapter_num: int,
        workflow_type: Optional[str]
    ) -> str:
        """Update rolling summary for last 5 chapters"""
        try:
            from src.core.db_service import DatabaseService

            chapters = DatabaseService.list_chapters(novel_id)
            recent_chapters = sorted(
                [ch.index for ch in chapters if ch.index <= chapter_num],
                reverse=True
            )[:5]

            if not recent_chapters:
                return ""

            contents = DatabaseService.get_chapters_content_batch(novel_id, recent_chapters)

            summaries = []
            for ch_num in reversed(recent_chapters):
                content = contents.get(ch_num)
                if content:
                    summary = await self.manager.generate_summary(content, workflow_type)
                    summaries.append(f"第{ch_num}章：{summary}")

            rolling_summary = "\n".join(summaries)

            # Store in Redis
            self.state_manager.redis_client.set(
                f"novel:{novel_name}:rolling_summary",
                rolling_summary
            )

            return rolling_summary

        except Exception as e:
            logger.warning(f"Rolling summary generation failed: {e}")
            return ""
