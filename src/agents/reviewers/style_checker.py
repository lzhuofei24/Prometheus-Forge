from pathlib import Path
import yaml
import json
import logging
from typing import Dict, Any
from .base_checker import BaseChecker
from src.core.state import AgentState
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager

logger = logging.getLogger(__name__)

FICTION_SYSTEM_PROMPT = """
你是一位专业的文学编辑和小说创作助手。

【合规要求，必须遵守】
1. 所有产出必须符合中华人民共和国法律法规及内容安全与出版规范，禁止任何非法、政治敏感、色情、暴力恐怖、违法犯罪或违背公序良俗的内容。
2. 内容健康向上，适合全年龄或合规分级受众；不涉及真实政党、敏感历史事件或违法犯罪细节。
3. 在合规前提下进行客观分析与文学润色，严格遵循用户指令（如 JSON 格式），并**使用简体中文**回复。
"""


class StyleChecker(BaseChecker):
    def __init__(self, llm_client: LLMClient, file_manager: ProjectManager):
        self.llm_client = llm_client
        self.file_manager = file_manager
    
    def get_name(self) -> str:
        return "style"
    
    def check(self, state: AgentState) -> Dict[str, Any]:
        logger.info(f"[StyleChecker] 开始检查第 {state['chapter_num']} 章的文风")
        
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        draft_content = state.get("draft_content", "")
        outline = state.get("outline", "")
        reference_style = state.get("reference_style", "")
        
        if not draft_content:
            chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
            content_path = chapter_path / "content.md"
            if content_path.exists():
                draft_content = self.file_manager.load_content(content_path)
        
        project_root = Path(__file__).parent.parent.parent.parent
        prompt_path = project_root / "config" / "prompts" / "style_check.yaml"
        
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_data = yaml.safe_load(f)
        
        system_prompt = FICTION_SYSTEM_PROMPT + "\n\n" + prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        
        user_prompt = user_template.format(
            reference_style=reference_style or "（无参考风格）",
            chapter_content=draft_content,
            outline=outline
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.llm_client.chat(messages, temperature=0.5, max_tokens=3000)
        
        try:
            result = self._parse_json_response(response)
            logger.info(f"[StyleChecker] 评分: {result['score']}")
            return result
        except Exception as e:
            logger.error(f"[StyleChecker] 解析失败: {e}")
            return {
                "score": 50,
                "issues": [{"scene_id": 0, "type": "解析错误", "description": str(e)}],
                "suggestions": [],
                "strengths": []
            }
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        json_text = response.strip()
        if "```json" in json_text:
            start = json_text.find("```json") + 7
            end = json_text.find("```", start)
            json_text = json_text[start:end].strip()
        elif "```" in json_text:
            start = json_text.find("```") + 3
            end = json_text.find("```", start)
            json_text = json_text[start:end].strip()
        
        return json.loads(json_text)
