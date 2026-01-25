import os
# 【关键】必须在导入 chromadb 之前设置，强制关闭遥测，防止 Windows 崩溃
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
from src.core.logger import setup_logger
from src.utils.file_manager import ProjectManager
from src.rag.indexer import VectorIndexer
from src.rag.retriever import VectorRetriever
from src.agents.builder import WorldBuilder
from src.agents.novelist import Novelist
from src.agents.editor import ChiefEditor, Critic
from src.workflow.graph import NovelWorkflow

logger = setup_logger()

def init_test_components():
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    
    llm_client = LLMClient(
        provider=config.model.provider,
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    
    file_manager = ProjectManager(Path(config.paths.workspace))
    
    indexer = None
    retriever = None
    try:
        indexer = VectorIndexer(
            persist_directory=Path(config.paths.chroma_db),
            collection_name="novel_chunks"
        )
        retriever = VectorRetriever(indexer.collection)
        logger.info("✓ 向量数据库初始化完成")
    except Exception as e:
        logger.warning(f"向量数据库初始化失败: {e}")
    
    return {
        "llm_client": llm_client,
        "file_manager": file_manager,
        "retriever": retriever
    }
    
def test_world_builder():
    logger.info("=" * 60)
    logger.info("测试 WorldBuilder")
    logger.info("=" * 60)
    
    components = init_test_components()
    world_builder = WorldBuilder(
        llm_client=components["llm_client"],
        retriever=components["retriever"],
        file_manager=components["file_manager"]
    )
    
    state: AgentState = {
        "novel_name": "test_novel",
        "chapter_num": 1,
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
        "status": "draft",
        "current_node": None
    }
    
    state = world_builder.build_context(state)
    
    assert state["reference_context"] is not None
    logger.info(f"✅ WorldBuilder 测试通过")
    logger.info(f"参考上下文长度: {len(state['reference_context'])} 字符")
    logger.info(f"参考上下文预览: {state['reference_context'][:200]}...")
    
    return state


def test_novelist():
    logger.info("=" * 60)
    logger.info("测试 Novelist")
    logger.info("=" * 60)
    
    components = init_test_components()
    novelist = Novelist(
        llm_client=components["llm_client"],
        file_manager=components["file_manager"]
    )
    
    state: AgentState = {
        "novel_name": "test_novel",
        "chapter_num": 1,
        "outline": None,
        "draft_content": None,
        "critique_comments": None,
        "critique_score": None,
        "revision_count": 0,
        "reference_context": "## 人物设定：\n- **测试人物**\n  - 性格：勇敢\n\n## 世界观设定：\n测试世界观\n\n",
        "character_bios": "- **测试人物**\n  - 性格：勇敢",
        "world_setting": "测试世界观",
        "reference_style": None,
        "character_updates": {},
        "previous_context": None,
        "status": "draft",
        "current_node": None
    }
    
    state = novelist.generate_outline(state)
    assert state["outline"] is not None
    logger.info(f"✅ 大纲生成成功")
    logger.info(f"大纲预览: {state['outline'][:200]}...")
    
    state = novelist.generate_draft(state)
    assert state["draft_content"] is not None
    logger.info(f"✅ 正文生成成功")
    logger.info(f"正文长度: {len(state['draft_content'])} 字符")
    logger.info(f"正文预览: {state['draft_content'][:200]}...")
    
    return state


def test_critic():
    logger.info("=" * 60)
    logger.info("测试 Critic")
    logger.info("=" * 60)
    
    components = init_test_components()
    critic = Critic(
        llm_client=components["llm_client"],
        file_manager=components["file_manager"]
    )
    
    state: AgentState = {
        "novel_name": "test_novel",
        "chapter_num": 1,
        "outline": "# 第1章\n\n测试大纲",
        "draft_content": "# 第1章\n\n这是测试正文内容。",
        "critique_comments": None,
        "critique_score": None,
        "revision_count": 0,
        "reference_context": "## 人物设定：\n- **测试人物**\n\n## 世界观设定：\n测试世界观\n\n",
        "character_bios": "- **测试人物**",
        "world_setting": "测试世界观",
        "reference_style": None,
        "character_updates": {},
        "previous_context": None,
        "status": "draft",
        "current_node": None
    }
    
    state = critic.critique(state)
    
    assert state["critique_score"] is not None
    assert state["critique_comments"] is not None
    logger.info(f"✅ Critic 测试通过")
    logger.info(f"评分: {state['critique_score']}")
    logger.info(f"审稿意见: {state['critique_comments'][:200]}...")
    
    should_approve = critic.should_approve(state)
    logger.info(f"是否通过: {should_approve}")
    
    return state


def test_chief_editor():
    logger.info("=" * 60)
    logger.info("测试 ChiefEditor")
    logger.info("=" * 60)
    
    components = init_test_components()
    chief_editor = ChiefEditor(
        llm_client=components["llm_client"],
        file_manager=components["file_manager"]
    )
    
    state: AgentState = {
        "novel_name": "test_novel",
        "chapter_num": 1,
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
        "status": "draft",
        "current_node": None
    }
    
    next_step = chief_editor.plan_next_step(state)
    logger.info(f"✅ ChiefEditor 测试通过")
    logger.info(f"下一步: {next_step}")
    
    return state


def test_full_workflow():
    logger.info("=" * 60)
    logger.info("测试完整工作流")
    logger.info("=" * 60)
    
    components = init_test_components()
    
    world_builder = WorldBuilder(
        llm_client=components["llm_client"],
        retriever=components["retriever"],
        file_manager=components["file_manager"]
    )
    
    novelist = Novelist(
        llm_client=components["llm_client"],
        file_manager=components["file_manager"]
    )
    
    chief_editor = ChiefEditor(
        llm_client=components["llm_client"],
        file_manager=components["file_manager"]
    )
    
    critic = Critic(
        llm_client=components["llm_client"],
        file_manager=components["file_manager"]
    )
    
    workflow = NovelWorkflow(
        world_builder=world_builder,
        novelist=novelist,
        chief_editor=chief_editor,
        critic=critic,
        file_manager=components["file_manager"]
    )
    
    initial_state: AgentState = {
        "novel_name": "test_novel",
        "chapter_num": 1,
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
        "status": "draft",
        "current_node": None
    }
    
    def update_callback(node_name, node_state):
        logger.info(f"  → 节点 {node_name} 执行完成")
        if node_name == "novelist":
            logger.info(f"    大纲长度: {len(node_state.get('outline', ''))}")
            logger.info(f"    正文长度: {len(node_state.get('draft_content', ''))}")
        elif node_name == "critic":
            logger.info(f"    评分: {node_state.get('critique_score', 0)}")
    
    logger.info("开始执行工作流...")
    result = workflow.run(initial_state, update_callback=update_callback)
    
    logger.info(f"✅ 工作流执行完成")
    logger.info(f"最终状态: {result['status']}")
    logger.info(f"重试次数: {result['revision_count']}")
    if result.get("critique_score"):
        logger.info(f"最终评分: {result['critique_score']}")
    
    return result


if __name__ == "__main__":
    try:
        logger.info("开始测试多智能体工作流系统")
        
        logger.info("\n" + "=" * 60)
        logger.info("第一步：测试 WorldBuilder")
        logger.info("=" * 60)
        test_world_builder()
        
        logger.info("\n" + "=" * 60)
        logger.info("第二步：测试 Novelist")
        logger.info("=" * 60)
        test_novelist()
        
        logger.info("\n" + "=" * 60)
        logger.info("第三步：测试 Critic")
        logger.info("=" * 60)
        test_critic()
        
        logger.info("\n" + "=" * 60)
        logger.info("第四步：测试 ChiefEditor")
        logger.info("=" * 60)
        test_chief_editor()
        
        logger.info("\n" + "=" * 60)
        logger.info("第五步：测试完整工作流")
        logger.info("=" * 60)
        test_full_workflow()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ 所有测试完成！")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        sys.exit(1)