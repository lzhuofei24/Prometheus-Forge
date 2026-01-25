import os
import subprocess
from pathlib import Path

model_name = "BAAI/bge-small-zh-v1.5"
cache_dir = Path.home() / ".cache" / "huggingface" / "hub"

print(f"正在手动下载模型: {model_name}")
print(f"目标目录: {cache_dir}")

mirror_url = f"https://hf-mirror.com/{model_name}"
official_url = f"https://huggingface.co/{model_name}"

print("\n方法1: 使用 git clone (推荐)")
print(f"  git clone {mirror_url}")

print("\n方法2: 使用 huggingface-cli")
print("  1. 安装: pip install huggingface_hub")
print(f"  2. 下载: huggingface-cli download {model_name}")

print("\n方法3: 使用 Python 代码")
print("""
from huggingface_hub import snapshot_download
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
snapshot_download(repo_id="BAAI/bge-small-zh-v1.5", local_dir="./models/bge-small-zh-v1.5")
""")

print("\n下载完成后，模型会自动缓存到:")
print(f"  {cache_dir}")
