import json
import logging
import yaml
from typing import Optional
from src.core.state import AgentState
from src.core.llm import LLMClient
from src.core.prompt_loader import get_fiction_system_prompt, resolve_prompt, format_prompt_template
from src.utils.file_manager import ProjectManager
from src.utils.json_utils import parse_json_from_response

logger = logging.getLogger(__name__)


class PlannerAgent:
    """规划Agent，负责生成章节分场景大纲"""
    
    def __init__(self, llm_client: LLMClient, file_manager: ProjectManager):
        self.llm_client = llm_client
        self.file_manager = file_manager
    
    def plan_chapter(self, state: AgentState) -> AgentState:
        """生成章节的分场景细纲"""
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        reference_context = state.get("reference_context", "")
        critique_comments = state.get("critique_comments")
        
        logger.info(f"[PlannerAgent] 开始规划第 {chapter_num} 章的分场景大纲")
        
        feedback_section = (
            f"\n\n【重要】请根据以下审稿意见调整场景规划：\n{critique_comments}\n"
            if critique_comments else ""
        )
        prompt_raw = resolve_prompt("architect")
        prompt_data = yaml.safe_load(prompt_raw)
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        architect_prompt = format_prompt_template(
            user_template,
            reference_context=reference_context,
            chapter_num=chapter_num,
            feedback_section=feedback_section,
        )
        messages = [
            {"role": "system", "content": get_fiction_system_prompt() + "\n\n" + system_prompt},
            {"role": "user", "content": architect_prompt}
        ]
        
        response = self.llm_client.chat(messages, temperature=0.7, max_tokens=4096)
        
        try:
            outline_json = parse_json_from_response(response)
            if not outline_json or "scenes" not in outline_json:
                raise ValueError("大纲生成失败，模型未返回有效的 JSON Scenes")
        except Exception as e:
            logger.error(f"解析场景大纲失败: {e}")
            logger.error(f"响应内容: {response[:500]}")
            raise ValueError(f"场景大纲解析失败: {e}")
        
        scenes = outline_json["scenes"]
        state["outline"] = json.dumps(scenes, ensure_ascii=False, indent=2)
        
        chapter_path = self.file_manager.init_chapter(novel_name, chapter_num)
        outline_path = chapter_path / "outline.md"
        outline_markdown = f"# 第{chapter_num}章分场景大纲\n\n"
        for scene in scenes:
            outline_markdown += f"## 场景 {scene['id']}\n\n"
            outline_markdown += f"**描述**: {scene['summary']}\n\n"
            outline_markdown += f"**目标字数**: {scene['expected_words']} 字\n\n"
            outline_markdown += f"**关键人物**: {', '.join(scene.get('key_characters', []))}\n\n"
        self.file_manager.save_content(outline_path, outline_markdown)
        
        logger.info(f"[PlannerAgent] 场景规划完成，共 {len(scenes)} 个场景")
        
        return state
