from pathlib import Path
import sys
from dotenv import load_dotenv

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

from src.core.config import Settings
from src.core.llm import LLMClient
from src.agents.novelist import Novelist
from src.agents.editor import Critic
from src.utils.file_manager import ProjectManager
from src.workflow.import_graph import ImportWorkflow, BatchProcessor
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    novel_name = "史莱姆契约公主"
    failed_chapters = [66, 70, 71, 72, 73]
    
    logger.info(f"开始重新处理小说《{novel_name}》的失败章节: {failed_chapters}")
    
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    workspace_root = Path(config.paths.workspace)
    
    llm_client = LLMClient(
        provider=config.model.provider,
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    
    file_manager = ProjectManager(workspace_root)
    novelist = Novelist(llm_client, file_manager)
    critic = Critic(llm_client, file_manager)
    
    workflow = ImportWorkflow(novelist, critic, file_manager, llm_client)
    processor = BatchProcessor(workflow, file_manager, max_workers=20)
    
    def progress_callback(novel, chapter_num, node_name, node_state):
        logger.info(f"处理章节 {chapter_num} - 节点: {node_name}")
        if node_name == "extract":
            extraction = node_state.get("extraction", {})
            if extraction:
                chars = extraction.get("characters", [])
                logger.info(f"  提取到 {len(chars)} 个人物")
        elif node_name == "outline":
            outline = node_state.get("outline", "")
            if outline:
                preview = outline[:100] + "..." if len(outline) > 100 else outline
                logger.info(f"  大纲预览: {preview}")
        elif node_name == "review":
            score = node_state.get("critique_score", 0)
            logger.info(f"  审阅评分: {score} 分")
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    results = []
    results_dict = {}
    
    logger.info("开始批量处理（异步，最多20个并发）...")
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_chapter = {
            executor.submit(
                processor._process_single_chapter,
                novel_name,
                chapter_num,
                progress_callback
            ): chapter_num
            for chapter_num in failed_chapters
        }
        
        for future in as_completed(future_to_chapter):
            chapter_num = future_to_chapter[future]
            try:
                result = future.result()
                results_dict[chapter_num] = result
                logger.info(f"✅ 章节 {chapter_num} 处理完成")
            except Exception as e:
                results_dict[chapter_num] = {
                    "chapter_num": chapter_num,
                    "status": "error",
                    "error": f"执行异常: {str(e)}"
                }
                logger.error(f"❌ 章节 {chapter_num} 处理失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
    
    results = [results_dict[ch_num] for ch_num in failed_chapters]
    
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = sum(1 for r in results if r.get("status") == "error")
    
    logger.info(f"\n处理完成！")
    logger.info(f"成功: {success_count} 章")
    logger.info(f"失败: {error_count} 章")
    
    if error_count > 0:
        logger.warning("失败的章节：")
        for r in results:
            if r.get("status") == "error":
                logger.warning(f"  章节 {r.get('chapter_num')}: {r.get('error')}")
    
    logger.info("\n处理结果摘要：")
    for r in results:
        if r.get("status") == "success":
            score = r.get("score", "N/A")
            logger.info(f"  章节 {r.get('chapter_num')}: 评分 {score}")


if __name__ == "__main__":
    main()
