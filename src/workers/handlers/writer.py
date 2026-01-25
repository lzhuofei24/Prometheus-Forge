import json
import logging
from typing import Dict, Any, Optional
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager
from src.core.db_service import DatabaseService
import yaml
from src.core.prompt_loader import get_fiction_system_prompt, resolve_prompt, format_prompt_template

logger = logging.getLogger(__name__)


class WriterHandler(BaseAgentHandler):
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
        previous_outline = ""
        if novel:
            chapters = DatabaseService.list_chapters(novel.id)
            previous_chapters = sorted([ch.index for ch in chapters if ch.index < chapter_num], reverse=True)
            if previous_chapters:
                try:
                    previous_outline = DatabaseService.get_chapter_outline(novel.id, previous_chapters[0]) or ""
                except Exception as e:
                    logger.warning(f"加载上一章大纲失败: {e}")
        
        reference_context = f"# 核心指令\n{get_fiction_system_prompt()}\n\n"
        reference_context += f"# 世界观与人物\n## 人物设定：\n{character_bios_text}\n\n## 世界观设定：\n{world_setting_text}\n\n"
        
        if previous_outline:
            reference_context += f"# 上一章大纲\n{previous_outline}\n\n"
        
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
        outline = state.get("outline", "")
        reference_context = state.get("reference_context") or self._build_context(novel_name, chapter_num)
        feedback = input_data.get("feedback")

        try:
            if isinstance(outline, dict):
                scenes = outline.get("scenes", [])
            elif isinstance(outline, str):
                outline_dict = json.loads(outline)
                scenes = outline_dict.get("scenes", [])
            else:
                raise ValueError("outline格式错误：既不是dict也不是字符串")
            
            if not scenes:
                raise ValueError("outline中没有scenes数组")
        except Exception as e:
            logger.error(f"[WriterHandler] outline解析失败: {e}, outline类型: {type(outline)}")
            raise ValueError(f"outline格式错误，无法解析场景: {e}")

        novel = DatabaseService.get_or_create_novel(novel_name)
        existing_content = DatabaseService.get_chapter_content(novel.id, chapter_num)
        
        rewrite_mode = feedback is not None
        if rewrite_mode and existing_content:
            scene_contents = self._split_scenes(existing_content, len(scenes))
        else:
            scene_contents = [None] * len(scenes)

        previous_text = "（章节开始）"
        full_content = []

        # 按大纲中的场景顺序依次生成，每个场景生成一段，最后拼接一次、不重复
        for i, scene in enumerate(scenes):
            scene_id = scene["id"]
            
            if rewrite_mode and scene_contents[i]:
                previous_text = scene_contents[i]
                full_content.append(scene_contents[i])
                continue

            logger.info(f"[WriterHandler] 正在撰写场景 {scene['id']}: {scene['summary'][:30]}...")

            feedback_section = (
                f"\n\n【重要】请根据以下审稿意见调整写作：\n{feedback}\n" if feedback else ""
            )
            prompt_raw = resolve_prompt("writer_builder")
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
        DatabaseService.add_pending_write(
            "content",
            novel.id,
            chapter_num,
            {"content": content},
            workflow_id=workflow_id,
            source_agent="writer",
        )

        return {"content": content}

    def _split_scenes(self, content: str, scene_count: int) -> list:
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

    def _get_source(self) -> EventSource:
        return EventSource.AGENT_WRITER

    def _get_completion_event_type(self) -> EventType:
        return EventType.CONTENT_WRITTEN
