from pathlib import Path
import yaml
import json
from src.core.state import AgentState
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager


FICTION_SYSTEM_PROMPT = """
你是一位专业的文学编辑和小说创作助手。

【合规要求，必须遵守】
1. 所有产出必须符合中华人民共和国法律法规及内容安全与出版规范，禁止任何非法、政治敏感、色情、暴力恐怖、违法犯罪或违背公序良俗的内容。
2. 内容健康向上，适合全年龄或合规分级受众；不涉及真实政党、敏感历史事件或违法犯罪细节。
3. 在合规前提下进行客观分析与文学润色，严格遵循用户指令（如 JSON 格式），并**使用简体中文**回复。
"""


class ChiefEditor:
    def __init__(
        self,
        llm_client: LLMClient,
        file_manager: ProjectManager
    ):
        self.llm_client = llm_client
        self.file_manager = file_manager
    
    def plan_next_step(self, state: AgentState) -> str:
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        
        existing_chapters = self.file_manager.list_chapters(novel_name)
        
        if chapter_num not in existing_chapters:
            return "world_builder"
        
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        outline_path = chapter_path / "outline.md"
        content_path = chapter_path / "content.md"
        
        if not outline_path.exists():
            return "world_builder"
        elif not content_path.exists() or state.get("revision_count", 0) > 0:
            return "novelist"
        else:
            return "critic"
    
    def should_continue(self, state: AgentState) -> bool:
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        content_path = chapter_path / "content.md"
        
        return content_path.exists()


