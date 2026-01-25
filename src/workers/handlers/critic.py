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
from src.core.prompt_loader import get_fiction_system_prompt

logger = logging.getLogger(__name__)


class CriticHandler(BaseAgentHandler):
    def __init__(self, state_manager, dispatcher, llm_client: LLMClient, file_manager: ProjectManager):
        super().__init__(state_manager, dispatcher)
        self.llm_client = llm_client
        self.file_manager = file_manager

    def _build_context(self, novel_name: str, chapter_num: int) -> str:
        try:
            from src.core.container import container
            cache_service = container.cache_service()
            cached_settings = cache_service.get_novel_settings(novel_name)
            
            if cached_settings:
                bios = cached_settings.get("bios", [])
                world = cached_settings.get("world", "")
                story_summary = cached_settings.get("story_summary", "")
            else:
                global_dir = self.file_manager.get_global_settings_path(novel_name)
                bios_path = global_dir / "bios.json"
                world_path = global_dir / "world.md"
                story_summary_path = global_dir / "story_summary.md"
                
                bios = self.file_manager.load_content(bios_path) if bios_path.exists() else []
                world = self.file_manager.load_content(world_path) if world_path.exists() else ""
                story_summary = self.file_manager.load_content(story_summary_path) if story_summary_path.exists() else ""
                
                cache_service.set_novel_settings(novel_name, {"bios": bios, "world": world, "story_summary": story_summary})
        except:
            global_dir = self.file_manager.get_global_settings_path(novel_name)
            bios_path = global_dir / "bios.json"
            world_path = global_dir / "world.md"
            story_summary_path = global_dir / "story_summary.md"
            
            bios = self.file_manager.load_content(bios_path) if bios_path.exists() else []
            world = self.file_manager.load_content(world_path) if world_path.exists() else ""
            story_summary = self.file_manager.load_content(story_summary_path) if story_summary_path.exists() else ""
        
        character_bios_text = self._format_bios(bios)
        world_setting_text = world if world else ""
        
        novel = DatabaseService.get_novel_by_title(novel_name)
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
        
        draft_content = DatabaseService.get_chapter_content(novel.id, chapter_num)
        if not draft_content:
            raise FileNotFoundError(f"章节内容不存在: {novel_name} 第{chapter_num}章")

        critique_prompt = f"""
{reference_context}

---
【审稿任务】
你是一位严厉的文学编辑，需要对第 {chapter_num} 章的正文进行专业审稿。

**本章大纲**：
{outline}

**待审稿正文**：
{draft_content}

【审稿维度】
请从以下四个维度严格评分（每项 0-25 分，总分 100 分）：

1. **剧情逻辑 (Logic)**: 情节是否合理、前后是否连贯、是否有逻辑漏洞
2. **人设一致性 (Character)**: 角色行为是否符合设定、性格是否一致
3. **文笔流畅度 (Style)**: 文字是否流畅、描写是否生动、对话是否自然
4. **大纲符合度 (Compliance)**: 是否按照大纲推进、是否偏离主线

【输出格式】
请**必须**返回严格的 JSON 格式，格式如下：
{{
  "score": 85,
  "critique": "整体不错，但主角的心理描写不够深入，战斗场面缺乏紧张感。",
  "suggestions": "在战斗结束后增加一段主角内心的恐惧描写，让读者更能感受到生死关头的紧张。",
  "passed": true,
  "details": {{
    "logic": 22,
    "character": 20,
    "style": 21,
    "compliance": 22
  }}
}}

**重要**：
- `score` 必须是 0-100 的整数
- `passed` 为 true 当且仅当 `score >= 75`
- `critique` 是总体评价（200字以内）
- `suggestions` 是具体修改建议（100字以内）
- `details` 是四个维度的详细分数（每项 0-25）
"""

        messages = [
            {"role": "system", "content": get_fiction_system_prompt() + "\n\n你是一位专业的文学编辑，擅长发现文本中的问题并提供建设性意见。必须返回严格的 JSON 格式。"},
            {"role": "user", "content": critique_prompt}
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
            
            DatabaseService.save_content(novel.id, chapter_num, draft_content, critique_data=critique_data)
            
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
