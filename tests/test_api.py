"""
API 测试脚本

测试 OpenRouter API 调用是否成功，验证配置是否正确。
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 尝试加载 .env 文件（如果安装了 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✓ 使用 python-dotenv 加载环境变量")
except ImportError:
    print("⚠ python-dotenv 未安装，将直接从环境变量读取")
    print("  提示：可以运行 'pip install python-dotenv' 安装")

from src.core.llm import LLMClient

# 尝试导入 logger（可选）
try:
    from src.core.logger import setup_logger
    logger = setup_logger()
except ImportError:
    import logging
    logger = logging.getLogger("test")
    logger.setLevel(logging.INFO)


def test_direct_api():
    """直接使用 OpenAI SDK 测试"""
    print("\n" + "=" * 50)
    print("测试 1: 直接使用 OpenAI SDK 调用 OpenRouter")
    print("=" * 50)
    
    from openai import OpenAI
    import httpx
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    
    if not api_key:
        print("❌ 错误: 未找到 OPENROUTER_API_KEY 环境变量")
        return False
    
    print(f"✓ API Key: {api_key[:20]}...")
    print(f"✓ Base URL: {base_url}")
    
    # 检查代理设置
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if http_proxy or https_proxy:
        print(f"⚠️  检测到代理设置: HTTP_PROXY={http_proxy}, HTTPS_PROXY={https_proxy}")
    
    try:
        # 配置 HTTP 客户端，增加超时和重试
        http_client = httpx.Client(
            timeout=60.0,
            verify=True,
        )
        
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            http_client=http_client,
        )
        
        print("\n🚀 正在调用 MythoMax-13B...")
        
        completion = client.chat.completions.create(
            model="gryphe/mythomax-l2-13b",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的小说创作助手，擅长描写细腻的场景和人物。"
                },
                {
                    "role": "user",
                    "content": "请用100字左右描写一个剑客走进废弃古庙的场景，要求细节丰富、氛围感强。"
                }
            ],
            temperature=0.8,
            extra_headers={
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "Novel-Agent-Test"
            },
        )
        
        print("\n✅ API 调用成功！")
        print("-" * 50)
        print("模型回复：")
        print("-" * 50)
        print(completion.choices[0].message.content)
        print("-" * 50)
        return True
        
    except Exception as e:
        print(f"\n❌ API 调用失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        
        # 提供诊断建议
        if "SSL" in str(e) or "EOF" in str(e):
            print("\n💡 诊断建议：")
            print("   1. 检查网络连接是否正常")
            print("   2. 检查是否有防火墙或代理拦截")
            print("   3. 尝试禁用代理：取消设置 HTTP_PROXY 和 HTTPS_PROXY")
            print("   4. 检查 SSL 证书是否过期")
            print("   5. 如果在公司网络，可能需要配置代理")
            print("   6. 运行: python tools/diagnose_network.py")
        
        import traceback
        traceback.print_exc()
        return False


def test_llm_client():
    """使用项目的 LLMClient 类测试"""
    print("\n" + "=" * 50)
    print("测试 2: 使用项目的 LLMClient 类")
    print("=" * 50)
    
    try:
        # 初始化 LLMClient（会自动从环境变量读取配置）
        llm_client = LLMClient(
            provider="openrouter",
            model="gryphe/mythomax-l2-13b"
        )
        
        print(f"✓ Provider: {llm_client.provider}")
        print(f"✓ Model: {llm_client.model}")
        print(f"✓ Base URL: {llm_client.client.base_url}")
        
        print("\n🚀 正在调用 LLMClient...")
        
        messages = [
            {
                "role": "system",
                "content": "你是一个专业的小说创作助手，擅长描写细腻的场景和人物。"
            },
            {
                "role": "user",
                "content": "请用100字左右描写一个剑客走进废弃古庙的场景，要求细节丰富、氛围感强。"
            }
        ]
        
        response = llm_client.chat(
            messages=messages,
            temperature=0.8,
            max_tokens=200
        )
        
        print("\n✅ LLMClient 调用成功！")
        print("-" * 50)
        print("模型回复：")
        print("-" * 50)
        print(response)
        print("-" * 50)
        return True
        
    except Exception as e:
        print(f"\n❌ LLMClient 调用失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        
        # 提供诊断建议
        if "SSL" in str(e) or "EOF" in str(e):
            print("\n💡 诊断建议：")
            print("   1. 检查网络连接是否正常")
            print("   2. 检查是否有防火墙或代理拦截")
            print("   3. 尝试禁用代理：取消设置 HTTP_PROXY 和 HTTPS_PROXY")
            print("   4. 检查 SSL 证书是否过期")
            print("   5. 如果在公司网络，可能需要配置代理")
            print("   6. 运行: python tools/diagnose_network.py")
        
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("=" * 50)
    print("Novel-Agent API 测试")
    print("=" * 50)
    
    # 检查环境变量
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE")
    
    print(f"\n环境变量检查：")
    print(f"  OPENROUTER_API_KEY: {'✓ 已设置' if api_key else '❌ 未设置'}")
    print(f"  OPENAI_API_BASE: {base_url if base_url else '❌ 未设置（将使用默认值）'}")
    
    # 检查代理设置
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if http_proxy or https_proxy:
        print(f"  HTTP_PROXY: {http_proxy}")
        print(f"  HTTPS_PROXY: {https_proxy}")
        print("  ⚠️  检测到代理设置，如果连接失败，可能需要配置正确的代理")
    else:
        print("  代理设置: 未检测到")
    
    if not api_key:
        print("\n❌ 错误: 请先设置 OPENROUTER_API_KEY 环境变量")
        print("   方法1: 创建 .env 文件并填入 API Key")
        print("   方法2: 在系统环境变量中设置")
        return
    
    # 运行测试
    test1_result = test_direct_api()
    test2_result = test_llm_client()
    
    # 总结
    print("\n" + "=" * 50)
    print("测试总结")
    print("=" * 50)
    print(f"直接 API 调用: {'✅ 通过' if test1_result else '❌ 失败'}")
    print(f"LLMClient 调用: {'✅ 通过' if test2_result else '❌ 失败'}")
    
    if test1_result and test2_result:
        print("\n🎉 所有测试通过！API 配置正确。")
    else:
        print("\n⚠️  部分测试失败，请检查配置和网络连接。")


if __name__ == "__main__":
    main()
