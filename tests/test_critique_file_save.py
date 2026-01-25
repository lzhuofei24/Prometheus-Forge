"""
测试审稿文件是否正确保存
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
from src.agents.editor import Critic, ChiefEditor
from src.workflow.graph import NovelWorkflow
from src.rag.retriever import VectorRetriever
from src.rag.indexer import VectorIndexer
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_critique_file_save():
    """测试审稿文件是否正确保存"""
    print("=" * 60)
    print("测试审稿文件保存")
    print("=" * 60)
    
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
    
    test_novel = "测试小说"
    test_chapter = 999
    
    chapter_path = file_manager.get_chapter_path(test_novel, test_chapter)
    critique_path = chapter_path / "critique.md"
    meta_path = chapter_path / "meta.json"
    
    if critique_path.exists():
        critique_path.unlink()
        print(f"删除已存在的 critique.md: {critique_path}")
    
    initial_state: AgentState = {
        "novel_name": test_novel,
        "chapter_num": test_chapter,
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
        result = workflow.run(initial_state, update_callback=None)
        
        print(f"\n工作流执行完成")
        print(f"最终状态中的 critique_score: {result.get('critique_score')}")
        print(f"最终状态中的 critique_comments 长度: {len(result.get('critique_comments', ''))}")
        
        if critique_path.exists():
            print(f"\n✓ critique.md 文件已创建: {critique_path}")
            content = file_manager.load_content(critique_path)
            print(f"文件内容长度: {len(content)}")
            print(f"文件内容前200字符:\n{content[:200]}")
            
            if "审稿意见" in content:
                print("✓ 文件包含 '审稿意见' 标题")
            else:
                print("❌ 文件不包含 '审稿意见' 标题")
                return False
            
            if result.get('critique_comments') and result.get('critique_comments') in content:
                print("✓ 文件包含审稿意见内容")
            else:
                print("⚠️  文件内容可能与状态中的审稿意见不一致")
        else:
            print(f"\n❌ critique.md 文件未创建: {critique_path}")
            print(f"章节路径是否存在: {chapter_path.exists()}")
            if chapter_path.exists():
                print(f"章节路径中的文件: {list(chapter_path.iterdir())}")
            return False
        
        if meta_path.exists():
            meta = file_manager.load_content(meta_path)
            if "critique_score" in meta:
                print(f"✓ meta.json 包含 critique_score: {meta.get('critique_score')}")
            else:
                print("⚠️  meta.json 不包含 critique_score")
            
            if "critique_comments" in meta:
                print(f"✓ meta.json 包含 critique_comments (长度: {len(meta.get('critique_comments', ''))})")
            else:
                print("⚠️  meta.json 不包含 critique_comments")
        
        print("\n" + "=" * 60)
        print("测试通过！审稿文件保存正常")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_critique_file_save()
