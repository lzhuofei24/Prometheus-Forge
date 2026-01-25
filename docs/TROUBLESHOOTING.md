# 故障排除指南

## SSL 连接错误

如果遇到 `[SSL: UNEXPECTED_EOF_WHILE_READING]` 错误，请尝试以下解决方案：

### 1. 运行网络诊断

```bash
python tools/diagnose_network.py
```

这将检查：
- DNS 解析
- TCP 连接
- SSL 握手
- 代理设置
- HTTP 请求

### 2. 检查网络环境

**如果在公司/学校网络：**
- 可能需要配置代理
- 检查防火墙是否阻止了连接
- 联系网络管理员

**如果在家庭网络：**
- 检查路由器设置
- 尝试重启路由器
- 检查是否有 VPN 连接

### 3. 更新依赖库

```bash
pip install --upgrade requests urllib3 httpx openai
```

### 4. 检查系统时间

SSL 证书验证需要正确的系统时间。确保系统时间准确。

### 5. 尝试不同的测试脚本

- `tests/test_api.py` - 完整测试（使用 OpenAI SDK）
- `tests/test_api_simple.py` - 简化测试（使用 requests）
- `tests/test_api_with_retry.py` - 带重试机制的测试

### 6. 临时禁用 SSL 验证（仅用于调试）

⚠️ **警告：仅用于调试，不要在生产环境使用**

在 `src/core/llm.py` 中，临时修改：

```python
http_client = httpx.Client(
    timeout=60.0,
    verify=False,  # 临时禁用 SSL 验证
)
```

### 7. 配置代理（如果需要）

如果网络需要代理，设置环境变量：

```bash
# Windows PowerShell
$env:HTTP_PROXY="http://proxy.example.com:8080"
$env:HTTPS_PROXY="http://proxy.example.com:8080"

# Windows CMD
set HTTP_PROXY=http://proxy.example.com:8080
set HTTPS_PROXY=http://proxy.example.com:8080

# Linux/Mac
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
```

### 8. 使用 VPN

如果网络环境限制访问，尝试使用 VPN 连接。

### 9. 检查 OpenRouter 服务状态

访问 https://openrouter.ai 检查服务是否正常。

### 10. 联系支持

如果以上方法都无效，可能是：
- OpenRouter 服务临时故障
- 网络环境特殊限制
- Python SSL 库版本问题

可以尝试：
- 等待一段时间后重试
- 在不同的网络环境下测试
- 检查 OpenRouter 的官方状态页面

## 常见错误代码

### APIConnectionError
- **原因**：网络连接问题
- **解决**：检查网络连接，运行 `tools/diagnose_network.py`

### SSLError
- **原因**：SSL/TLS 握手失败
- **解决**：更新 urllib3，检查系统时间，检查代理设置

### TimeoutError
- **原因**：请求超时
- **解决**：增加超时时间，检查网络速度

### AuthenticationError
- **原因**：API Key 无效
- **解决**：检查 `.env` 文件中的 `OPENROUTER_API_KEY` 是否正确

## 测试脚本说明

1. **tools/diagnose_network.py** - 网络连接诊断
2. **tests/test_api.py** - 完整 API 测试（使用项目代码）
3. **tests/test_api_simple.py** - 简化测试（直接使用 requests）
4. **tests/test_api_with_retry.py** - 带重试机制的测试

## 获取帮助

如果问题持续存在，请提供以下信息：
1. 运行 `tools/diagnose_network.py` 的输出
2. 完整的错误堆栈信息
3. Python 版本：`python --version`
4. 操作系统信息
5. 网络环境（家庭/公司/学校）
