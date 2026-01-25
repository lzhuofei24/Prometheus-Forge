"""
简化的 API 测试脚本（使用 requests）

直接使用 requests 库测试 OpenRouter API，绕过可能的 httpx SSL 问题。
"""

import os
import sys
import json
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✓ 使用 python-dotenv 加载环境变量")
except ImportError:
    print("⚠ python-dotenv 未安装，将直接从环境变量读取")

try:
    import requests
except ImportError:
    print("❌ 错误: 需要安装 requests 库")
    print("   运行: pip install requests")
    sys.exit(1)


def test_openrouter_api():
    """使用 requests 直接测试 OpenRouter API"""
    print("=" * 50)
    print("OpenRouter API 测试（使用 requests）")
    print("=" * 50)
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    
    if not api_key:
        print("❌ 错误: 未找到 OPENROUTER_API_KEY 环境变量")
        return False
    
    print(f"\n✓ API Key: {api_key[:20]}...")
    print(f"✓ Base URL: {base_url}")
    
    # 准备请求
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "Novel-Agent-Test"
    }
    
    data = {
        "model": "gryphe/mythomax-l2-13b",
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业的小说创作助手。"
            },
            {
                "role": "user",
                "content": "请用50字左右简单介绍一下你自己。"
            }
        ],
        "temperature": 0.8,
        "max_tokens": 100
    }
    
    try:
        print("\n🚀 正在调用 OpenRouter API...")
        
        # 尝试使用不同的 SSL 配置
        import ssl
        import urllib3
        
        # 禁用 SSL 警告（仅用于测试）
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # 创建自定义 SSL 上下文
        ssl_context = ssl.create_default_context()
        # 尝试使用更宽松的 SSL 设置
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        
        # 使用 requests 的 Session 来更好地控制连接
        session = requests.Session()
        session.verify = True  # 保持 SSL 验证
        
        response = session.post(
            url,
            headers=headers,
            json=data,
            timeout=60
        )
        
        print(f"\n✓ HTTP 状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            print("\n✅ API 调用成功！")
            print("-" * 50)
            print("模型回复：")
            print("-" * 50)
            print(content)
            print("-" * 50)
            return True
        else:
            print(f"\n❌ API 调用失败")
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:500]}")
            return False
            
    except requests.exceptions.SSLError as e:
        print(f"\n❌ SSL 错误: {e}")
        print("\n💡 建议：")
        print("   1. 检查网络连接")
        print("   2. 尝试更新 requests 库: pip install --upgrade requests")
        print("   3. 检查系统时间是否正确")
        print("   4. 运行: python tools/diagnose_network.py")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ 连接错误: {e}")
        print("\n💡 建议：")
        print("   1. 检查网络连接")
        print("   2. 检查防火墙设置")
        print("   3. 如果在公司网络，可能需要配置代理")
        print("   4. 运行: python tools/diagnose_network.py")
        return False
    except requests.exceptions.Timeout:
        print(f"\n❌ 请求超时")
        print("\n💡 建议：增加超时时间或检查网络速度")
        return False
    except Exception as e:
        print(f"\n❌ 未知错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_openrouter_api()
    if success:
        print("\n🎉 测试通过！API 配置正确。")
        print("\n现在可以尝试使用项目的 LLMClient 类了。")
    else:
        print("\n⚠️  测试失败，请检查网络连接和配置。")
