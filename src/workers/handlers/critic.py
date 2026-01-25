import json
import logging
from typing import Dict, Any
from pathlib import Path
import yaml
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource, EventPayload, AuditLogEntry
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager
from src.core.db_service import DatabaseService
from src.core.prompt_loader import get_fiction_system_prompt, resolve_prompt

logger = logging.getLogger(__name__)


class CriticHandler(BaseAgentHandler):
    def __init__(self, state_manager, dispatcher, llm_client: LLMClient, file_manager: ProjectManager):
        super().__init__(state_manager, dispatcher)
        self.llm_client = llm_client
        self.file_manager = file_manager

    def _build_context(self, novel_name: str, chapter_num: int) -> str:
        novel = DatabaseService.get_novel_by_title(novel_name)
        if novel:
            settings = DatabaseService.get_novel_global_settings(novel.id)
            bios = settings.get("bios", [])
            world = settings.get("world", "")
            story_summary = settings.get("story_summary", "")
        else:
            bios, world, story_summary = [], "", ""
        character_bios_text = self._format_bios(bios)
        world_setting_text = world if world else ""
        recent_chapters_content = []
        if novel:
            chapters = DatabaseService.list_chapters(novel.id)
            previous_chapters = sorted([ch.index for ch in chapters if ch.index < chapter_num], reverse=True)[:5]
            
            if previous_chapters:
                contents = DatabaseService.get_chapters_content_batch(novel.id, previous_chapters)
                for ch_num in reversed(previous_chapters):
                    content = contents.get(ch_num)
                    if content:
                        recent_chapters_content.append(f"## 第{ch_num}章完整正文\n\n{content}\n\n")
        
        recent_content_text = "\n\n---\n\n".join(recent_chapters_content)
        
        reference_context = f"# 核心指令\n{get_fiction_system_prompt()}\n\n"
        reference_context += f"# 世界观与人物\n## 人物设定：\n{character_bios_text}\n\n## 世界观设定：\n{world_setting_text}\n\n"
        
        if story_summary:
            reference_context += f"# 全书剧情梗概 (The Story So Far)\n{story_summary}\n\n"
        
        if recent_content_text:
            reference_context += f"# 最近剧情 (Context Window)\n{recent_content_text}\n\n"
        
        return reference_context

    def _format_bios(self, bios):
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

    def _process(self, workflow_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        核心处理逻辑：严厉的文学编辑审稿
        
        检查维度：
        - 剧情逻辑 (Logic)
        - 人设一致性 (Character)
        - 文笔流畅度 (Style)
        - 大纲符合度 (Compliance)
        """
        state = self.state_manager.get_state(workflow_id)
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        outline = state.get("outline", "")
        reference_context = state.get("reference_context") or self._build_context(novel_name, chapter_num)

        novel = DatabaseService.get_novel_by_title(novel_name)
        if not novel:
            raise ValueError(f"小说不存在: {novel_name}")
        # 优先从 workflow state 取正文（writer 完成后 controller 会写入 state["content"]），否则从 DB 取
        draft_content = state.get("content") or state.get("draft_content") or DatabaseService.get_chapter_content(novel.id, chapter_num)
        if not draft_content:
            raise FileNotFoundError(f"章节内容不存在: {novel_name} 第{chapter_num}章（请先通过审批助手中的正文写入）")

        prompt_raw = resolve_prompt("critique_handler")
        prompt_data = yaml.safe_load(prompt_raw)
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        user_prompt = user_template.format(
            reference_context=reference_context,
            outline=outline,
            draft_content=draft_content,
            chapter_num=chapter_num,
        )

        messages = [
            {"role": "system", "content": get_fiction_system_prompt() + "\n\n" + system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = self.llm_client.chat(messages, temperature=0.3, max_tokens=2048)

        from src.utils.json_utils import parse_json_from_response
        try:
            critique_result = parse_json_from_response(response)
            
            score = int(critique_result.get("score", 0))
            passed = score >= 75
            if "passed" in critique_result:
                passed = bool(critique_result["passed"])
            
            critique_data = {
                "score": score,
                "advice": critique_result.get("suggestions", ""),
                "comments": critique_result.get("critique", ""),
                "passed": passed,
                "details": critique_result.get("details", {})
            }
            
            DatabaseService.add_pending_write(
                "content",
                novel.id,
                chapter_num,
                {"content": draft_content, "critique_data": critique_data},
                workflow_id=workflow_id,
                source_agent="critic",
            )
            
            return critique_data
        except Exception as e:
            logger.warning(f"Critique JSON解析失败: {e}，使用默认值")
            return {
                "score": 50,
                "advice": "请重新审视章节结构，确保情节连贯、人物饱满。",
                "comments": "审稿解析失败，请检查内容质量。",
                "passed": False,
                "details": {}
            }

    def _get_source(self) -> EventSource:
        return EventSource.AGENT_CRITIC

    def _get_completion_event_type(self) -> EventType:
        return EventType.CRITIQUE_COMPLETED
