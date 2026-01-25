from pathlib import Path
from typing import Optional
import yaml
import re
import json
import logging
from src.core.state import AgentState
from src.core.llm import LLMClient
from src.core.prompt_loader import get_fiction_system_prompt, resolve_prompt
from src.utils.file_manager import ProjectManager
from src.utils.json_utils import parse_json_from_response

logger = logging.getLogger(__name__)

# 标记为废弃，推荐使用PlannerAgent和WriterAgent
logger.warning("Novelist类将被废弃，推荐使用PlannerAgent和WriterAgent")


class Novelist:
    def __init__(
        self,
        llm_client: LLMClient,
        file_manager: ProjectManager
    ):
        self.llm_client = llm_client
        self.file_manager = file_manager
    
    def generate_outline(self, state: AgentState) -> AgentState:
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        reference_context = state.get("reference_context", "")
        
        outline_prompt = (
            f"请为小说《{novel_name}》的第{chapter_num}章生成详细大纲。\n\n"
            f"{reference_context}\n\n"
            "请生成一个详细的大纲，包括：\n"
            "1. 章节标题（格式要求：只输出标题本身，不要包含'第X章'、'《小说名》'等前缀，例如：'神秘的灵能之旅'）\n"
            "2. 主要情节点（3-5个）\n"
            "3. 涉及的主要人物\n"
            "4. 关键场景描述\n"
            "\n请以 Markdown 格式输出，标题使用 # 开头。"
        )
        
        system_prompt = (
            get_fiction_system_prompt() + "\n\n" +
            "你是一位专业的小说创作助手，擅长创作符合原著风格的小说章节。\n\n"
            "**重要格式要求**：\n"
            "- 章节标题必须使用 `# 标题名称` 格式\n"
            "- 标题只包含标题本身，不要包含'第X章'、'《小说名》'等前缀\n"
            "- 例如：`# 神秘的灵能之旅`，而不是 `# 《测试小说》第3章：神秘的灵能之旅`"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": outline_prompt}
        ]
        
        outline = self.llm_client.chat(messages)
        state["outline"] = outline
        
        chapter_path = self.file_manager.init_chapter(novel_name, chapter_num)
        outline_path = chapter_path / "outline.md"
        self.file_manager.save_content(outline_path, outline)
        try:
            from src.core.db_service import DatabaseService
            novel = DatabaseService.get_or_create_novel(novel_name)
            DatabaseService.save_outline(novel.id, chapter_num, outline)
        except Exception as e:
            logger.warning("大纲写入数据库失败（已写入文件）: %s", e)
        
        return state
    
    def generate_draft(self, state: AgentState, feedback: Optional[str] = None) -> AgentState:
        """
        Architect-Builder 模式生成长章节
        
        Args:
            state: 当前状态
            feedback: 来自Critic的可执行反馈（用于迭代重写）
        """
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        reference_context = state.get("reference_context", "")
        critique_comments = state.get("critique_comments")
        
        # 优先使用新的feedback参数，如果没有则使用旧的critique_comments
        if feedback:
            critique_comments = feedback
        
        logger.info(f"🏗️ 开始 Architect-Builder 模式生成第 {chapter_num} 章")
        if feedback:
            logger.info(f"📝 本次基于反馈重写: {feedback[:100]}...")
        
        # --- Phase 1: Architect (生成分场景细纲) ---
        logger.info(f"📋 Phase 1: 正在规划第 {chapter_num} 章的分场景大纲...")
        
        feedback_section = (
            "\n\n【关键反馈 - 必须遵循】\n上一版审稿意见："
            + critique_comments
            + "\n你必须在场景规划中充分考虑这些反馈，调整情节结构、人物设置和冲突设计。\n"
            if critique_comments else ""
        )
        prompt_raw = resolve_prompt("architect")
        prompt_data = yaml.safe_load(prompt_raw)
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        architect_prompt = user_template.format(
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
        try:
            from src.core.db_service import DatabaseService
            novel = DatabaseService.get_or_create_novel(novel_name)
            DatabaseService.save_outline(novel.id, chapter_num, state["outline"])
        except Exception as e:
            logger.warning("分场景大纲写入数据库失败（已写入文件）: %s", e)
        
        logger.info(f"✅ 场景规划完成，共 {len(scenes)} 个场景")
        
        # --- Phase 2: Builder (循环写作) ---
        chapter_path = self.file_manager.init_chapter(novel_name, chapter_num)
        content_path = chapter_path / "content.md"
        
        full_content = []
        previous_text = "（章节开始）"
        
        for i, scene in enumerate(scenes):
            logger.info(f"✍️ Phase 2: 正在撰写场景 {i+1}/{len(scenes)}: {scene['summary'][:30]}...")
            
            feedback_section = (
                "\n\n【关键反馈 - 必须遵循】\n"
                f"Critical Feedback from previous draft: {critique_comments}\n"
                "You MUST revise the chapter to address these points while maintaining the plot.\n"
                "请在写作中充分体现这些修改建议，确保问题得到解决。\n"
                if critique_comments else ""
            )
            prompt_raw = resolve_prompt("writer_builder")
            prompt_data = yaml.safe_load(prompt_raw)
            user_template = prompt_data.get("user", "")
            builder_prompt = user_template.format(
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
            
            scene_content = None
            max_retries = 5
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(f"   尝试生成场景 {i+1}（第 {attempt}/{max_retries} 次）...")
                    scene_content = self.llm_client.chat(messages, max_tokens=4096, temperature=0.8)
                    if scene_content and len(scene_content.strip()) > 100:
                        logger.info(f"   ✅ 场景 {i+1} 生成成功，字数: {len(scene_content)}")
                        break
                    else:
                        logger.warning(f"   场景 {i+1} 响应内容过短，重试...")
                except Exception as e:
                    logger.warning(f"   场景 {i+1} 请求失败（第 {attempt} 次）: {e}")
                    if attempt < max_retries:
                        import time
                        time.sleep(2)
                    else:
                        raise ValueError(f"场景 {i+1} 生成失败，已重试 {max_retries} 次")
            
            if not scene_content:
                raise ValueError(f"场景 {i+1} 生成失败，未获得有效内容")
            
            full_content.append(scene_content)
            previous_text = scene_content
            
            current_draft = "\n\n***\n\n".join(full_content)
            self.file_manager.save_content(content_path, current_draft)
            logger.info(f"✅ 场景 {i+1} 完成并已保存，字数: {len(scene_content)}，累计字数: {len(current_draft)}")
        
        # --- Phase 3: Stitch (最终保存) ---
        logger.info("🔗 Phase 3: 最终保存全文...")
        final_draft = "\n\n***\n\n".join(full_content)
        state["draft_content"] = final_draft
        self.file_manager.save_content(content_path, final_draft)
        
        meta_path = chapter_path / "meta.json"
        if meta_path.exists():
            meta = self.file_manager.load_content(meta_path)
        else:
            meta = {}
        meta["word_count"] = len(final_draft)
        meta["status"] = "draft"
        from datetime import datetime
        meta["updated_at"] = datetime.now().isoformat()
        if not meta.get("created_at"):
            meta["created_at"] = meta["updated_at"]
        self.file_manager.save_content(meta_path, meta)
        
        logger.info(f"✅ 第 {chapter_num} 章生成完成，总字数: {len(final_draft)}")
        
        return state
    
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
    
    def reverse_outline(self, content: str) -> str:
        original_model = self.llm_client.model
        original_provider = self.llm_client.provider
        
        try:
            self.llm_client.switch_model("deepseek/deepseek-chat", "openrouter", "https://openrouter.ai/api/v1")
            
            system_prompt = (
                get_fiction_system_prompt() + "\n\n" +
                "你是一位专业的小说分析助手，擅长从章节正文中提炼出结构化的章节大纲。\n\n"
                "请仔细阅读章节正文，提炼出以下内容：\n"
                "1. 主要事件（按时间顺序）\n"
                "2. 关键冲突和转折点\n"
                "3. 人物表现和互动\n"
                "4. 章节结局或悬念\n\n"
                "请以 Markdown 格式输出，使用清晰的标题和列表结构。"
            )
            
            user_prompt = (
                f"请阅读以下章节正文，并提炼出一份结构化的章节大纲：\n\n"
                f"{content}\n\n"
                f"请生成详细的大纲，包括主要事件、冲突、人物表现和结果。"
            )
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            outline = self.llm_client.chat(messages, temperature=0.7, max_tokens=4000)
            return outline
        finally:
            self.llm_client.switch_model(original_model, original_provider)