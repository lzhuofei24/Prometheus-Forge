import json
import logging
import yaml
from typing import Optional, List
from src.core.state import AgentState
from src.core.llm import LLMClient
from src.core.prompt_loader import get_fiction_system_prompt, resolve_prompt, format_prompt_template
from src.utils.file_manager import ProjectManager

logger = logging.getLogger(__name__)


class WriterAgent:
    """写作Agent，负责场景正文生成"""
    
    def __init__(self, llm_client: LLMClient, file_manager: ProjectManager):
        self.llm_client = llm_client
        self.file_manager = file_manager
    
    def write_scenes(self, state: AgentState, scene_ids: Optional[List[int]] = None) -> AgentState:
        """
        写作场景正文
        
        Args:
            state: 当前状态
            scene_ids: 指定要写作的场景ID列表，None表示写全部场景（用于局部重写）
        """
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        reference_context = state.get("reference_context", "")
        critique_comments = state.get("critique_comments")
        
        outline_str = state.get("outline", "")
        try:
            scenes = json.loads(outline_str)
        except:
            logger.error(f"[WriterAgent] outline解析失败，无法获取场景列表")
            raise ValueError("outline格式错误，无法解析场景")
        
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        content_path = chapter_path / "content.md"
        
        rewrite_mode = scene_ids is not None
        if rewrite_mode:
            logger.info(f"[WriterAgent] 局部重写模式，目标场景: {scene_ids}")
            if content_path.exists():
                existing_content = self.file_manager.load_content(content_path)
            else:
                existing_content = ""
            scene_contents = self._split_scenes(existing_content, len(scenes))
        else:
            logger.info(f"[WriterAgent] 全文写作模式，共 {len(scenes)} 个场景")
            scene_contents = [None] * len(scenes)
        
        previous_text = "（章节开始）"
        
        for i, scene in enumerate(scenes):
            scene_id = scene["id"]
            
            if rewrite_mode and scene_id not in scene_ids:
                if scene_contents[i]:
                    previous_text = scene_contents[i]
                continue
            
            logger.info(f"[WriterAgent] 正在撰写场景 {i+1}/{len(scenes)}: {scene['summary'][:30]}...")
            
            feedback_section = (
                f"\n\n【重要】请根据以下审稿意见调整写作：\n{critique_comments}\n"
                if (critique_comments and (rewrite_mode or i == 0)) else ""
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
            
            scene_contents[i] = scene_content
            previous_text = scene_content
            
            current_draft = "\n\n***\n\n".join([s for s in scene_contents if s])
            self.file_manager.save_content(content_path, current_draft)
            logger.info(f"✅ 场景 {i+1} 完成并已保存，字数: {len(scene_content)}，累计字数: {len(current_draft)}")
        
        final_draft = "\n\n***\n\n".join([s for s in scene_contents if s])
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
        
        logger.info(f"[WriterAgent] 第 {chapter_num} 章完成，总字数: {len(final_draft)}")
        
        return state
    
    def _split_scenes(self, content: str, num_scenes: int) -> List[str]:
        """将现有内容按分隔符拆分为场景"""
        if not content:
            return [None] * num_scenes
        
        parts = content.split("\n\n***\n\n")
        
        if len(parts) == num_scenes:
            return parts
        elif len(parts) < num_scenes:
            return parts + [None] * (num_scenes - len(parts))
        else:
            return parts[:num_scenes]
