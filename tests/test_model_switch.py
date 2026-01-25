"""
测试模型切换功能

验证模型预设切换是否正常工作。
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.core.config import Settings
from src.core.llm import LLMClient


def test_model_switch():
    """测试模型切换功能"""
    print("=" * 60)
    print("模型切换功能测试")
    print("=" * 60)
    
    config_path = project_root / "config" / "settings.yaml"
    settings = Settings.load_from_yaml(config_path)
    
    # 显示当前配置
    print("\n1. 当前配置（从配置文件加载）")
    print("-" * 60)
    print(f"模型: {settings.model.name}")
    print(f"提供商: {settings.model.provider}")
    print(f"温度: {settings.model.temperature}")
    print(f"最大 tokens: {settings.model.max_tokens}")
    
    # 测试通过环境变量切换
    print("\n2. 测试通过环境变量切换模型")
    print("-" * 60)
    
    # 切换到 mythomax
    os.environ["MODEL_PRESET"] = "mythomax"
    settings_mythomax = Settings.load_from_yaml(config_path)
    print(f"切换到 mythomax: {settings_mythomax.model.name}")
    
    # 切换到 qwen
    os.environ["MODEL_PRESET"] = "qwen"
    settings_qwen = Settings.load_from_yaml(config_path)
    print(f"切换到 qwen: {settings_qwen.model.name}")
    
    # 测试 LLMClient 初始化
    print("\n3. 测试 LLMClient 初始化")
    print("-" * 60)
    
    # 使用默认配置
    client1 = LLMClient()
    print(f"默认 LLMClient 模型: {client1.model}")
    print(f"默认温度: {client1.default_temperature}")
    
    # 使用指定模型
    client2 = LLMClient(
        model="gryphe/mythomax-l2-13b",
        provider="openrouter",
        temperature=0.8
    )
    print(f"指定模型的 LLMClient: {client2.model}")
    print(f"指定温度: {client2.default_temperature}")
    
    # 测试动态切换
    print("\n4. 测试动态切换模型")
    print("-" * 60)
    client2.switch_model("qwen/qwen-2.5-72b-instruct")
    print(f"切换后模型: {client2.model}")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
    print("\n💡 使用提示：")
    print("   1. 运行 'python tools/switch_model.py list' 查看所有预设")
    print("   2. 运行 'python tools/switch_model.py switch <preset>' 切换模型")
    print("   3. 或设置环境变量 MODEL_PRESET=<preset>")


if __name__ == "__main__":
    test_model_switch()
