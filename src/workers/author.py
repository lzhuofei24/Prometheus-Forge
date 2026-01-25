"""
作者模块（Author）

负责基于提取的设定生成小说大纲和正文内容。
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import yaml
from src.core.llm import LLMClient
from src.core.db_service import DatabaseService
from src.rag.retriever import VectorRetriever
from src.utils.file_manager import ProjectManager

logger = logging.getLogger(__name__)


class Author:
    """
    作者类
    
    基于设定和 RAG 检索结果，生成小说章节的大纲和正文。
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        retriever: VectorRetriever,
        file_manager: ProjectManager
    ):
        """
        初始化作者
        
        Args:
            llm_client: LLM 客户端
            retriever: 向量检索器
            file_manager: 文件管理器
        """
        self.llm_client = llm_client
        self.retriever = retriever
        self.file_manager = file_manager
    
    def generate_outline(
        self,
        novel_name: str,
        chapter_num: int,
        previous_context: List[Dict[str, Any]] = None,
        prompt_template_path: Optional[Path] = None
    ) -> str:
        """
        生成章节大纲
        
        Args:
            novel_name: 小说名称
            chapter_num: 章节编号
            previous_context: 前文上下文（可选，包含前几章的信息）
            prompt_template_path: 已废弃，保留仅为兼容；大纲生成未使用提示词模板。
            
        Returns:
            章节大纲文本
        """
        # 1. 加载全局设定
        global_dir = self.file_manager.get_global_settings_path(novel_name)
        bios_path = global_dir / "bios.json"
        world_path = global_dir / "world.md"
        
        bios = self.file_manager.load_content(bios_path) if bios_path.exists() else []
        world = self.file_manager.load_content(world_path) if world_path.exists() else ""
        
        # 2. 检索相关的原著片段作为参考
        # 构建查询文本：结合人物和世界观信息
        query_text = f"第{chapter_num}章"
        if bios:
            character_names = [bio.get("name", "") for bio in bios if isinstance(bio, dict)]
            if character_names:
                query_text += " " + " ".join(character_names[:3])  # 使用前3个人物名
        
        retrieved_chunks = self.retriever.retrieve(query_text, top_k=3)
        reference_text = "\n\n".join([chunk["text"] for chunk in retrieved_chunks])
        
        # 3. 构建前文上下文信息
        context_text = ""
        if previous_context:
            context_summary = []
            for ctx in previous_context:
                if isinstance(ctx, dict):
                    ctx_text = ctx.get("summary", ctx.get("outline", ""))
                    if ctx_text:
                        context_summary.append(f"第{ctx.get('chapter_num', '?')}章: {ctx_text[:200]}")
            context_text = "\n".join(context_summary)
        
        # 4. 使用 LLM 生成大纲
        outline_prompt = (
            f"请为小说《{novel_name}》的第{chapter_num}章生成详细大纲。\n\n"
            f"## 人物设定：\n{self._format_bios(bios)}\n\n"
            f"## 世界观设定：\n{world[:1000]}\n\n"
        )
        
        if context_text:
            outline_prompt += f"## 前文摘要：\n{context_text}\n\n"
        
        if reference_text:
            outline_prompt += f"## 原著参考片段：\n{reference_text[:500]}\n\n"
        
        outline_prompt += (
            "请生成一个详细的大纲，包括：\n"
            "1. 章节标题\n"
            "2. 主要情节点（3-5个）\n"
            "3. 涉及的主要人物\n"
            "4. 关键场景描述\n"
            "\n请以 Markdown 格式输出。"
        )
        
        messages = [
            {"role": "system", "content": "你是一位专业的小说创作助手，擅长创作符合原著风格的小说章节。"},
            {"role": "user", "content": outline_prompt}
        ]
        
        outline = self.llm_client.chat(messages)
        
        # 5. 保存大纲（文件 + 数据库）
        chapter_path = self.file_manager.init_chapter(novel_name, chapter_num)
        outline_path = chapter_path / "outline.md"
        self.file_manager.save_content(outline_path, outline)
        try:
            novel = DatabaseService.get_or_create_novel(novel_name)
            DatabaseService.save_outline(novel.id, chapter_num, outline)
        except Exception as e:
            logger.warning("大纲写入数据库失败（已写入文件）: %s", e)
        
        return outline
    
    def _format_bios(self, bios: List[Dict[str, Any]]) -> str:
        """格式化人物设定为文本"""
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
    
    def generate_content(
        self,
        novel_name: str,
        chapter_num: int,
        outline: str = None,
        prompt_template_path: Optional[Path] = None
    ) -> str:
        """
        生成章节正文
        
        Args:
            novel_name: 小说名称
            chapter_num: 章节编号
            outline: 章节大纲（如果为 None，从文件加载）
            prompt_template_path: 已废弃，保留仅为兼容；提示词仅从数据库 key=writing 读取。
            
        Returns:
            章节正文文本
        """
        # 1. 加载大纲（如果未提供）
        if outline is None:
            chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
            outline_path = chapter_path / "outline.md"
            if outline_path.exists():
                outline = self.file_manager.load_content(outline_path)
            else:
                outline = f"# 第{chapter_num}章\n\n（无大纲）"
        
        # 2. 加载全局设定
        global_dir = self.file_manager.get_global_settings_path(novel_name)
        bios_path = global_dir / "bios.json"
        world_path = global_dir / "world.md"
        
        bios = self.file_manager.load_content(bios_path) if bios_path.exists() else []
        world = self.file_manager.load_content(world_path) if world_path.exists() else ""
        
        # 3. 检索相关的原著片段作为风格参考
        # 从大纲中提取关键词进行检索
        query_text = outline[:200]  # 使用大纲的前200字符作为查询
        retrieved_chunks = self.retriever.retrieve(query_text, top_k=5)
        reference_text = "\n\n---\n\n".join([chunk["text"] for chunk in retrieved_chunks])
        
        # 4. 从数据库加载 writing 提示词（仅 DB，不使用 YAML）
        from src.core.prompt_loader import resolve_prompt
        prompt_raw = resolve_prompt("writing")
        prompt_data = yaml.safe_load(prompt_raw)
        
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        
        # 5. 构建设定文本
        settings_text = f"## 人物设定：\n{self._format_bios(bios)}\n\n## 世界观设定：\n{world[:1500]}"
        
        # 6. 使用 LLM 生成正文
        user_prompt = user_template.format(
            settings=settings_text,
            outline=outline
        )
        
        # 添加风格参考
        if reference_text:
            user_prompt += f"\n\n## 原著风格参考：\n{reference_text[:1000]}\n\n请参考以上片段的写作风格。"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        content = self.llm_client.chat(messages)
        
        # 7. 保存正文
        chapter_path = self.file_manager.init_chapter(novel_name, chapter_num)
        content_path = chapter_path / "content.md"
        self.file_manager.save_content(content_path, content)
        
        # 8. 更新元数据
        meta_path = chapter_path / "meta.json"
        if meta_path.exists():
            meta = self.file_manager.load_content(meta_path)
            meta["word_count"] = len(content)
            meta["status"] = "draft"
            from datetime import datetime
            meta["updated_at"] = datetime.now().isoformat()
            if not meta.get("created_at"):
                meta["created_at"] = meta["updated_at"]
            self.file_manager.save_content(meta_path, meta)
        
        return content
    
    def write_chapter(
        self,
        novel_name: str,
        chapter_num: int,
        auto_outline: bool = True,
        previous_context: List[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """
        完整生成一个章节（大纲 + 正文）
        
        Args:
            novel_name: 小说名称
            chapter_num: 章节编号
            auto_outline: 是否自动生成大纲（如果为 False，需要先手动创建大纲）
            previous_context: 前文上下文（可选，用于生成大纲时参考）
            
        Returns:
            包含大纲和正文的字典：
            {
                "outline": 章节大纲文本,
                "content": 章节正文文本
            }
        """
        # 1. 初始化章节目录
        chapter_path = self.file_manager.init_chapter(novel_name, chapter_num)
        
        # 2. 生成大纲（如果需要）
        outline = None
        if auto_outline:
            outline = self.generate_outline(
                novel_name=novel_name,
                chapter_num=chapter_num,
                previous_context=previous_context
            )
        else:
            # 从文件加载已有大纲
            outline_path = chapter_path / "outline.md"
            if outline_path.exists():
                outline = self.file_manager.load_content(outline_path)
            else:
                # 如果没有大纲，自动生成
                outline = self.generate_outline(
                    novel_name=novel_name,
                    chapter_num=chapter_num,
                    previous_context=previous_context
                )
        
        # 3. 生成正文
        content = self.generate_content(
            novel_name=novel_name,
            chapter_num=chapter_num,
            outline=outline
        )
        
        # 4. 更新元数据（已在 generate_content 中完成）
        
        return {
            "outline": outline,
            "content": content
        }
