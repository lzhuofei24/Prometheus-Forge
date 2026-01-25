import os
import shutil
import time
from pathlib import Path

project_root = Path(__file__).parent
chroma_db_path = project_root / "data" / "chroma_db"

if chroma_db_path.exists():
    print(f"正在删除旧的 ChromaDB 数据: {chroma_db_path}")
    try:
        shutil.rmtree(chroma_db_path)
        print("✅ 旧数据已清理完成")
    except PermissionError as e:
        print("❌ 删除失败：文件被占用")
        print("\n请先关闭以下进程：")
        print("  1. Streamlit 应用（如果正在运行）")
        print("  2. Celery Workers（如果正在运行）")
        print("  3. 任何使用 ChromaDB 的 Python 进程")
        print("\n然后手动删除文件夹：")
        print(f"  {chroma_db_path}")
        print("\n或者重启电脑后再次运行此脚本")
        exit(1)
    except Exception as e:
        print(f"❌ 删除失败: {e}")
        exit(1)
else:
    print(f"✅ ChromaDB 数据目录不存在: {chroma_db_path}，无需清理")

print("\n提示：系统将在下次运行时使用新的 BGE 中文模型重建数据库")
