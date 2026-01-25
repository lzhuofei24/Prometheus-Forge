"""
萃取者模块（Crawler）

负责读取原始文本文件，提取小说设定（人物、世界观、关系等），
并将提取的设定保存到 workspace/{novel}/global/ 目录。
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import yaml
from src.core.llm import LLMClient
from src.rag.indexer import VectorIndexer
from src.utils.file_manager import ProjectManager


class Crawler:
    """
    萃取者类
    
    通过读取原著文本，使用 LLM 提取设定信息，并建立向量索引。
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        indexer: VectorIndexer,
        file_manager: ProjectManager
    ):
        """
        初始化萃取者
        
        Args:
            llm_client: LLM 客户端
            indexer: 向量索引器
            file_manager: 文件管理器
        """
        self.llm_client = llm_client
        self.indexer = indexer
        self.file_manager = file_manager
    
    def load_raw_text(self, file_path: Path) -> str:
        """
        加载原始文本文件
        
        支持多种编码格式（UTF-8, GBK, GB2312, Big5 等），
        自动检测并处理编码问题。
        
        Args:
            file_path: 文本文件路径
            
        Returns:
            文件内容字符串
            
        Raises:
            FileNotFoundError: 文件不存在
            UnicodeDecodeError: 无法解码文件内容
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        # 尝试的编码列表（按优先级排序）
        encodings = ['utf-8', 'gbk', 'gb2312', 'big5', 'latin-1']
        
        # 逐个尝试编码
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                return content
            except UnicodeDecodeError:
                continue
        
        # 如果所有编码都失败，使用 errors='replace' 作为最后手段
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return content
    
    def extract_settings(
        self, 
        text: str, 
        novel_name: str,
        prompt_template_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        从文本中提取设定
        
        使用 LLM 分析文本，提取：
        - 人物设定（bios.json）
        - 世界观设定（world.md）
        - 关系图（relation_graph.json）
        
        Args:
            text: 原始文本
            novel_name: 小说名称（用于保存设定文件）
            prompt_template_path: Prompt 模板路径（可选，默认使用 config/prompts/extraction.yaml）
            
        Returns:
            提取的设定字典，包含：
            - bios: 人物设定列表
            - world: 世界观设定文本
            - relations: 关系图字典
        """
        # 1. 加载 Prompt 模板
        if prompt_template_path is None:
            project_root = Path(__file__).parent.parent.parent
            prompt_template_path = project_root / "config" / "prompts" / "extraction.yaml"
        
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_data = yaml.safe_load(f)
        
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        
        # 2. 如果文本太长，只取前一部分进行分析（避免超出 token 限制）
        # 假设模型 max_tokens 为 8000，我们使用前 6000 个字符进行分析
        max_text_length = 6000
        text_chunk = text[:max_text_length] if len(text) > max_text_length else text
        if len(text) > max_text_length:
            text_chunk += "\n\n[注：文本已截断，仅分析前部分内容]"
        
        # 3. 构建用户提示词
        user_prompt = user_template.format(text_chunk=text_chunk)
        
        # 4. 调用 LLM 提取设定
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # 要求 LLM 返回 JSON 格式
        extraction_prompt = (
            "请以 JSON 格式返回提取的设定信息，格式如下：\n"
            "{\n"
            '  "bios": [\n'
            '    {"name": "人物姓名", "personality": "性格特点", "appearance": "外貌描述", "background": "背景信息"}\n'
            "  ],\n"
            '  "world": "世界观设定文本（Markdown 格式）",\n'
            '  "relations": {\n'
            '    "人物1": ["人物2", "人物3"],\n'
            '    "人物2": ["人物1"]\n'
            "  }\n"
            "}\n"
            "\n请只返回 JSON，不要包含其他说明文字。"
        )
        
        messages.append({"role": "user", "content": extraction_prompt})
        
        response = self.llm_client.chat(messages)
        
        # 5. 解析 JSON 响应
        # 尝试从响应中提取 JSON（可能包含 markdown 代码块）
        json_text = response.strip()
        if "```json" in json_text:
            # 提取代码块中的 JSON
            start = json_text.find("```json") + 7
            end = json_text.find("```", start)
            json_text = json_text[start:end].strip()
        elif "```" in json_text:
            # 提取普通代码块中的 JSON
            start = json_text.find("```") + 3
            end = json_text.find("```", start)
            json_text = json_text[start:end].strip()
        
        try:
            settings = json.loads(json_text)
        except json.JSONDecodeError:
            # 如果解析失败，返回空设定
            settings = {
                "bios": [],
                "world": "# 世界观设定\n\n（提取失败，请手动填写）",
                "relations": {}
            }
        
        # 6. 保存到文件
        global_dir = self.file_manager.get_global_settings_path(novel_name)
        
        # 保存人物设定
        bios_path = global_dir / "bios.json"
        self.file_manager.save_content(bios_path, settings.get("bios", []))
        
        # 保存世界观设定
        world_path = global_dir / "world.md"
        world_content = settings.get("world", "# 世界观设定\n\n")
        self.file_manager.save_content(world_path, world_content)
        
        # 保存关系图
        relations_path = global_dir / "relation_graph.json"
        self.file_manager.save_content(relations_path, settings.get("relations", {}))
        
        return settings
    
    def process_novel(
        self, 
        novel_name: str, 
        raw_file_path: Path,
        prompt_template_path: Optional[Path] = None
    ) -> None:
        """
        处理整部小说
        
        完整的处理流程：
        1. 初始化小说项目目录
        2. 加载原始文本
        3. 提取设定并保存
        4. 建立向量索引
        
        Args:
            novel_name: 小说名称
            raw_file_path: 原始文本文件路径
            prompt_template_path: Prompt 模板路径（可选）
        """
        # 1. 初始化小说项目目录
        self.file_manager.init_novel(novel_name)
        
        # 2. 加载原始文本
        text = self.load_raw_text(raw_file_path)
        
        # 3. 提取设定并保存
        settings = self.extract_settings(text, novel_name, prompt_template_path)
        
        # 4. 建立向量索引
        # 为文本添加元数据，方便后续检索
        metadata = {
            "novel_name": novel_name,
            "source": "raw_text",
            "file_path": str(raw_file_path)
        }
        
        # 将文本索引到向量数据库
        self.indexer.index_text(text, metadata=metadata)
