"""
模型切换工具

快速切换项目使用的模型预设。
"""

import os
import sys
import argparse
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import Settings


def list_presets(config_path: Path = None):
    """列出所有可用的模型预设"""
    if config_path is None:
        config_path = project_root / "config" / "settings.yaml"
    
    settings = Settings.load_from_yaml(config_path)
    presets = settings.get_available_presets()
    
    print("=" * 60)
    print("可用的模型预设")
    print("=" * 60)
    
    if not presets:
        print("❌ 未找到模型预设配置")
        return
    
    for name, config in presets.items():
        current = " (当前)" if settings.model.name == config.get("name") else ""
        print(f"\n📌 {name}{current}")
        print(f"   模型: {config.get('name')}")
        print(f"   提供商: {config.get('provider')}")
        print(f"   温度: {config.get('temperature')}")
        print(f"   最大 tokens: {config.get('max_tokens')}")
        if config.get('description'):
            print(f"   描述: {config.get('description')}")
    
    print("\n" + "=" * 60)
    print(f"当前使用: {settings.model.name}")
    print("=" * 60)


def switch_preset(preset_name: str, config_path: Path = None, set_env: bool = True):
    """
    切换到指定的模型预设
    
    Args:
        preset_name: 预设名称
        config_path: 配置文件路径
        set_env: 是否设置环境变量
    """
    if config_path is None:
        config_path = project_root / "config" / "settings.yaml"
    
    settings = Settings.load_from_yaml(config_path)
    presets = settings.get_available_presets()
    
    if not presets or preset_name not in presets:
        print(f"❌ 错误: 未找到预设 '{preset_name}'")
        print("\n可用的预设:")
        for name in presets.keys():
            print(f"  - {name}")
        return False
    
    preset_config = presets[preset_name]
    
    if set_env:
        # 设置环境变量（仅对当前进程有效）
        os.environ["MODEL_PRESET"] = preset_name
        os.environ["DEFAULT_MODEL"] = preset_config["name"]
        os.environ["DEFAULT_PROVIDER"] = preset_config["provider"]
        os.environ["DEFAULT_TEMPERATURE"] = str(preset_config["temperature"])
        
        print("=" * 60)
        print(f"✅ 已切换到模型预设: {preset_name}")
        print("=" * 60)
        print(f"模型: {preset_config['name']}")
        print(f"提供商: {preset_config['provider']}")
        print(f"温度: {preset_config['temperature']}")
        print(f"最大 tokens: {preset_config['max_tokens']}")
        if preset_config.get('description'):
            print(f"描述: {preset_config['description']}")
        print("\n💡 提示: 环境变量仅对当前进程有效。")
        print("   要在新进程中生效，请运行:")
        print(f"   $env:MODEL_PRESET=\"{preset_name}\"  # PowerShell")
        print(f"   set MODEL_PRESET={preset_name}  # CMD")
    else:
        print(f"✅ 预设 '{preset_name}' 配置:")
        for key, value in preset_config.items():
            print(f"  {key}: {value}")
    
    return True


def show_current(config_path: Path = None):
    """显示当前使用的模型配置"""
    if config_path is None:
        config_path = project_root / "config" / "settings.yaml"
    
    settings = Settings.load_from_yaml(config_path)
    
    print("=" * 60)
    print("当前模型配置")
    print("=" * 60)
    print(f"模型: {settings.model.name}")
    print(f"提供商: {settings.model.provider}")
    print(f"温度: {settings.model.temperature}")
    print(f"最大 tokens: {settings.model.max_tokens}")
    if settings.model.description:
        print(f"描述: {settings.model.description}")
    
    # 检查环境变量
    env_preset = os.getenv("MODEL_PRESET")
    if env_preset:
        print(f"\n环境变量 MODEL_PRESET: {env_preset}")
    else:
        print("\n环境变量 MODEL_PRESET: 未设置（使用配置文件默认值）")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Novel-Agent 模型切换工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出所有可用预设
  python tools/switch_model.py list
  
  # 切换到 mythomax 预设
  python tools/switch_model.py switch mythomax
  
  # 显示当前配置
  python tools/switch_model.py current
  
  # 通过环境变量切换（PowerShell）
  $env:MODEL_PRESET="qwen"
  python tools/switch_model.py current
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # list 命令
    list_parser = subparsers.add_parser("list", help="列出所有可用的模型预设")
    list_parser.add_argument(
        "--config",
        type=Path,
        default=project_root / "config" / "settings.yaml",
        help="配置文件路径"
    )
    
    # switch 命令
    switch_parser = subparsers.add_parser("switch", help="切换到指定的模型预设")
    switch_parser.add_argument(
        "preset",
        help="预设名称"
    )
    switch_parser.add_argument(
        "--config",
        type=Path,
        default=project_root / "config" / "settings.yaml",
        help="配置文件路径"
    )
    switch_parser.add_argument(
        "--no-env",
        action="store_true",
        help="不设置环境变量，仅显示配置"
    )
    
    # current 命令
    current_parser = subparsers.add_parser("current", help="显示当前使用的模型配置")
    current_parser.add_argument(
        "--config",
        type=Path,
        default=project_root / "config" / "settings.yaml",
        help="配置文件路径"
    )
    
    args = parser.parse_args()
    
    if args.command == "list":
        list_presets(args.config)
    elif args.command == "switch":
        switch_preset(args.preset, args.config, not args.no_env)
    elif args.command == "current":
        show_current(args.config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
