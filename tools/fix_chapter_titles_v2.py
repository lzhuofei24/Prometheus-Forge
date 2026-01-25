import sys
from pathlib import Path
import json
import re

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
                meta["title"] = ""
                file_manager.save_content(meta_path, meta)
                print(f"修复: {novel_name} 第{chapter_num}章 - 清空标题")
            else:
                new_title = re.sub(r'^第\d+章\s*', '', title).strip()
                if new_title != title:
                    meta["title"] = new_title
                    file_manager.save_content(meta_path, meta)
                    print(f"修复: {novel_name} 第{chapter_num}章 - 标题改为: '{new_title}'")

if __name__ == "__main__":
    fix_chapter_titles()
    print("修复完成！")
