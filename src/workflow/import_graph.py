from typing import Literal
from langgraph.graph import StateGraph, END
from src.core.state import AgentState
from src.agents.novelist import Novelist
from src.agents.editor import Critic
from src.utils.file_manager import ProjectManager
from src.core.llm import LLMClient
from datetime import datetime
from pathlib import Path
import json
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


FICTION_SYSTEM_PROMPT = """
你是一位专业的文学编辑和小说创作助手。

【合规要求，必须遵守】
1. 所有产出必须符合中华人民共和国法律法规及内容安全与出版规范，禁止任何非法、政治敏感、色情、暴力恐怖、违法犯罪或违背公序良俗的内容。
2. 内容健康向上，适合全年龄或合规分级受众；不涉及真实政党、敏感历史事件或违法犯罪细节。
3. 在合规前提下进行客观分析与文学润色，严格遵循用户指令（如 JSON 格式），并**使用简体中文**回复。
"""


class ImportWorkflow:
    def __init__(
        self,
        novelist: Novelist,
        critic: Critic,
        file_manager: ProjectManager,
        llm_client: LLMClient
    ):
        self.novelist = novelist
        self.critic = critic
        self.file_manager = file_manager
        self.llm_client = llm_client
        self.graph = self._build_graph()
    
    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        workflow.add_node("load", self._load_node)
        workflow.add_node("extract", self._extract_node)
        workflow.add_node("outline", self._outline_node)
        workflow.add_node("review", self._review_node)
        
        workflow.set_entry_point("load")
        
        workflow.add_edge("load", "extract")
        workflow.add_edge("extract", "outline")
        workflow.add_edge("outline", "review")
        workflow.add_edge("review", END)
        
        return workflow.compile()
    
    def _load_node(self, state: AgentState) -> AgentState:
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        content_path = chapter_path / "content.md"
        
        if not content_path.exists():
            raise FileNotFoundError(f"章节内容不存在: {content_path}")
        
        content = self.file_manager.load_content(content_path)
        state["draft_content"] = content
        
        return state
    
    def _extract_node(self, state: AgentState) -> AgentState:
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        content = state.get("draft_content", "")
        
        if not content:
            raise ValueError("章节内容为空")
        
        project_root = Path(__file__).parent.parent.parent
        prompt_template_path = project_root / "config" / "prompts" / "extraction.yaml"
        
        with open(prompt_template_path, "r", encoding="utf-8") as f:
            prompt_data = yaml.safe_load(f)
        
        original_system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        
        system_prompt = FICTION_SYSTEM_PROMPT + "\n\n" + original_system_prompt
        
        user_prompt = user_template.format(text_chunk=content)
        
        extraction_prompt = (
            "请以 JSON 格式返回提取的设定信息，格式如下：\n"
            "{\n"
            '  "characters": [\n'
            '    {"name": "人物姓名", "aliases": ["绰号1"], "role": "主角/配角/反派/路人", "tags": ["性格标签"], "description": "综合描述", "abilities": ["技能"], "status": "当前状态"}\n'
            "  ],\n"
            '  "world_setting": [\n'
            '    {"category": "Location/Organization/Rule/Item", "name": "名词", "description": "详细描述"}\n'
            "  ],\n"
            '  "relationships": [\n'
            '    {"source": "人物A", "target": "人物B或势力", "relation": "关系类型", "details": "具体描述"}\n'
            "  ],\n"
            '  "style_analysis": {\n'
            '    "tone": "整体基调",\n'
            '    "key_dialogues": ["台词1", "台词2"]\n'
            "  }\n"
            "}\n"
            "\n请只返回 JSON，不要包含其他说明文字。"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "user", "content": extraction_prompt}
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
            extraction_data = json.loads(json_text)
        except json.JSONDecodeError:
            extraction_data = {
                "characters": [],
                "world_setting": [],
                "relationships": [],
                "style_analysis": {"tone": "", "key_dialogues": []}
            }
        
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        extraction_path = chapter_path / "extraction.json"
        self.file_manager.save_content(extraction_path, extraction_data)
        
        state["extraction"] = extraction_data
        
        return state
    
    def _outline_node(self, state: AgentState) -> AgentState:
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        content = state.get("draft_content", "")
        
        if not content:
            raise ValueError("章节内容为空")
        
        outline = self.novelist.reverse_outline(content)
        state["outline"] = outline
        
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        outline_path = chapter_path / "outline.md"
        self.file_manager.save_content(outline_path, outline)
        
        return state
    
    def _review_node(self, state: AgentState) -> AgentState:
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        content = state.get("draft_content", "")
        outline = state.get("outline", "")
        extraction = state.get("extraction", {})
        
        if not content:
            raise ValueError("章节内容为空")
        if not outline:
            raise ValueError("章节大纲为空")
        
        extraction_summary = ""
        if extraction:
            extraction_summary = f"\n\n## 提取的设定信息：\n"
            if extraction.get("characters"):
                extraction_summary += f"人物：{', '.join([c.get('name', '') for c in extraction['characters']])}\n"
            if extraction.get("world_setting"):
                extraction_summary += f"世界观要素：{len(extraction['world_setting'])} 项\n"
            if extraction.get("relationships"):
                extraction_summary += f"关系：{len(extraction['relationships'])} 项\n"
        
        review_result = self.critic.review_chapter(content, outline + extraction_summary)
        
        state["critique_score"] = review_result.get("score", 50)
        state["critique_comments"] = review_result.get("comments", "")
        
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        meta_path = chapter_path / "meta.json"
        
        if meta_path.exists():
            meta = self.file_manager.load_content(meta_path)
        else:
            meta = {
                "chapter_num": chapter_num,
                "title": "",
                "status": "draft",
                "word_count": len(content),
                "character_states": {},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        
        meta["critique_score"] = review_result.get("score", 50)
        meta["critique_comments"] = review_result.get("comments", "")
        meta["updated_at"] = datetime.now().isoformat()
        
        self.file_manager.save_content(meta_path, meta)
        
        return state
    
    def run(self, initial_state: AgentState, update_callback=None) -> AgentState:
        if update_callback:
            final_state = initial_state
            for event in self.graph.stream(initial_state):
                for node_name, node_state in event.items():
                    if update_callback:
                        update_callback(node_name, node_state)
                    final_state = node_state
            return final_state
        else:
            return self.graph.invoke(initial_state)


class BatchProcessor:
    def __init__(
        self,
        workflow: ImportWorkflow,
        file_manager: ProjectManager,
        max_workers: int = 20
    ):
        self.workflow = workflow
        self.file_manager = file_manager
        self.max_workers = max_workers
        self.results_lock = threading.Lock()
    
    def _process_single_chapter(
        self,
        novel_name: str,
        chapter_num: int,
        update_callback=None
    ) -> dict:
        initial_state: AgentState = {
            "novel_name": novel_name,
            "chapter_num": chapter_num,
            "outline": None,
            "draft_content": None,
            "critique_comments": None,
            "critique_score": None,
            "revision_count": 0,
            "reference_context": None,
            "character_bios": None,
            "world_setting": None,
            "reference_style": None,
            "character_updates": {},
            "previous_context": None,
            "status": "processing",
            "current_node": None
        }
        
        try:
            if update_callback:
                def chapter_callback(node_name, node_state):
                    update_callback(novel_name, chapter_num, node_name, node_state)
                final_state = self.workflow.run(initial_state, chapter_callback)
            else:
                final_state = self.workflow.run(initial_state)
            
            return {
                "chapter_num": chapter_num,
                "status": "success",
                "score": final_state.get("critique_score"),
                "outline": final_state.get("outline")
            }
        except Exception as e:
            return {
                "chapter_num": chapter_num,
                "status": "error",
                "error": str(e)
            }
    
    def process_all_chapters(
        self,
        novel_name: str,
        update_callback=None
    ) -> list:
        chapter_nums = self.file_manager.list_chapters(novel_name)
        
        if not chapter_nums:
            return []
        
        results = []
        results_dict = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chapter = {
                executor.submit(
                    self._process_single_chapter,
                    novel_name,
                    chapter_num,
                    update_callback
                ): chapter_num
                for chapter_num in chapter_nums
            }
            
            for future in as_completed(future_to_chapter):
                chapter_num = future_to_chapter[future]
                try:
                    result = future.result()
                    results_dict[chapter_num] = result
                except Exception as e:
                    results_dict[chapter_num] = {
                        "chapter_num": chapter_num,
                        "status": "error",
                        "error": f"执行异常: {str(e)}"
                    }
        
        results = [results_dict[ch_num] for ch_num in chapter_nums]
        return results
