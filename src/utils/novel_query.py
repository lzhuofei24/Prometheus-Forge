from pathlib import Path
from typing import List, Dict, Optional, Any
from .file_manager import ProjectManager


class NovelQuery:
    def __init__(self, workspace_root: Path):
        self.file_manager = ProjectManager(workspace_root)
        self.workspace_root = workspace_root
    
    def list_novels(self) -> List[str]:
        novels = []
        for item in self.workspace_root.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                if (item / "chapters").exists() or (item / "global").exists():
                    novels.append(item.name)
        return sorted(novels)
    
    def get_novel_info(self, novel_name: str) -> Dict[str, Any]:
        novel_path = self.workspace_root / novel_name
        if not novel_path.exists():
            return {}
        
        chapters = self.file_manager.list_chapters(novel_name)
        
        global_path = self.file_manager.get_global_settings_path(novel_name)
        bios = {}
        world = ""
        relations = {}
        
        if (global_path / "bios.json").exists():
            bios = self.file_manager.load_content(global_path / "bios.json")
        if (global_path / "world.md").exists():
            world = self.file_manager.load_content(global_path / "world.md")
        if (global_path / "relation_graph.json").exists():
            relations = self.file_manager.load_content(global_path / "relation_graph.json")
        
        return {
            "name": novel_name,
            "chapters": chapters,
            "chapter_count": len(chapters),
            "bios": bios,
            "world": world,
            "relations": relations
        }
    
    def get_chapter_info(self, novel_name: str, chapter_num: int) -> Dict[str, Any]:
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        if not chapter_path.exists():
            return {}
        
        outline = ""
        content = ""
        critique = ""
        meta = {}
        
        if (chapter_path / "outline.md").exists():
            outline = self.file_manager.load_content(chapter_path / "outline.md")
        if (chapter_path / "content.md").exists():
            content = self.file_manager.load_content(chapter_path / "content.md")
        if (chapter_path / "critique.md").exists():
            critique = self.file_manager.load_content(chapter_path / "critique.md")
        if (chapter_path / "meta.json").exists():
            meta = self.file_manager.load_content(chapter_path / "meta.json")
        
        return {
            "chapter_num": chapter_num,
            "outline": outline,
            "content": content,
            "critique": critique,
            "meta": meta
        }
    
    def get_chapters_summary(self, novel_name: str) -> List[Dict[str, Any]]:
        chapters = self.file_manager.list_chapters(novel_name)
        summary = []
        
        for ch_num in chapters:
            chapter_path = self.file_manager.get_chapter_path(novel_name, ch_num)
            meta = {}
            outline_preview = ""
            
            if (chapter_path / "meta.json").exists():
                meta = self.file_manager.load_content(chapter_path / "meta.json")
            
            if (chapter_path / "outline.md").exists():
                outline = self.file_manager.load_content(chapter_path / "outline.md")
                outline_preview = outline[:100] + "..." if len(outline) > 100 else outline
            
            title = meta.get("title", "")
            if not title:
                title = ""
            
            meta_chapter_num = meta.get("chapter_num", ch_num)
            
            summary.append({
                "chapter_num": meta_chapter_num,
                "title": title,
                "status": meta.get("status", "unknown"),
                "word_count": meta.get("word_count", 0),
                "outline_preview": outline_preview,
                "folder_index": ch_num
            })
        
        return summary
