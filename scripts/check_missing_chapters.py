from pathlib import Path
import sys
from dotenv import load_dotenv

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

from src.core.config import Settings
from src.utils.file_manager import ProjectManager
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    novel_name = "史莱姆契约公主"
    
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    workspace_root = Path(config.paths.workspace)
    file_manager = ProjectManager(workspace_root)
    
    chapters = file_manager.list_chapters(novel_name)
    logger.info(f"共找到 {len(chapters)} 个章节")
    
    missing_chapters = []
    problematic_chapters = []
    
    for chapter_num in sorted(chapters):
        chapter_path = file_manager.get_chapter_path(novel_name, chapter_num)
        extraction_path = chapter_path / "extraction.json"
        outline_path = chapter_path / "outline.md"
        meta_path = chapter_path / "meta.json"
        
        missing = []
        problems = []
        
        if not extraction_path.exists():
            missing.append("extraction.json")
        elif extraction_path.stat().st_size < 50:
            problems.append("extraction.json 内容过短")
        
        if not outline_path.exists():
            missing.append("outline.md")
        elif outline_path.stat().st_size < 50:
            problems.append("outline.md 内容过短")
        
        if not meta_path.exists():
            missing.append("meta.json")
        else:
            try:
                meta = file_manager.load_content(meta_path)
                if not meta.get("critique_score") and not meta.get("critique_comments"):
                    problems.append("meta.json 缺少审阅信息")
            except:
                problems.append("meta.json 解析失败")
        
        if missing:
            missing_chapters.append({
                "chapter_num": chapter_num,
                "missing": missing
            })
            logger.warning(f"章节 {chapter_num} 缺少: {', '.join(missing)}")
        elif problems:
            problematic_chapters.append({
                "chapter_num": chapter_num,
                "problems": problems
            })
            logger.warning(f"章节 {chapter_num} 有问题: {', '.join(problems)}")
    
    all_problematic = missing_chapters + problematic_chapters
    
    if all_problematic:
        logger.info(f"\n共 {len(all_problematic)} 个章节需要重新处理:")
        for item in all_problematic:
            if "missing" in item:
                logger.info(f"  章节 {item['chapter_num']}: 缺少 {', '.join(item['missing'])}")
            else:
                logger.info(f"  章节 {item['chapter_num']}: {', '.join(item['problems'])}")
        return [item["chapter_num"] for item in all_problematic]
    else:
        logger.info("所有章节都已处理完成！")
        return []


if __name__ == "__main__":
    missing = main()
    if missing:
        print(f"\n需要处理的章节: {missing}")
