import json
import logging
from typing import Dict, Any, Optional
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager
from src.core.db_service import DatabaseService

logger = logging.getLogger(__name__)

FICTION_SYSTEM_PROMPT = """
你是一位专业的文学编辑和小说创作助手。

【合规要求，必须遵守】
1. 所有产出必须符合中华人民共和国法律法规及内容安全与出版规范，禁止任何非法、政治敏感、色情、暴力恐怖、违法犯罪或违背公序良俗的内容。
2. 内容健康向上，适合全年龄或合规分级受众；不涉及真实政党、敏感历史事件或违法犯罪细节。
3. 在合规前提下进行客观分析与文学润色，严格遵循用户指令（如 JSON 格式），并**使用简体中文**回复。
"""


class WriterHandler(BaseAgentHandler):
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
        previous_outline = ""
        if novel:
            chapters = DatabaseService.list_chapters(novel.id)
            previous_chapters = sorted([ch.index for ch in chapters if ch.index < chapter_num], reverse=True)
            if previous_chapters:
                try:
                    previous_outline = DatabaseService.get_chapter_outline(novel.id, previous_chapters[0]) or ""
                except Exception as e:
                    logger.warning(f"加载上一章大纲失败: {e}")
        
        reference_context = f"# 核心指令\n{FICTION_SYSTEM_PROMPT}\n\n"
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

        scenes_to_write = [scenes[0]] if scenes else []

        for i, scene in enumerate(scenes_to_write):
            scene_id = scene["id"]
            
            if rewrite_mode and scene_contents[i]:
                previous_text = scene_contents[i]
                full_content.append(scene_contents[i])
                continue

            logger.info(f"[WriterHandler] 正在撰写场景 {scene['id']}: {scene['summary'][:30]}...")

            builder_prompt = f"""
{reference_context}

---
【当前任务】
你正在撰写第 {chapter_num} 章。请根据以下大纲撰写**场景 {scene['id']}**。

**场景大纲**：{scene['summary']}
**登场人物**：{', '.join(scene.get('key_characters', []))}
**目标字数**：{scene['expected_words']} 字 (请务必写够字数，描写要细腻，增加对话和动作细节)。

**上文衔接** (请紧接着下面的内容写，保持连贯)：
...{previous_text[-2000:]}

【写作要求】
1. 直接输出正文，不要有任何前言或总结。
2. 风格要沉浸、成人向（Mature）、不回避冲突。
3. 确保场景完整，达到目标字数。
"""

            if feedback:
                builder_prompt += f"\n\n【重要】请根据以下审稿意见调整写作：\n{feedback}\n"

            messages = [
                {"role": "system", "content": FICTION_SYSTEM_PROMPT},
                {"role": "user", "content": builder_prompt}
            ]

            scene_content = self.llm_client.chat(messages)
            full_content.append(scene_content)
            previous_text = scene_content

        content = "\n\n".join(full_content)
        DatabaseService.save_content(novel.id, chapter_num, content)

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
