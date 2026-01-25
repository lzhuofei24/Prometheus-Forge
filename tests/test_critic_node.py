"""
测试审稿节点是否被正确执行
"""
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_IMPL"] = "chromadb.telemetry.posthog.Posthog"
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv()

from src.core.config import Settings
from src.core.llm import LLMClient
from src.core.state import AgentState
from src.utils.file_manager import ProjectManager
from src.agents.builder import WorldBuilder
from src.agents.novelist import Novelist
from src.agents.editor import Critic
from src.workflow.graph import NovelWorkflow
from src.agents.editor import ChiefEditor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_critic_node_execution():
    """测试审稿节点是否被正确执行"""
    print("=" * 60)
    print("测试审稿节点执行")
    print("=" * 60)
    
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    
    llm_client = LLMClient(
        provider=config.model.provider,
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    
    file_manager = ProjectManager(Path(config.paths.workspace))
    
    from src.rag.retriever import VectorRetriever
    from src.rag.indexer import VectorIndexer
    
    retriever = None
    try:
        indexer = VectorIndexer(
            persist_directory=Path(config.paths.chroma_db),
            collection_name="novel_chunks"
        )
        retriever = VectorRetriever(indexer.collection)
    except:
        pass
    
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
    
    initial_state: AgentState = {
        "novel_name": "测试小说",
        "chapter_num": 999,
        "outline": "测试大纲：主角遇到困难，最终解决。",
        "draft_content": "这是测试正文内容。主角遇到了困难，但最终解决了问题。",
        "critique_comments": None,
        "critique_score": None,
        "revision_count": 0,
        "reference_context": "测试参考上下文",
        "character_bios": None,
        "world_setting": None,
        "reference_style": None,
        "character_updates": {},
        "previous_context": None,
        "status": "draft",
        "current_node": None
    }
    
    executed_nodes = []
    
    def update_callback(node_name: str, node_state: AgentState):
        executed_nodes.append(node_name)
        logger.info(f"节点执行: {node_name}")
        if node_name == "critic":
            score = node_state.get("critique_score")
            comments = node_state.get("critique_comments", "")
            logger.info(f"审稿结果: score={score}, comments长度={len(comments)}")
    
    try:
        logger.info("开始执行工作流")
        result = workflow.run(initial_state, update_callback=update_callback)
        
        print(f"\n执行的节点顺序: {' -> '.join(executed_nodes)}")
        
        assert "critic" in executed_nodes, "审稿节点未被执行！"
        print("✓ 审稿节点已执行")
        
        final_score = result.get("critique_score")
        final_comments = result.get("critique_comments", "")
        
        assert final_score is not None, "审稿评分未生成！"
        print(f"✓ 审稿评分: {final_score}")
        
        assert len(final_comments) > 0, "审稿意见未生成！"
        print(f"✓ 审稿意见长度: {len(final_comments)}")
        
        print("\n" + "=" * 60)
        print("测试通过！审稿节点正常工作")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_critic_node_execution()
