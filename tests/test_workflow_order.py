"""
测试工作流执行顺序，确保审稿节点被正确执行
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

from src.core.state import AgentState
from src.workflow.graph import NovelWorkflow
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_workflow_order():
    """测试工作流执行顺序"""
    print("=" * 60)
    print("测试工作流执行顺序")
    print("=" * 60)
    
    from src.core.config import Settings
    from src.core.llm import LLMClient
    from src.utils.file_manager import ProjectManager
    from src.agents.builder import WorldBuilder
    from src.agents.novelist import Novelist
    from src.agents.editor import ChiefEditor, Critic
    from src.rag.retriever import VectorRetriever
    from src.rag.indexer import VectorIndexer
    
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    
    llm_client = LLMClient(
        provider=config.model.provider,
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    
    file_manager = ProjectManager(Path(config.paths.workspace))
    
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
    
    executed_nodes = []
    
    def track_node(node_name: str, node_state: AgentState):
        executed_nodes.append(node_name)
        print(f"  → 节点执行: {node_name}")
        if node_name == "critic":
            score = node_state.get("critique_score")
            comments = node_state.get("critique_comments", "")
            print(f"     审稿评分: {score}, 审稿意见长度: {len(comments)}")
    
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
    
    try:
        print("\n开始执行工作流...")
        result = workflow.run(initial_state, update_callback=track_node)
        
        print(f"\n执行的节点顺序: {' -> '.join(executed_nodes)}")
        
        expected_order = ["world_builder", "novelist", "critic", "publisher"]
        actual_order = executed_nodes[:len(expected_order)]
        
        if actual_order == expected_order:
            print("✓ 节点执行顺序正确")
        else:
            print(f"❌ 节点执行顺序错误！")
            print(f"  期望: {' -> '.join(expected_order)}")
            print(f"  实际: {' -> '.join(executed_nodes)}")
            return False
        
        if "critic" not in executed_nodes:
            print("❌ 审稿节点未被执行！")
            return False
        
        final_score = result.get("critique_score")
        final_comments = result.get("critique_comments", "")
        
        if final_score is None:
            print("❌ 最终状态中没有审稿评分！")
            return False
        
        if len(final_comments) == 0:
            print("❌ 最终状态中没有审稿意见！")
            return False
        
        print(f"✓ 审稿评分: {final_score}")
        print(f"✓ 审稿意见长度: {len(final_comments)}")
        
        print("\n" + "=" * 60)
        print("测试通过！工作流执行顺序正确，审稿节点正常工作")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        print(f"执行的节点: {' -> '.join(executed_nodes) if executed_nodes else '无'}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_workflow_order()
