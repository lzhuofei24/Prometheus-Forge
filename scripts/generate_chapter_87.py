from pathlib import Path
import sys
from dotenv import load_dotenv
import logging

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

from src.core.config import Settings
from src.core.llm import LLMClient
from src.core.state import AgentState
from src.agents.builder import WorldBuilder
from src.agents.novelist import Novelist
from src.agents.editor import ChiefEditor, Critic
from src.utils.file_manager import ProjectManager
from src.rag.indexer import VectorIndexer
from src.rag.retriever import VectorRetriever
from src.workflow.graph import NovelWorkflow
from src.gui.workflow_executor import WorkflowExecutor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    novel_name = "史莱姆契约公主"
    chapter_num = 87
    
    logger.info(f"开始为小说《{novel_name}》生成第{chapter_num}章...")
    
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    workspace_root = Path(config.paths.workspace)
    
    llm_client = LLMClient(
        provider=config.model.provider,
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    
    file_manager = ProjectManager(workspace_root)
    
    indexer = VectorIndexer(
        persist_directory=Path(config.paths.chroma_db),
        collection_name="novel_chunks"
    )
    
    retriever = VectorRetriever(indexer.collection)
    
    world_builder = WorldBuilder(llm_client, retriever, file_manager)
    novelist = Novelist(llm_client, file_manager)
    chief_editor = ChiefEditor(llm_client, file_manager)
    critic = Critic(llm_client, file_manager)
    
    workflow = NovelWorkflow(
        world_builder=world_builder,
        novelist=novelist,
        chief_editor=chief_editor,
        critic=critic,
        file_manager=file_manager
    )
    
    logger.info("准备初始状态...")
    existing_chapters = file_manager.list_chapters(novel_name)
    previous_chapters = [ch for ch in existing_chapters if ch < chapter_num]
    previous_context = None
    
    if previous_chapters:
        previous_context = []
        for ch_num in previous_chapters[-3:]:
            try:
                ch_path = file_manager.get_chapter_path(novel_name, ch_num)
                outline_path = ch_path / "outline.md"
                if outline_path.exists():
                    outline = file_manager.load_content(outline_path)
                    previous_context.append({
                        "chapter_num": ch_num,
                        "outline": outline[:200] if outline else ""
                    })
            except Exception as e:
                logger.warning(f"加载前文上下文失败 (chapter {ch_num}): {str(e)}")
                continue
    
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
        "previous_context": previous_context,
        "status": "processing",
        "current_node": None
    }
    
    logger.info("开始执行工作流...")
    
    def update_callback(node_name: str, node_state: AgentState, novel_name: str = None, elapsed_time: int = 0):
        node_display = {
            "world_builder": "构建上下文",
            "novelist": "生成内容",
            "critic": "审稿",
            "publisher": "发布"
        }
        display = node_display.get(node_name, node_name)
        logger.info(f"📌 当前节点: {display}")
        
        if node_name == "novelist":
            outline = node_state.get("outline")
            draft = node_state.get("draft_content")
            if outline:
                logger.info(f"   大纲已生成，长度: {len(outline)} 字符")
            if draft:
                logger.info(f"   正文已生成，长度: {len(draft)} 字符")
        elif node_name == "critic":
            score = node_state.get("critique_score")
            if score is not None:
                logger.info(f"   审稿评分: {score} 分")
    
    executor = WorkflowExecutor(workflow)
    result = executor.execute(
        initial_state=initial_state,
        update_callback=update_callback,
        timeout=600
    )
    
    if result.get("success"):
        logger.info("✅ 第87章生成完成！")
        final_state = result.get("result", {})
        logger.info(f"   状态: {final_state.get('status', 'unknown')}")
        logger.info(f"   审稿评分: {final_state.get('critique_score', 'N/A')} 分")
        
        chapter_path = file_manager.get_chapter_path(novel_name, chapter_num)
        content_path = chapter_path / "content.md"
        if content_path.exists():
            content = file_manager.load_content(content_path)
            logger.info(f"   正文字数: {len(content)} 字符")
    else:
        error = result.get("error", "未知错误")
        logger.error(f"❌ 生成失败: {error}")
        if result.get("traceback"):
            logger.error(f"错误堆栈:\n{result['traceback']}")


if __name__ == "__main__":
    main()
