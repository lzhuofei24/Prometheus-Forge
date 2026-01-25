"""
预下载嵌入模型到本地 models 文件夹

使用方式：
python scripts/download_embedding_model.py
"""

import os
from pathlib import Path
import sys

# 设置项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置模型缓存目录
models_dir = project_root / "models"
models_dir.mkdir(exist_ok=True)

os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(models_dir)
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "300"

print(f"📦 模型将下载到: {models_dir.absolute()}")
print("=" * 60)

from sentence_transformers import SentenceTransformer

model_name = "BAAI/bge-small-zh-v1.5"

print(f"🚀 开始下载模型: {model_name}")
print("📝 说明: 首次下载约 95MB，请耐心等待...")
print("=" * 60)

try:
    model = SentenceTransformer(model_name)
    print("\n" + "=" * 60)
    print("✅ 模型下载成功！")
    print(f"📂 模型位置: {models_dir.absolute()}")
    print("=" * 60)
    
    # 测试模型
    print("\n🧪 测试模型...")
    test_text = "这是一个测试句子"
    embedding = model.encode(test_text)
    print(f"✅ 模型测试成功！向量维度: {len(embedding)}")
    
except Exception as e:
    print("\n" + "=" * 60)
    print(f"❌ 下载失败: {e}")
    print("=" * 60)
    import traceback
    traceback.print_exc()
    sys.exit(1)
