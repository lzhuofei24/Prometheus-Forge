import logging
import re
from typing import Dict, Any
from pathlib import Path
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager

logger = logging.getLogger(__name__)


class MediaHandler(BaseAgentHandler):
    """
    插画师 Agent：负责将小说片段转化为绘图 Prompt 并生成图片
    
    流程：
    1. Prompt Engineering: 调用 LLM 将中文小说片段转化为英文绘图 Prompt
    2. Safety Check: 替换敏感词汇为"氛围词"
    3. Image Generation: 调用生图 API
    4. Storage: 保存图片到本地或对象存储
    """
    
    def __init__(self, state_manager, dispatcher, llm_client: LLMClient, file_manager: ProjectManager):
        super().__init__(state_manager, dispatcher)
        self.llm_client = llm_client
        self.file_manager = file_manager

    def _process(self, workflow_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        核心处理逻辑：生成插画
        
        Args:
            workflow_id: 工作流 ID
            input_data: 包含 chapter_content 或 scene_description
        """
        state = self.state_manager.get_state(workflow_id)
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        
        chapter_content = input_data.get("chapter_content") or state.get("draft_content", "")
        scene_description = input_data.get("scene_description", "")
        
        if not chapter_content and not scene_description:
            raise ValueError("必须提供 chapter_content 或 scene_description")
        
        text_to_illustrate = scene_description if scene_description else chapter_content[:1000]
        
        prompt_en = self._generate_image_prompt(text_to_illustrate)
        sanitized_prompt = self._sanitize_prompt(prompt_en)
        
        image_url = self._generate_image(sanitized_prompt, novel_name, chapter_num)
        
        return {
            "prompt": sanitized_prompt,
            "image_url": image_url,
            "original_text": text_to_illustrate[:200]
        }

    def _generate_image_prompt(self, chinese_text: str) -> str:
        """
        Step 1: Prompt Engineering
        将中文小说片段转化为英文绘图 Prompt
        """
        prompt_engineering_prompt = f"""
你是一位专业的 AI 绘图 Prompt 工程师。请将以下中文小说片段转化为英文绘图 Prompt。

**原文**：
{chinese_text[:800]}

**要求**：
1. 将中文内容翻译为英文，保持场景和氛围
2. 添加视觉风格描述（如 "Anime style, Makoto Shinkai style, cinematic lighting"）
3. 替换敏感词汇：
   - 血腥/暴力 → 使用氛围词（如 "crimson fluid" 代替 "blood"）
   - 色情内容 → 使用暗示性描述（如 "intimate moment" 代替具体描写）
4. 强调画面构图、光影、色彩氛围
5. 输出纯英文 Prompt，不要包含解释文字

**输出格式**：
直接输出英文 Prompt，例如：
"A serene night scene in ancient Chinese style, soft moonlight filtering through traditional architecture, cinematic lighting, Makoto Shinkai style, ethereal atmosphere, detailed background, 4K quality"
"""

        messages = [
            {"role": "system", "content": "You are a professional AI image prompt engineer. Convert Chinese novel descriptions into English image generation prompts with artistic style descriptions."},
            {"role": "user", "content": prompt_engineering_prompt}
        ]

        response = self.llm_client.chat(messages, temperature=0.7, max_tokens=512)
        return response.strip()

    def _sanitize_prompt(self, prompt: str) -> str:
        """
        Step 2: Safety Check
        进一步清理敏感词汇
        """
        replacements = {
            r'\bblood\b': 'crimson fluid',
            r'\bviolence\b': 'dramatic tension',
            r'\bdeath\b': 'fading',
            r'\bkilling\b': 'confrontation',
        }
        
        sanitized = prompt
        for pattern, replacement in replacements.items():
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        
        return sanitized.strip()

    def _generate_image(self, prompt: str, novel_name: str, chapter_num: int) -> str:
        """
        Step 3: Image Generation
        调用 Gemini 2.5 Flash Image API 生成图片
        """
        logger.info(f"生成图片: novel={novel_name}, chapter={chapter_num}, prompt={prompt[:100]}...")
        
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        images_dir = chapter_path / "images"
        images_dir.mkdir(exist_ok=True)
        
        image_filename = f"scene_{len(list(images_dir.glob('*.png')))}.png"
        image_path = images_dir / image_filename
        
        try:
            from openai import OpenAI
            import os
            import base64
            
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY 未设置")
            
            client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost"),
                    "X-Title": os.getenv("OPENROUTER_APP_NAME", "Novel-Agent")
                }
            )
            
            response = client.chat.completions.create(
                model="google/gemini-2.5-flash-image",
                messages=[
                    {
                        "role": "user",
                        "content": f"Generate a high-quality image: {prompt}"
                    }
                ],
                extra_body={
                    "modalities": ["image", "text"],
                    "image_config": {
                        "aspect_ratio": "1:1"
                    }
                }
            )
            
            message = response.choices[0].message
            
            if hasattr(message, 'images') and message.images:
                img_item = message.images[0]
                if isinstance(img_item, dict) and 'image_url' in img_item:
                    url = img_item['image_url'].get('url', '')
                    if url.startswith('data:image/'):
                        base64_str = url.split(',', 1)[1]
                        image_data = base64.b64decode(base64_str)
                        
                        with open(image_path, "wb") as f:
                            f.write(image_data)
                        
                        logger.info(f"图片已保存: {image_path}")
                        return str(image_path.relative_to(self.file_manager.workspace_root))
            
            logger.warning("图片生成 API 返回空结果")
        except Exception as e:
            logger.error(f"图片生成失败: {e}", exc_info=True)
        
        return f"placeholder://{novel_name}/chapter_{chapter_num}/{image_filename}"

    def _get_source(self) -> EventSource:
        return EventSource.AGENT_MEDIA

    def _get_completion_event_type(self) -> EventType:
        return EventType.MEDIA_GENERATED
