"""
API 测试脚本（带重试机制）

测试 OpenRouter API 调用，包含重试逻辑和更好的错误处理。
"""

import os
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✓ 使用 python-dotenv 加载环境变量")
except ImportError:
    print("⚠ python-dotenv 未安装，将直接从环境变量读取")

from openai import OpenAI
import httpx

# 尝试导入 requests 作为备选
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("⚠ requests 库未安装，将只使用 httpx")


def test_with_retry(max_retries=3, retry_delay=2):
    """带重试机制的 API 测试"""
    print("=" * 50)
    print("Novel-Agent API 测试（带重试机制）")
    print("=" * 50)
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    
    if not api_key:
        print("❌ 错误: 未找到 OPENROUTER_API_KEY 环境变量")
        return False
    
    print(f"\n✓ API Key: {api_key[:20]}...")
    print(f"✓ Base URL: {base_url}")
    print(f"✓ 最大重试次数: {max_retries}")
    
    # 检查代理
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if http_proxy or https_proxy:
        print(f"⚠️  检测到代理: HTTP={http_proxy}, HTTPS={https_proxy}")
    
    for attempt in range(1, max_retries + 1):
        print(f"\n{'='*50}")
        print(f"尝试 {attempt}/{max_retries}")
        print(f"{'='*50}")
        
        try:
            # 每次尝试都创建新的 HTTP 客户端
            # 尝试不同的配置来解决 SSL 问题
            try:
                http_client = httpx.Client(
                    timeout=60.0,
                    verify=True,
                    # 尝试禁用 HTTP/2（某些情况下可以解决 SSL 问题）
                    http2=False,
                )
            except Exception as e:
                print(f"⚠️  创建 httpx 客户端时出错: {e}")
                # 如果 httpx 有问题，尝试使用默认配置
                http_client = None
            
            if http_client:
                client = OpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    http_client=http_client,
                )
            else:
                # 使用默认 HTTP 客户端
                client = OpenAI(
                    base_url=base_url,
                    api_key=api_key,
                )
            
            print("🚀 正在调用 MythoMax-13B...")
            
            completion = client.chat.completions.create(
                model="gryphe/mythomax-l2-13b",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的小说创作助手。"
                    },
                    {
                        "role": "user",
                        "content": "请用50字左右简单介绍一下你自己。"
                    }
                ],
                temperature=0.8,
                max_tokens=100,
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
            
            # 关闭 HTTP 客户端
            if http_client:
                http_client.close()
            return True
            
        except Exception as e:
            print(f"\n❌ 尝试 {attempt} 失败: {type(e).__name__}")
            print(f"   错误信息: {str(e)[:200]}")
            
            if attempt < max_retries:
                print(f"\n⏳ 等待 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
            else:
                print("\n" + "=" * 50)
                print("所有重试均失败")
                print("=" * 50)
                
                # 详细错误诊断
                if "SSL" in str(e) or "EOF" in str(e):
                    print("\n💡 SSL 错误诊断：")
                    print("   这通常是网络或代理问题导致的。")
                    print("\n   可能的解决方案：")
                    print("   1. 检查网络连接：ping openrouter.ai")
                    print("   2. 如果在公司网络，可能需要配置代理")
                    print("   3. 尝试禁用代理：")
                    print("      set HTTP_PROXY=")
                    print("      set HTTPS_PROXY=")
                    print("   4. 检查防火墙是否阻止了连接")
                    print("   5. 尝试使用 VPN 或更换网络")
                    print("   6. 运行: python tools/diagnose_network.py")
                
                import traceback
                print("\n完整错误堆栈：")
                traceback.print_exc()
                
                # 关闭 HTTP 客户端（如果创建了）
                try:
                    if http_client:
                        http_client.close()
                except:
                    pass
                
                return False
    
    return False


if __name__ == "__main__":
    success = test_with_retry(max_retries=3, retry_delay=2)
    if success:
        print("\n🎉 测试通过！")
    else:
        print("\n⚠️  测试失败，请检查网络连接和配置。")
