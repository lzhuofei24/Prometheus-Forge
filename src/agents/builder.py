from pathlib import Path
from typing import Dict, Any, List
from src.core.state import AgentState
from src.core.llm import LLMClient
from src.rag.retriever import VectorRetriever
from src.utils.file_manager import ProjectManager


FICTION_SYSTEM_PROMPT = """
你是一位专业的文学编辑和小说创作助手。

【合规要求，必须遵守】
1. 所有产出必须符合中华人民共和国法律法规及内容安全与出版规范，禁止任何非法、政治敏感、色情、暴力恐怖、违法犯罪或违背公序良俗的内容。
2. 内容健康向上，适合全年龄或合规分级受众；不涉及真实政党、敏感历史事件或违法犯罪细节。
3. 在合规前提下进行客观分析与文学润色，严格遵循用户指令（如 JSON 格式），并**使用简体中文**回复。
"""


class WorldBuilder:
    def __init__(
        self,
        llm_client: LLMClient,
        retriever: VectorRetriever,
        file_manager: ProjectManager
    ):
        self.llm_client = llm_client
        self.retriever = retriever
        self.file_manager = file_manager
    
    def build_context(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("WorldBuilder.build_context() 开始执行（升级版：加载超长上下文）")
            novel_name = state["novel_name"]
            chapter_num = state["chapter_num"]
            logger.info(f"处理小说: {novel_name}, 章节: {chapter_num}")
            
            global_dir = self.file_manager.get_global_settings_path(novel_name)
            bios_path = global_dir / "bios.json"
            world_path = global_dir / "world.md"
            story_summary_path = global_dir / "story_summary.md"
            
            logger.info("加载全局设定文件")
            bios = self.file_manager.load_content(bios_path) if bios_path.exists() else []
            world = self.file_manager.load_content(world_path) if world_path.exists() else ""
            story_summary = self.file_manager.load_content(story_summary_path) if story_summary_path.exists() else ""
            logger.info(f"加载完成: bios={len(bios) if isinstance(bios, list) else 'N/A'}, world长度={len(world)}, story_summary长度={len(story_summary)}")
            
            logger.info("格式化人物设定和世界观")
            character_bios_text = self._format_bios(bios)
            world_setting_text = world if world else ""
            
            existing_chapters = self.file_manager.list_chapters(novel_name)
            all_previous_chapters = sorted([ch for ch in existing_chapters if ch < chapter_num], reverse=True)
            
            logger.info("加载最近3章完整正文")
            recent_3_chapters = all_previous_chapters[:3]  # 最近3章
            recent_chapters_content = []
            
            for ch_num in reversed(recent_3_chapters):
                try:
                    ch_path = self.file_manager.get_chapter_path(novel_name, ch_num)
                    content_path = ch_path / "content.md"
                    if content_path.exists():
                        content = self.file_manager.load_content(content_path)
                        recent_chapters_content.append(f"## 第{ch_num}章完整正文\n\n{content}\n\n")
                        logger.info(f"加载第{ch_num}章正文，长度: {len(content)}")
                except Exception as e:
                    logger.warning(f"加载第{ch_num}章正文失败: {e}")
                    continue
            
            recent_content_text = "\n\n---\n\n".join(recent_chapters_content)
            logger.info(f"最近3章正文总长度: {len(recent_content_text)}")
            
            logger.info("加载近15章大纲（排除最近3章）")
            # 从第4倒数章开始，往前取15章的大纲
            max_outline_count = 15
            outline_chapters = all_previous_chapters[3:3+max_outline_count]  # 跳过最近3章，取接下来15章
            outlines_text_list = []
            
            for ch_num in reversed(outline_chapters):
                try:
                    ch_path = self.file_manager.get_chapter_path(novel_name, ch_num)
                    outline_path = ch_path / "outline.md"
                    
                    if outline_path.exists():
                        outline = self.file_manager.load_content(outline_path)
                        outlines_text_list.append((ch_num, f"### 第{ch_num}章大纲\n{outline}\n"))
                        logger.info(f"加载第{ch_num}章大纲，长度: {len(outline)}")
                except Exception as e:
                    logger.warning(f"加载第{ch_num}章大纲失败: {e}")
                    continue
            
            outlines_text = "\n".join([text for _, text in outlines_text_list])
            logger.info(f"近15章大纲总长度: {len(outlines_text)}, 共{len(outlines_text_list)}章")
            
            logger.info("组装参考上下文并控制 token 数量")
            
            # 1. 基础部分（固定）
            base_context = f"# 核心指令\n{FICTION_SYSTEM_PROMPT}\n\n"
            base_context += f"# 世界观与人物\n## 人物设定：\n{character_bios_text}\n\n## 世界观设定：\n{world_setting_text}\n\n"
            if story_summary:
                base_context += f"# 全书剧情梗概 (The Story So Far)\n{story_summary}\n\n"
            
            # 2. 最近3章完整正文（固定）
            content_part = ""
            if recent_content_text:
                content_part = f"# 最近3章完整正文 (第{recent_3_chapters[-1] if recent_3_chapters else '?'}章-第{recent_3_chapters[0] if recent_3_chapters else '?'}章)\n{recent_content_text}\n\n"
            
            # 3. 动态调整大纲数量以满足 token 限制
            MAX_TOKENS = 24000
            
            def estimate_tokens(text: str) -> int:
                """估算文本的 token 数（中文按1.5字/token，英文按4字/token）"""
                chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
                other_chars = len(text) - chinese_chars
                return int(chinese_chars / 1.5 + other_chars / 4)
            
            # 计算基础部分和正文的 token
            base_tokens = estimate_tokens(base_context)
            content_tokens = estimate_tokens(content_part)
            available_tokens = MAX_TOKENS - base_tokens - content_tokens
            
            logger.info(f"Token 分配: 基础={base_tokens}, 正文={content_tokens}, 可用于大纲={available_tokens}")
            
            # 逐步添加大纲，直到达到 token 限制
            selected_outlines = []
            selected_chapters = []
            current_outline_tokens = 0
            
            for ch_num, outline_text in outlines_text_list:
                outline_tokens = estimate_tokens(outline_text)
                if current_outline_tokens + outline_tokens <= available_tokens:
                    selected_outlines.append(outline_text)
                    selected_chapters.append(ch_num)
                    current_outline_tokens += outline_tokens
                    logger.info(f"包含第{ch_num}章大纲，累计 token: {current_outline_tokens}")
                else:
                    logger.info(f"跳过第{ch_num}章大纲（超出 token 限制）")
                    break
            
            outlines_text = "\n".join(selected_outlines)
            logger.info(f"最终大纲部分: {len(selected_outlines)}章, {current_outline_tokens} tokens")
            
            # 组装最终上下文
            reference_context = base_context
            if outlines_text and selected_chapters:
                first_ch = selected_chapters[0]  # 第一个选中的章节
                last_ch = selected_chapters[-1]  # 最后一个选中的章节
                reference_context += f"# 近{len(selected_outlines)}章大纲（第{first_ch}章-第{last_ch}章）\n{outlines_text}\n\n"
            reference_context += content_part
            
            total_tokens = estimate_tokens(reference_context)
            logger.info(f"reference_context 总长度: {len(reference_context)} 字符, 约 {total_tokens} tokens")
            
            logger.info("更新状态")
            state["reference_context"] = reference_context
            state["character_bios"] = character_bios_text
            state["world_setting"] = world_setting_text
            state["reference_style"] = ""
            logger.info("WorldBuilder.build_context() 完成")
            return state
        except Exception as e:
            logger.error(f"WorldBuilder.build_context() 执行失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _format_bios(self, bios: List[Dict[str, Any]]) -> str:
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
    
    def update_global_settings(self, state: AgentState) -> AgentState:
        if not state.get("character_updates"):
            return state
        
        novel_name = state["novel_name"]
        global_dir = self.file_manager.get_global_settings_path(novel_name)
        bios_path = global_dir / "bios.json"
        
        bios = self.file_manager.load_content(bios_path) if bios_path.exists() else []
        if not isinstance(bios, list):
            bios = []
        
        updates = state["character_updates"]
        for update in updates.values():
            if isinstance(update, dict) and "name" in update:
                existing = next((b for b in bios if isinstance(b, dict) and b.get("name") == update["name"]), None)
                if existing:
                    existing.update(update)
                else:
                    bios.append(update)
        
        self.file_manager.save_content(bios_path, bios)
        return state
