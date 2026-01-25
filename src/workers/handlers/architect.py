import json
import logging
from typing import Dict, Any
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager
from src.utils.json_utils import parse_json_from_response
from src.core.db_service import DatabaseService
from src.core.prompt_loader import get_fiction_system_prompt

logger = logging.getLogger(__name__)


class ArchitectHandler(BaseAgentHandler):
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
            else:
                global_dir = self.file_manager.get_global_settings_path(novel_name)
                bios_path = global_dir / "bios.json"
                world_path = global_dir / "world.md"
                
                bios = self.file_manager.load_content(bios_path) if bios_path.exists() else []
                world = self.file_manager.load_content(world_path) if world_path.exists() else ""
                
                cache_service.set_novel_settings(novel_name, {"bios": bios, "world": world})
        except:
            global_dir = self.file_manager.get_global_settings_path(novel_name)
            bios_path = global_dir / "bios.json"
            world_path = global_dir / "world.md"
            
            bios = self.file_manager.load_content(bios_path) if bios_path.exists() else []
            world = self.file_manager.load_content(world_path) if world_path.exists() else ""
        
        character_bios_text = self._format_bios(bios)
        world_setting_text = world if world else ""
        
        novel = DatabaseService.get_novel_by_title(novel_name)
        recent_content_text = ""
        if novel:
            chapters = DatabaseService.list_chapters(novel.id)
            previous_chapters = sorted([ch.index for ch in chapters if ch.index < chapter_num], reverse=True)
            
            if previous_chapters:
                try:
                    content = DatabaseService.get_chapter_content(novel.id, previous_chapters[0])
                    if content:
                        recent_content_text = content[:500]
                except Exception as e:
                    logger.warning(f"加载上一章前500字失败: {e}")
        
        reference_context = f"# 核心指令\n{get_fiction_system_prompt()}\n\n"
        reference_context += f"# 世界观与人物\n## 人物设定：\n{character_bios_text}\n\n## 世界观设定：\n{world_setting_text}\n\n"
        
        if recent_content_text:
            reference_context += f"# 上一章前500字\n{recent_content_text}\n\n"
        
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
        state = self.state_manager.get_state(workflow_id)
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        reference_context = self._build_context(novel_name, chapter_num)
        
        self.state_manager.update_state(workflow_id, {"reference_context": reference_context})

        outline_prompt = f"""
{reference_context}

---
【任务目标】
请规划第 {chapter_num} 章的详细大纲，目标总字数 10000 字。
请将本章拆分为 4 到 6 个具体的场景 (Scenes)。

【输出格式】
请仅返回一个 JSON 对象，格式如下：
{{
    "scenes": [
        {{
            "id": 1,
            "summary": "详细描述该场景发生的事件、冲突和对话重点...",
            "expected_words": 2000,
            "key_characters": ["姓名1", "姓名2"]
        }},
        ...
    ]
}}
"""

        system_prompt = (
            get_fiction_system_prompt() + "\n\n" +
            "你是一位专业的小说创作助手，擅长创作符合原著风格的小说章节。\n\n"
            "**重要格式要求**：\n"
            "- 必须返回严格的 JSON 格式\n"
            "- 包含 scenes 数组，每个场景包含 id, summary, expected_words, key_characters\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": outline_prompt}
        ]

        response = self.llm_client.chat(messages, temperature=0.7, max_tokens=4096)
        
        from src.utils.json_utils import parse_json_from_response
        try:
            outline_json = parse_json_from_response(response)
            if not outline_json or "scenes" not in outline_json:
                raise ValueError("大纲生成失败，模型未返回有效的 JSON Scenes")
            outline = json.dumps(outline_json, ensure_ascii=False)
        except Exception as e:
            logger.error(f"解析场景大纲失败: {e}")
            raise ValueError(f"场景大纲解析失败: {e}")
        
        novel = DatabaseService.get_or_create_novel(novel_name)
        DatabaseService.save_outline(novel.id, chapter_num, outline)

        return {"outline": outline}

    def _get_source(self) -> EventSource:
        return EventSource.AGENT_ARCHITECT

    def _get_completion_event_type(self) -> EventType:
        return EventType.OUTLINE_GENERATED