class Critic:
    def __init__(
        self,
        llm_client: LLMClient,
        file_manager: ProjectManager
    ):
        self.llm_client = llm_client
        self.file_manager = file_manager
    
    def critique(self, state: AgentState) -> AgentState:
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        draft_content = state.get("draft_content", "")
        outline = state.get("outline", "")
        reference_context = state.get("reference_context", "")
        
        if not draft_content:
            chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
            content_path = chapter_path / "content.md"
            if content_path.exists():
                draft_content = self.file_manager.load_content(content_path)
                state["draft_content"] = draft_content
        
        project_root = Path(__file__).parent.parent.parent
        prompt_template_path = project_root / "config" / "prompts" / "critique.yaml"
        
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_data = yaml.safe_load(f)
        
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        
        user_prompt = user_template.format(
            novel_name=novel_name,
            chapter_num=chapter_num,
            outline=outline,
            draft_content=draft_content,
            reference_context=reference_context
        )
        
        messages = [
            {"role": "system", "content": FICTION_SYSTEM_PROMPT + "\n\n" + system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = self.llm_client.chat(messages)
        
        json_text = response.strip()
        if "```json" in json_text:
            start = json_text.find("```json") + 7
            end = json_text.find("```", start)
            json_text = json_text[start:end].strip()
        elif "```" in json_text:
            start = json_text.find("```") + 3
            end = json_text.find("```", start)
            json_text = json_text[start:end].strip()
        
        try:
            critique_result = json.loads(json_text)
            state["critique_score"] = critique_result.get("score", 0)
            state["critique_comments"] = critique_result.get("comments", "")
            state["actionable_feedback"] = critique_result.get("actionable_feedback", "")
            state["character_updates"] = critique_result.get("character_updates", {})
            
            # 如果没有actionable_feedback，使用comments作为降级方案
            if not state["actionable_feedback"] and state["critique_comments"]:
                state["actionable_feedback"] = state["critique_comments"]
        except json.JSONDecodeError:
            state["critique_score"] = 50
            state["critique_comments"] = "审稿解析失败，请检查内容质量。"
            state["actionable_feedback"] = "请重新审视章节结构，确保情节连贯、人物饱满。"
            state["character_updates"] = {}
        
        return state
    
    def should_approve(self, state: AgentState) -> bool:
        score = state.get("critique_score", 0)
        revision_count = state.get("revision_count", 0)
        return score >= 90 or revision_count >= 3
    
    def _estimate_tokens(self, text: str) -> int:
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)
    
    def _truncate_content(self, content: str, max_tokens: int = 6000) -> str:
        if self._estimate_tokens(content) <= max_tokens:
            return content
        
        lines = content.split('\n')
        truncated = []
        current_tokens = 0
        
        for line in lines:
            line_tokens = self._estimate_tokens(line)
            if current_tokens + line_tokens > max_tokens:
                break
            truncated.append(line)
            current_tokens += line_tokens
        
        result = '\n'.join(truncated)
        if len(result) < len(content):
            result += "\n\n[注：内容已截断以适应模型上下文限制]"
        return result
    
    def review_chapter(self, content: str, outline: str) -> dict:
        """
        审稿章节，返回包含评分和可执行反馈的JSON
        
        Returns:
            dict: {
                "score": int (0-100),
                "comments": str,
                "actionable_feedback": str  # 针对Writer的具体修改指令
            }
        """
        original_model = self.llm_client.model
        original_provider = self.llm_client.provider
        
        try:
            self.llm_client.switch_model("deepseek/deepseek-chat", "openrouter", "https://openrouter.ai/api/v1")
            
            system_prompt = (
                FICTION_SYSTEM_PROMPT + "\n\n" +
                "你是一位专业的小说编辑，擅长评估章节的质量并提供可执行的修改建议。\n\n"
                "请从以下维度评价章节：\n"
                "1. 节奏感：情节推进是否流畅，是否有拖沓或过快的问题\n"
                "2. 代入感：读者是否能沉浸其中，场景描写是否生动\n"
                "3. 人物表现：人物行为是否合理，性格是否鲜明\n"
                "4. 整体质量：综合评分（0-100分）\n\n"
                "**关键要求**：\n"
                "- 必须返回严格的 JSON 格式\n"
                "- 包含三个字段：score (整数), comments (总体评价), actionable_feedback (具体修改指令)\n"
                "- actionable_feedback 必须是针对Writer的可执行建议，例如：\n"
                "  * '增加对话冲突，让人物之间的矛盾更明显'\n"
                "  * '减少环境描写，加快情节推进速度'\n"
                "  * '强化主角的情感变化，让读者更有共鸣'\n"
                "- 如果评分低于75分，actionable_feedback 必须给出2-3条具体的修改方向"
            )
            
            user_prompt = (
                f"请审阅以下章节：\n\n"
                f"## 章节大纲：\n{outline}\n\n"
                f"## 章节正文：\n{content}\n\n"
                f"请从节奏、代入感、人物表现等维度进行专业点评，给出综合评分（0-100分），"
                f"并提供针对Writer的具体、可执行的修改建议。\n\n"
                f"**输出格式示例**：\n"
                f'{{\n'
                f'  "score": 65,\n'
                f'  "comments": "节奏较慢，对话缺乏冲突",\n'
                f'  "actionable_feedback": "1. 增加人物对话中的矛盾冲突，让对话更有张力；2. 减少环境描写篇幅，将重点放在人物行为和心理变化上；3. 在关键情节点增加悬念或转折。"\n'
                f'}}'
            )
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = self.llm_client.chat(messages, temperature=0.7, max_tokens=3000)
            
            json_text = response.strip()
            if "```json" in json_text:
                start = json_text.find("```json") + 7
                end = json_text.find("```", start)
                json_text = json_text[start:end].strip()
            elif "```" in json_text:
                start = json_text.find("```") + 3
                end = json_text.find("```", start)
                json_text = json_text[start:end].strip()
            
            try:
                result = json.loads(json_text)
                if "score" not in result:
                    result["score"] = 50
                if "comments" not in result:
                    result["comments"] = "审稿解析失败"
                if "actionable_feedback" not in result:
                    result["actionable_feedback"] = "请整体提升章节质量，增强情节吸引力和人物表现力。"
                return result
            except json.JSONDecodeError:
                return {
                    "score": 50,
                    "comments": "审稿解析失败，请检查内容质量。",
                    "actionable_feedback": "请重新审视章节结构，确保情节连贯、人物饱满。"
                }
        finally:
            self.llm_client.switch_model(original_model, original_provider)