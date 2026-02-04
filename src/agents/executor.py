"""
Executor Agent - RAG-powered Generation Engine

Responsibilities:
1. Query rewrite (optional disambiguation)
2. Hybrid retrieval (vector + graph)
3. Cross-encoder reranking (offloaded to Celery in production)
4. Context-aware generation

This is the "brain's execution layer" - it retrieves knowledge and generates output.
"""

import json
import logging
import yaml
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from src.agents.base_agent import BaseAgent, AgentConfig, AgentError
from src.core.llm import LLMClient
from src.core.prompt_loader import resolve_prompt, format_prompt_template
from src.core.db_service import DatabaseService

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Result from retrieval"""
    documents: List[Dict[str, Any]]
    source: str  # "vector", "graph", "hybrid"
    metadata: Dict[str, Any]


class Executor(BaseAgent):
    """
    Executor Agent - RAG-powered generation with configurable retrieval.

    Usage:
        executor = Executor(config, llm_client)
        result = await executor.process({
            "query": "Generate chapter 1",
            "context": {...},  # Pre-built context
            "workflow_type": "generate_chapter",
            "retrieval_config": {...}  # Optional retrieval settings
        })

    Output:
        {
            "generated_content": str,
            "retrieval_metadata": Dict
        }
    """

    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """
        Initialize Executor.

        Args:
            config: Agent configuration with retrieval settings
            llm_client: LLM client for generation
        """
        super().__init__(config)
        self.llm_client = llm_client

        # Load retrieval configuration
        self.retrieval_enabled = self.get_config_value("retrieval_enabled", False)
        self.rerank_enabled = self.get_config_value("rerank_enabled", False)

    async def rewrite_query(
        self,
        query: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Rewrite query to be more explicit (remove ambiguity).

        Args:
            query: Original query
            context: Context data

        Returns:
            Rewritten query
        """
        # For now, simple pass-through
        # In production, this would use LLM to disambiguate
        self.log_info("Query rewrite: pass-through (not implemented)")
        return query

    async def retrieve(
        self,
        query: str,
        retrieval_config: Optional[Dict[str, Any]] = None
    ) -> RetrievalResult:
        """
        Retrieve relevant documents using configured strategy.

        Args:
            query: Search query
            retrieval_config: Optional retrieval configuration override

        Returns:
            RetrievalResult with documents
        """
        if not self.retrieval_enabled:
            self.log_info("Retrieval disabled, returning empty result")
            return RetrievalResult(
                documents=[],
                source="none",
                metadata={}
            )

        # Placeholder for hybrid retrieval
        # In production, this would call vector DB + graph DB
        self.log_info(f"Retrieving for query: {query[:50]}...")

        # Stub: Return empty result
        # TODO: Implement hybrid retrieval in Phase 2
        return RetrievalResult(
            documents=[],
            source="stub",
            metadata={"note": "Retrieval not yet implemented"}
        )

    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents using cross-encoder.

        In production, this offloads to Celery for heavy computation.

        Args:
            query: Search query
            documents: Retrieved documents

        Returns:
            Reranked documents
        """
        if not self.rerank_enabled or not documents:
            return documents

        self.log_info(f"Reranking {len(documents)} documents...")

        # Stub: Return documents as-is
        # TODO: Implement Celery-based reranking in Phase 2
        return documents

    async def generate(
        self,
        query: str,
        context: str,
        documents: List[Dict[str, Any]],
        workflow_type: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate content using LLM with context and retrieved documents.

        Args:
            query: Generation query
            context: Pre-built context string
            documents: Retrieved/reranked documents
            workflow_type: Optional workflow type for prompt selection
            **kwargs: Additional parameters for prompt formatting

        Returns:
            Generated content
        """
        try:
            # Load generation prompt
            prompt_raw = resolve_prompt("executor_generation", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw)

            system_prompt = prompt_data.get("system", "")
            user_template = prompt_data.get("user", "")

            # Format retrieved documents (if any)
            retrieved_context = ""
            if documents:
                retrieved_context = "\n\n# 检索增强上下文\n"
                for i, doc in enumerate(documents[:5], 1):  # Limit to top 5
                    content = doc.get("content", "")
                    retrieved_context += f"## 文档 {i}\n{content[:500]}\n\n"

            # Format user prompt
            user_prompt = format_prompt_template(
                user_template,
                query=query,
                context=context,
                retrieved_context=retrieved_context,
                **kwargs
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # Generate
            self.log_info("Generating content...")
            response = self.llm_client.chat(
                messages,
                temperature=kwargs.get("temperature", 0.7),
                max_tokens=kwargs.get("max_tokens", 4096)
            )

            return response

        except Exception as e:
            self.log_error(f"Generation failed: {e}")
            raise AgentError(
                self.get_agent_name(),
                f"Failed to generate content: {str(e)}"
            )

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process execution request.

        Input:
            {
                "query": str,  # Generation query
                "context": str,  # Pre-built context
                "workflow_type": Optional[str],
                "retrieval_config": Optional[Dict],  # Override retrieval settings
                "generation_params": Optional[Dict]  # Temperature, max_tokens, etc.
            }

        Output:
            {
                "generated_content": str,
                "retrieval_metadata": Dict
            }
        """
        self.validate_input(input_data, ["query", "context"])

        query = input_data["query"]
        context = input_data["context"]
        workflow_type = input_data.get("workflow_type")
        retrieval_config = input_data.get("retrieval_config")
        generation_params = input_data.get("generation_params", {})

        self.log_info(f"Executing query: {query[:50]}...")

        # Step 1: Query rewrite (optional)
        rewritten_query = await self.rewrite_query(query, input_data)

        # Step 2: Retrieve documents
        retrieval_result = await self.retrieve(rewritten_query, retrieval_config)

        # Step 3: Rerank documents
        ranked_docs = await self.rerank(rewritten_query, retrieval_result.documents)

        # Step 4: Generate
        generated_content = await self.generate(
            rewritten_query,
            context,
            ranked_docs,
            workflow_type,
            **generation_params
        )

        return {
            "generated_content": generated_content,
            "retrieval_metadata": {
                "source": retrieval_result.source,
                "doc_count": len(retrieval_result.documents),
                "reranked": self.rerank_enabled,
                **retrieval_result.metadata
            }
        }

    def get_agent_name(self) -> str:
        return "executor"


# Backward compatibility with legacy WriterHandler
class WriterHandler:
    """
    Legacy wrapper for Executor.

    Maintains compatibility with existing workflow code.
    Maps old writer behavior (scene-by-scene generation) to new Executor pattern.
    """

    def __init__(self, state_manager, dispatcher, llm_client: LLMClient, file_manager=None):
        self.state_manager = state_manager
        self.dispatcher = dispatcher
        self.llm_client = llm_client
        self.file_manager = file_manager

        # Create Executor with minimal config
        config = AgentConfig(
            scenario_name="novel",
            agent_name="executor",
            config_data={
                "retrieval_enabled": False,  # Disabled for now
                "rerank_enabled": False
            }
        )
        self.executor = Executor(config, llm_client)

    async def generate_content(
        self,
        novel_name: str,
        chapter_num: int,
        outline: str,
        reference_context: str,
        feedback: Optional[str] = None,
        workflow_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate chapter content scene by scene.

        Args:
            novel_name: Novel title
            chapter_num: Chapter number
            outline: JSON string of scenes
            reference_context: Pre-built context
            feedback: Optional revision feedback
            workflow_type: Optional workflow type

        Returns:
            {"content": str}  # Full chapter content
        """
        try:
            # Parse outline
            if isinstance(outline, dict):
                scenes = outline.get("scenes", [])
            elif isinstance(outline, str):
                outline_dict = json.loads(outline)
                scenes = outline_dict.get("scenes", [])
            else:
                raise ValueError("Invalid outline format")

            if not scenes:
                raise ValueError("No scenes in outline")

            # Check for hybrid retrieval support
            novel = DatabaseService.get_novel_by_title(novel_name)
            extra_context = ""
            try:
                from src.rag.hybrid import hybrid_retrieve
                query = outline[:500] if isinstance(outline, str) else str(outline)[:500]

                # Extract character names from outline
                entity_hint = []
                if isinstance(outline, str):
                    try:
                        o = json.loads(outline)
                        for sc in o.get("scenes", []):
                            for c in sc.get("key_characters", []):
                                if isinstance(c, str) and c.strip():
                                    entity_hint.append(c.strip())
                    except:
                        pass

                extra = hybrid_retrieve(
                    novel.id,
                    novel_name,
                    query,
                    top_k=5,
                    entity_hint=entity_hint or None
                )
                if extra:
                    extra_context = "\n\n" + extra
            except Exception as e:
                logger.debug(f"Hybrid retrieval skipped: {e}")

            # Enhance reference context
            if extra_context:
                reference_context = reference_context + extra_context

            # Load existing content for rewrite mode
            novel = DatabaseService.get_novel_by_title(novel_name)
            existing_content = DatabaseService.get_chapter_content(novel.id, chapter_num)
            rewrite_mode = feedback is not None

            scene_contents = []
            if rewrite_mode and existing_content:
                scene_contents = self._split_scenes(existing_content, len(scenes))
            else:
                scene_contents = [None] * len(scenes)

            # Generate scene by scene
            previous_text = "（章节开始）"
            full_content = []

            from src.core.prompt_loader import get_fiction_system_prompt

            for i, scene in enumerate(scenes):
                # Skip if already have content in rewrite mode
                if rewrite_mode and scene_contents[i]:
                    previous_text = scene_contents[i]
                    full_content.append(scene_contents[i])
                    continue

                logger.info(f"Writing scene {scene['id']}: {scene['summary'][:30]}...")

                feedback_section = (
                    f"\n\n【重要】请根据以下审稿意见调整写作：\n{feedback}\n"
                    if feedback else ""
                )

                # Load writer prompt
                prompt_raw = resolve_prompt("writer_builder", workflow_type=workflow_type)
                prompt_data = yaml.safe_load(prompt_raw)
                user_template = prompt_data.get("user", "")

                builder_prompt = format_prompt_template(
                    user_template,
                    reference_context=reference_context,
                    chapter_num=chapter_num,
                    scene_id=scene["id"],
                    scene_summary=scene["summary"],
                    key_characters=", ".join(scene.get("key_characters", [])),
                    expected_words=scene.get("expected_words", 2000),
                    previous_text=previous_text[-2000:],
                    feedback_section=feedback_section,
                )

                messages = [
                    {"role": "system", "content": get_fiction_system_prompt()},
                    {"role": "user", "content": builder_prompt}
                ]

                scene_content = self.llm_client.chat(messages)
                full_content.append(scene_content)
                previous_text = scene_content

            content = "\n\n".join(full_content)
            return {"content": content}

        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            raise ValueError(f"Failed to generate content: {str(e)}")

    def _split_scenes(self, content: str, scene_count: int) -> List[Optional[str]]:
        """Split existing content into scenes (rough heuristic)"""
        lines = content.split('\n')
        scenes = []
        current_scene = []

        for line in lines:
            current_scene.append(line)
            if len(current_scene) > 500:
                scenes.append('\n'.join(current_scene))
                current_scene = []

        if current_scene:
            scenes.append('\n'.join(current_scene))

        while len(scenes) < scene_count:
            scenes.append(None)

        return scenes[:scene_count]
