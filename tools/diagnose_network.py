"""
网络连接诊断脚本

帮助诊断 OpenRouter API 连接问题。
"""

import os
import sys
import socket
import ssl
from pathlib import Path
from urllib.parse import urlparse

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def test_dns():
    """测试 DNS 解析"""
    print("=" * 50)
    print("1. DNS 解析测试")
    print("=" * 50)
    try:
        hostname = "openrouter.ai"
        ip = socket.gethostbyname(hostname)
        print(f"✓ {hostname} -> {ip}")
        return True
    except Exception as e:
        print(f"❌ DNS 解析失败: {e}")
        return False


def test_tcp_connection():
    """测试 TCP 连接"""
    print("\n" + "=" * 50)
    print("2. TCP 连接测试")
    print("=" * 50)
    try:
        hostname = "openrouter.ai"
        port = 443
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((hostname, port))
        sock.close()
        
        if result == 0:
            print(f"✓ 可以连接到 {hostname}:{port}")
            return True
        else:
            print(f"❌ 无法连接到 {hostname}:{port} (错误代码: {result})")
            return False
    except Exception as e:
        print(f"❌ TCP 连接失败: {e}")
        return False


def test_ssl_handshake():
    """测试 SSL 握手"""
    print("\n" + "=" * 50)
    print("3. SSL 握手测试")
    print("=" * 50)
    try:
        hostname = "openrouter.ai"
        port = 443
        
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                print(f"✓ SSL 握手成功")
                print(f"  协议版本: {ssock.version()}")
                print(f"  证书主题: {ssock.getpeercert().get('subject', 'N/A')}")
                return True
    except Exception as e:
        print(f"❌ SSL 握手失败: {e}")
        return False


def check_proxy():
    """检查代理设置"""
    print("\n" + "=" * 50)
    print("4. 代理设置检查")
    print("=" * 50)
    
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    no_proxy = os.getenv("NO_PROXY") or os.getenv("no_proxy")
    
    if http_proxy:
        print(f"⚠️  HTTP_PROXY: {http_proxy}")
    else:
        print("✓ HTTP_PROXY: 未设置")
    
    if https_proxy:
        print(f"⚠️  HTTPS_PROXY: {https_proxy}")
    else:
        print("✓ HTTPS_PROXY: 未设置")
    
    if no_proxy:
        print(f"✓ NO_PROXY: {no_proxy}")
    else:
        print("✓ NO_PROXY: 未设置")
    
    if http_proxy or https_proxy:
        print("\n💡 检测到代理设置。如果连接失败，可能需要：")
        print("   1. 确认代理服务器正常工作")
        print("   2. 检查代理是否需要认证")
        print("   3. 尝试临时禁用代理测试：")
        print("      set HTTP_PROXY=")
        print("      set HTTPS_PROXY=")
        return True
    else:
        return False


def test_http_request():
    """测试 HTTP 请求"""
    print("\n" + "=" * 50)
    print("5. HTTP 请求测试")
    print("=" * 50)
    try:
        import httpx
        
        url = "https://openrouter.ai/api/v1/models"
        print(f"正在请求: {url}")
        
        with httpx.Client(timeout=10.0, verify=True) as client:
            response = client.get(url)
            if response.status_code == 200:
                print(f"✓ HTTP 请求成功 (状态码: {response.status_code})")
                return True
            else:
                print(f"⚠️  HTTP 请求返回状态码: {response.status_code}")
                return False
    except ImportError:
        print("⚠️  httpx 未安装，跳过 HTTP 请求测试")
        return None
    except Exception as e:
        print(f"❌ HTTP 请求失败: {e}")
        return False


def check_firewall():
    """检查可能的防火墙问题"""
    print("\n" + "=" * 50)
    print("6. 防火墙检查")
    print("=" * 50)
    print("💡 建议检查：")
    print("   1. Windows 防火墙是否阻止了 Python")
    print("   2. 公司/学校网络是否有防火墙限制")
    print("   3. 杀毒软件是否拦截了网络连接")
    print("   4. 尝试临时禁用防火墙测试")


def main():
    """主诊断函数"""
    print("=" * 50)
    print("OpenRouter API 网络连接诊断")
    print("=" * 50)
    
    results = {
        "DNS": test_dns(),
        "TCP": test_tcp_connection(),
        "SSL": test_ssl_handshake(),
        "Proxy": check_proxy(),
        "HTTP": test_http_request(),
    }
    
    check_firewall()
    
    # 总结
    print("\n" + "=" * 50)
    print("诊断总结")
    print("=" * 50)
    
    for test_name, result in results.items():
        if result is None:
            status = "跳过"
        elif result:
            status = "✓ 通过"
        else:
            status = "❌ 失败"
        print(f"  {test_name}: {status}")
    
    # 提供建议
    print("\n" + "=" * 50)
    print("建议")
    print("=" * 50)
    
    if not results.get("DNS"):
        print("❌ DNS 解析失败，请检查网络连接")
    elif not results.get("TCP"):
        print("❌ TCP 连接失败，可能是防火墙或网络问题")
    elif not results.get("SSL"):
        print("❌ SSL 握手失败，可能是证书或代理问题")
        print("   尝试运行: python tests/test_api_with_retry.py")
    elif results.get("Proxy"):
        print("⚠️  检测到代理设置，如果连接失败，尝试禁用代理")
    else:
        print("✓ 基础网络连接正常")
        print("   如果 API 调用仍然失败，可能是 API Key 或配置问题")
        print("   尝试运行: python tests/test_api_with_retry.py")


if __name__ == "__main__":
    main()
