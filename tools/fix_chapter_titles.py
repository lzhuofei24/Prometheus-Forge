import sys
from pathlib import Path
import json

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.file_manager import ProjectManager
from src.core.config import Settings

def fix_chapter_titles():
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    file_manager = ProjectManager(Path(config.paths.workspace))
    
    workspace_root = Path(config.paths.workspace)
    novels = []
    
    for item in workspace_root.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            if (item / "chapters").exists():
                novels.append(item.name)
    
    for novel_name in novels:
        chapters = file_manager.list_chapters(novel_name)
        
        for chapter_num in chapters:
            chapter_path = file_manager.get_chapter_path(novel_name, chapter_num)
            meta_path = chapter_path / "meta.json"
            
            if not meta_path.exists():
                continue
            
            meta = file_manager.load_content(meta_path)
            title = meta.get("title", "")
            
            if not title:
                meta["title"] = f"第{chapter_num}章"
                file_manager.save_content(meta_path, meta)
                print(f"修复: {novel_name} 第{chapter_num}章 - 添加默认标题")
            elif not title.startswith("第"):
                meta["title"] = f"第{chapter_num}章 {title}"
                file_manager.save_content(meta_path, meta)
                print(f"修复: {novel_name} 第{chapter_num}章 - 标题改为: {meta['title']}")
            elif not title.startswith(f"第{chapter_num}章"):
                title_part = title.replace("第", "").split("章")[1] if "章" in title else title
                meta["title"] = f"第{chapter_num}章 {title_part.strip()}"
                file_manager.save_content(meta_path, meta)
                print(f"修复: {novel_name} 第{chapter_num}章 - 标题改为: {meta['title']}")

if __name__ == "__main__":
    fix_chapter_titles()
    print("修复完成！")
