import json
import logging
import yaml
from typing import Dict, Any
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager
from src.utils.json_utils import parse_json_from_response
from src.core.db_service import DatabaseService
from src.core.prompt_loader import get_fiction_system_prompt, resolve_prompt

logger = logging.getLogger(__name__)


class ArchitectHandler(BaseAgentHandler):
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
        else:
            bios, world = [], ""
        character_bios_text = self._format_bios(bios)
        world_setting_text = world if world else ""
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

        prompt_raw = resolve_prompt("architect")
        prompt_data = yaml.safe_load(prompt_raw)
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        user_prompt = user_template.format(
            reference_context=reference_context,
            chapter_num=chapter_num,
            feedback_section="",
        )

        messages = [
            {"role": "system", "content": get_fiction_system_prompt() + "\n\n" + system_prompt},
            {"role": "user", "content": user_prompt}
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
        DatabaseService.add_pending_write(
            "outline",
            novel.id,
            chapter_num,
            {"summary": outline},
            workflow_id=workflow_id,
            source_agent="architect",
        )

        return {"outline": outline}

    def _get_source(self) -> EventSource:
        return EventSource.AGENT_ARCHITECT

    def _get_completion_event_type(self) -> EventType:
        return EventType.OUTLINE_GENERATED
