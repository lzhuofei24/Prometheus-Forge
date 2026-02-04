"""
Novel Generation Scenario - Context Builder

Domain-specific logic for assembling novel writing context.
This module handles character bios, world settings, and previous chapter loading.

Extracted from src/agents/builder.py and src/workers/handlers/writer.py
as part of Phase 1 refactoring.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from src.core.db_service import DatabaseService
from src.core.prompt_loader import get_fiction_system_prompt

logger = logging.getLogger(__name__)


class NovelContextBuilder:
    """
    Builds rich context for novel chapter generation.

    Responsibilities:
    - Load character bios from database
    - Load world settings
    - Load previous chapters (full content and outlines)
    - Token limit management (smart truncation)
    - Format context for prompt injection
    """

    def __init__(self, max_tokens: int = 24000):
        """
        Initialize context builder.

        Args:
            max_tokens: Maximum token budget for context
        """
        self.max_tokens = max_tokens

    def build_context(
        self,
        novel_name: str,
        chapter_num: int,
        include_recent_content: bool = True,
        include_outlines: bool = True,
        max_recent_chapters: int = 3,
        max_outline_chapters: int = 15
    ) -> Dict[str, Any]:
        """
        Build comprehensive context for chapter generation.

        Args:
            novel_name: Novel title
            chapter_num: Current chapter number
            include_recent_content: Whether to include recent chapter full content
            include_outlines: Whether to include previous chapter outlines
            max_recent_chapters: Number of recent chapters to include (full content)
            max_outline_chapters: Number of chapter outlines to include

        Returns:
            {
                "reference_context": str,  # Formatted context string
                "character_bios": List[Dict],  # Raw character data
                "world_setting": str,  # World description
                "story_summary": str,  # Overall story summary
                "token_usage": Dict  # Token breakdown
            }
        """
        logger.info(f"Building context for {novel_name}, chapter {chapter_num}")

        # Load novel and global settings
        novel = DatabaseService.get_novel_by_title(novel_name)
        if not novel:
            raise ValueError(f"Novel not found: {novel_name}")

        settings = DatabaseService.get_novel_global_settings(novel.id)
        bios = settings.get("bios", [])
        world = settings.get("world", "")
        story_summary = settings.get("story_summary", "")

        # Format character bios
        character_bios_text = self._format_bios(bios)
        world_setting_text = world if world else ""

        # Build base context (always included)
        base_context = f"# 核心指令\n{get_fiction_system_prompt()}\n\n"
        base_context += f"# 世界观与人物\n## 人物设定：\n{character_bios_text}\n\n"
        base_context += f"## 世界观设定：\n{world_setting_text}\n\n"

        if story_summary:
            base_context += f"# 全书剧情梗概 (The Story So Far)\n{story_summary}\n\n"

        base_tokens = self._estimate_tokens(base_context)
        logger.info(f"Base context: {base_tokens} tokens")

        # Load recent chapter content (optional)
        recent_content_text = ""
        content_tokens = 0

        if include_recent_content:
            recent_content_text = self._load_recent_chapters_content(
                novel.id,
                chapter_num,
                max_recent_chapters
            )
            if recent_content_text:
                content_tokens = self._estimate_tokens(recent_content_text)
                logger.info(f"Recent content: {content_tokens} tokens")

        # Load chapter outlines (optional, with token budget)
        outlines_text = ""
        outline_tokens = 0

        if include_outlines:
            available_tokens = self.max_tokens - base_tokens - content_tokens
            outlines_text, outline_tokens = self._load_chapter_outlines(
                novel.id,
                chapter_num,
                max_outline_chapters,
                available_tokens
            )
            logger.info(f"Outlines: {outline_tokens} tokens")

        # Assemble final context
        reference_context = base_context

        if outlines_text:
            reference_context += f"# 前序章节大纲\n{outlines_text}\n\n"

        if recent_content_text:
            reference_context += f"# 最近章节正文\n{recent_content_text}\n\n"

        total_tokens = base_tokens + content_tokens + outline_tokens

        logger.info(f"Total context: {total_tokens} tokens, {len(reference_context)} chars")

        return {
            "reference_context": reference_context,
            "character_bios": bios,
            "world_setting": world_setting_text,
            "story_summary": story_summary,
            "token_usage": {
                "base": base_tokens,
                "content": content_tokens,
                "outlines": outline_tokens,
                "total": total_tokens,
                "max": self.max_tokens
            }
        }

    def _format_bios(self, bios: List[Dict[str, Any]]) -> str:
        """
        Format character bios for prompt injection.

        Args:
            bios: List of character bio dictionaries

        Returns:
            Formatted bio text
        """
        if not bios:
            return "（暂无人物设定）"

        formatted = []
        for bio in bios:
            if isinstance(bio, dict):
                name = bio.get("name", "未知")
                personality = bio.get("personality", "")
                appearance = bio.get("appearance", "")
                background = bio.get("background", "")

                bio_text = f"- **{name}**"
                if personality:
                    bio_text += f"\n  - 性格：{personality}"
                if appearance:
                    bio_text += f"\n  - 外貌：{appearance}"
                if background:
                    bio_text += f"\n  - 背景：{background}"

                formatted.append(bio_text)

        return "\n".join(formatted)

    def _load_recent_chapters_content(
        self,
        novel_id: str,
        chapter_num: int,
        max_chapters: int = 3
    ) -> str:
        """
        Load recent chapter full content.

        Args:
            novel_id: Novel ID
            chapter_num: Current chapter number
            max_chapters: Maximum number of chapters to load

        Returns:
            Formatted recent content text
        """
        try:
            chapters = DatabaseService.list_chapters(novel_id)
            previous_chapters = sorted(
                [ch.index for ch in chapters if ch.index < chapter_num],
                reverse=True
            )[:max_chapters]

            if not previous_chapters:
                return ""

            # Load content in chronological order
            contents = DatabaseService.get_chapters_content_batch(novel_id, previous_chapters)
            recent_chapters_content = []

            for ch_num in reversed(previous_chapters):
                content = contents.get(ch_num)
                if content:
                    recent_chapters_content.append(
                        f"## 第{ch_num}章完整正文\n\n{content}\n\n"
                    )

            return "\n\n---\n\n".join(recent_chapters_content)

        except Exception as e:
            logger.warning(f"Failed to load recent chapters content: {e}")
            return ""

    def _load_chapter_outlines(
        self,
        novel_id: str,
        chapter_num: int,
        max_chapters: int,
        available_tokens: int
    ) -> tuple:
        """
        Load chapter outlines with token budget management.

        Args:
            novel_id: Novel ID
            chapter_num: Current chapter number
            max_chapters: Maximum number of outlines to consider
            available_tokens: Token budget for outlines

        Returns:
            (outlines_text, token_count)
        """
        try:
            chapters = DatabaseService.list_chapters(novel_id)
            previous_chapters = sorted(
                [ch.index for ch in chapters if ch.index < chapter_num],
                reverse=True
            )[3:3+max_chapters]  # Skip most recent 3 (already have full content)

            if not previous_chapters:
                return "", 0

            # Load outlines
            outlines_data = []
            for ch_num in reversed(previous_chapters):
                try:
                    outline = DatabaseService.get_chapter_outline(novel_id, ch_num)
                    if outline:
                        outline_text = f"### 第{ch_num}章大纲\n{outline}\n"
                        outlines_data.append((ch_num, outline_text))
                except Exception as e:
                    logger.warning(f"Failed to load outline for chapter {ch_num}: {e}")

            # Select outlines within token budget
            selected_outlines = []
            selected_chapters = []
            current_tokens = 0

            for ch_num, outline_text in outlines_data:
                outline_tokens = self._estimate_tokens(outline_text)
                if current_tokens + outline_tokens <= available_tokens:
                    selected_outlines.append(outline_text)
                    selected_chapters.append(ch_num)
                    current_tokens += outline_tokens
                else:
                    break  # Stop adding outlines

            outlines_text = "\n".join(selected_outlines)
            logger.info(f"Selected {len(selected_outlines)} outlines, {current_tokens} tokens")

            return outlines_text, current_tokens

        except Exception as e:
            logger.warning(f"Failed to load chapter outlines: {e}")
            return "", 0

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses heuristic: Chinese ~1.5 chars/token, English ~4 chars/token

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    def build_simple_context(self, novel_name: str, chapter_num: int) -> str:
        """
        Build minimal context (for backward compatibility).

        Args:
            novel_name: Novel title
            chapter_num: Chapter number

        Returns:
            Simple reference context string
        """
        novel = DatabaseService.get_novel_by_title(novel_name)
        if not novel:
            return ""

        settings = DatabaseService.get_novel_global_settings(novel.id)
        bios = settings.get("bios", [])
        world = settings.get("world", "")

        character_bios_text = self._format_bios(bios)
        world_setting_text = world if world else ""

        # Load previous chapter outline only
        previous_outline = ""
        try:
            chapters = DatabaseService.list_chapters(novel.id)
            previous_chapters = sorted(
                [ch.index for ch in chapters if ch.index < chapter_num],
                reverse=True
            )
            if previous_chapters:
                previous_outline = DatabaseService.get_chapter_outline(
                    novel.id, previous_chapters[0]
                ) or ""
        except Exception as e:
            logger.warning(f"Failed to load previous outline: {e}")

        reference_context = f"# 核心指令\n{get_fiction_system_prompt()}\n\n"
        reference_context += f"# 世界观与人物\n## 人物设定：\n{character_bios_text}\n\n"
        reference_context += f"## 世界观设定：\n{world_setting_text}\n\n"

        if previous_outline:
            reference_context += f"# 上一章大纲\n{previous_outline}\n\n"

        return reference_context
