# Novel-Agent 开发指南

## 目录

- [开发环境设置](#开发环境设置)
- [代码规范](#代码规范)
- [开发工作流](#开发工作流)
- [调试技巧](#调试技巧)
- [测试指南](#测试指南)
- [贡献指南](#贡献指南)

## 开发环境设置

### 1. 环境要求

**必需软件**：
- Python 3.10+
- Conda / Miniconda
- Docker Desktop
- Git
- VS Code / PyCharm（推荐）

**硬件推荐**：
- CPU: 4 核心+
- 内存: 16GB+（8GB 可运行，但会较慢）
- 硬盘: 10GB 可用空间
- GPU: 可选（仅用于本地模型）

### 2. 克隆项目

```bash
git clone https://github.com/your-org/novel-agent.git
cd novel-agent
```

### 3. 创建开发环境

```bash
# 创建 Conda 环境
conda env create -f environment.yml
conda activate novel-agent

# 验证安装
python --version  # 应显示 3.10.x
celery --version  # 应显示 5.3.x
streamlit --version  # 应显示 1.50.x
```

### 4. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env 文件
# OPENROUTER_API_KEY=your_key_here
```

### 5. 启动开发服务

```bash
# 1. 启动 Redis
docker-compose up -d

# 2. 启动 Celery Workers（开发模式，单worker）
celery -A src.workers.tasks worker -Q text_queue,rag_queue,media_queue -c 1 --loglevel=debug

# 3. 启动 Streamlit（开发模式，自动重载）
streamlit run src/gui/app.py --server.runOnSave true
```

### 6. IDE 配置

**VS Code 推荐插件**：
- Python
- Pylance
- Python Indent
- autoDocstring
- Better Comments
- GitLens

**VS Code 配置** (`.vscode/settings.json`)：
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.conda/envs/novel-agent/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "editor.rulers": [88],
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true
  }
}
```

## 代码规范

### 1. Python 风格指南

遵循 **PEP 8** 标准，使用 Black 格式化。

**基本规则**：
- 缩进：4 个空格
- 行长度：88 字符（Black 默认）
- 命名：
  - 类名：`PascalCase`
  - 函数/变量：`snake_case`
  - 常量：`UPPER_SNAKE_CASE`
  - 私有成员：`_leading_underscore`

**示例**：
```python
# 正确
class LLMClient:
    MAX_RETRIES = 8
    
    def __init__(self, api_key: str):
        self._api_key = api_key
    
    def chat(self, messages: list) -> str:
        return self._call_api(messages)
    
    def _call_api(self, messages: list) -> str:
        # 私有方法
        pass

# 错误
class llmClient:  # 应该用 PascalCase
    maxRetries = 8  # 常量应该用 UPPER_SNAKE_CASE
    
    def Chat(self, Messages):  # 函数名应该用 snake_case
        pass
```

### 2. 类型注解

**强制使用类型注解**（Python 3.10+ typing）：

```python
from typing import Optional, List, Dict, Any

def generate_outline(
    novel_name: str,
    chapter_num: int,
    context: Optional[str] = None
) -> Dict[str, Any]:
    """
    生成章节大纲
    
    Args:
        novel_name: 小说名称
        chapter_num: 章节编号
        context: 可选的上下文信息
    
    Returns:
        包含大纲结构的字典
    
    Raises:
        ValueError: 如果章节编号无效
    """
    if chapter_num < 1:
        raise ValueError("章节编号必须大于0")
    
    return {
        "title": "章节标题",
        "scenes": []
    }
```

### 3. 文档字符串

使用 **Google 风格** 的 docstring：

```python
def process_content(
    content: str,
    max_length: int = 5000,
    remove_markdown: bool = False
) -> str:
    """处理章节内容
    
    将原始内容进行清理和格式化，可选择移除 Markdown 标记。
    
    Args:
        content: 原始章节内容
        max_length: 最大长度限制，默认 5000 字
        remove_markdown: 是否移除 Markdown 标记，默认 False
    
    Returns:
        处理后的内容字符串
    
    Examples:
        >>> content = "# 标题\n\n正文内容"
        >>> process_content(content, max_length=100)
        '# 标题\n\n正文内容'
        
        >>> process_content(content, remove_markdown=True)
        '标题\n\n正文内容'
    
    Note:
        如果内容超过 max_length，会进行截断并添加省略号。
    """
    # 实现...
    pass
```

### 4. 错误处理

**分层异常处理**：

```python
# 定义自定义异常
class NovelAgentError(Exception):
    """基础异常类"""
    pass

class LLMError(NovelAgentError):
    """LLM 调用相关异常"""
    pass

class ValidationError(NovelAgentError):
    """数据验证异常"""
    pass

# 使用示例
def call_llm(prompt: str) -> str:
    try:
        response = openai.ChatCompletion.create(...)
        return response.choices[0].message.content
    except openai.error.APIError as e:
        # API 错误 → 包装为自定义异常
        raise LLMError(f"LLM API 调用失败: {e}") from e
    except openai.error.RateLimitError:
        # 限流 → 触发重试
        logger.warning("遇到限流，等待后重试")
        time.sleep(60)
        return call_llm(prompt)  # 递归重试
```

### 5. 日志记录

**使用 Python logging 模块**：

```python
import logging

# 在模块顶部配置 logger
logger = logging.getLogger(__name__)

# 使用分级日志
logger.debug("调试信息：变量值 = %s", variable)
logger.info("流程节点：开始生成大纲")
logger.warning("可恢复异常：重试第 %d 次", attempt)
logger.error("严重错误：LLM 调用失败", exc_info=True)

# 避免使用 print()
# ❌ print(f"结果：{result}")
# ✅ logger.info("任务完成，结果：%s", result)
```

## 开发工作流

### 1. 功能开发流程

```
1. 创建功能分支
   git checkout -b feature/your-feature-name

2. 编写代码
   - 实现功能
   - 添加类型注解
   - 编写 docstring

3. 编写测试
   - 单元测试
   - 集成测试

4. 格式化代码
   black src/
   flake8 src/

5. 提交代码
   git add .
   git commit -m "feat: 添加xxx功能"

6. 推送分支
   git push origin feature/your-feature-name

7. 创建 Pull Request
   - 填写 PR 模板
   - 请求代码审查
```

### 2. Git Commit 规范

使用 **Conventional Commits** 格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type 类型**：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构（不是新功能也不是修复）
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具链相关

**示例**：
```bash
# 新功能
git commit -m "feat(agents): 添加 Translator Agent"

# Bug 修复
git commit -m "fix(llm): 修复重试机制死循环问题"

# 文档
git commit -m "docs: 更新 README 安装说明"

# 重构
git commit -m "refactor(tasks): 重构图片生成任务逻辑"
```

### 3. 分支策略

**主要分支**：
- `main`: 生产环境，稳定版本
- `develop`: 开发环境，集成分支

**辅助分支**：
- `feature/*`: 功能开发
- `fix/*`: Bug 修复
- `refactor/*`: 重构
- `docs/*`: 文档更新

**合并策略**：
```
feature/xxx → develop → main
      ↓          ↓        ↓
    测试      集成测试   发布
```

## 调试技巧

### 1. Celery 任务调试

**同步执行任务**（跳过队列）：
```python
# 开发模式：直接调用
from src.workers.tasks import generate_outline_task

result = generate_outline_task("都市传说", 1)
print(result)

# 生产模式：异步执行
task = generate_outline_task.delay("都市传说", 1)
result = task.get()
```

**查看任务详情**：
```python
from celery.result import AsyncResult

task_id = "abc-123-def"
result = AsyncResult(task_id)

print(result.state)  # PENDING, SUCCESS, FAILURE
print(result.info)   # 任务结果或异常信息
print(result.traceback)  # 失败时的堆栈跟踪
```

### 2. LLM 调用调试

**启用详细日志**：
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 查看完整的请求和响应
```

**Mock LLM 响应**（加速测试）：
```python
class MockLLMClient:
    def chat(self, messages, **kwargs):
        return json.dumps({
            "title": "测试章节",
            "scenes": [{"description": "测试场景"}]
        })

# 在测试中注入 Mock
llm_client = MockLLMClient()
```

### 3. Streamlit 调试

**启用开发模式**：
```bash
streamlit run src/gui/app.py --server.runOnSave true --logger.level debug
```

**使用 st.write() 调试**：
```python
import streamlit as st

st.write("Debug:", variable)
st.json(complex_object)
st.code(source_code)
```

### 4. 断点调试

**VS Code 配置** (`.vscode/launch.json`)：
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Streamlit",
      "type": "python",
      "request": "launch",
      "module": "streamlit",
      "args": ["run", "src/gui/app.py"],
      "console": "integratedTerminal"
    },
    {
      "name": "Python: Celery Worker",
      "type": "python",
      "request": "launch",
      "module": "celery",
      "args": ["-A", "src.workers.tasks", "worker", "--loglevel=debug"],
      "console": "integratedTerminal"
    }
  ]
}
```

## 测试指南

### 1. 测试结构

```
tests/
├── unit/           # 单元测试
│   ├── test_llm.py
│   ├── test_agents.py
│   └── test_utils.py
├── integration/    # 集成测试
│   ├── test_workflow.py
│   └── test_tasks.py
└── fixtures/       # 测试数据
    ├── sample_outline.json
    └── sample_content.md
```

### 2. 单元测试示例

```python
import pytest
from src.core.llm import LLMClient

class TestLLMClient:
    @pytest.fixture
    def llm_client(self):
        """创建 LLMClient 实例"""
        return LLMClient(api_key="test_key")
    
    def test_chat_basic(self, llm_client, mocker):
        """测试基本的 chat 功能"""
        # Mock API 响应
        mock_response = mocker.Mock()
        mock_response.choices = [mocker.Mock()]
        mock_response.choices[0].message.content = "Hello"
        
        mocker.patch('openai.ChatCompletion.create', return_value=mock_response)
        
        # 执行测试
        result = llm_client.chat([{"role": "user", "content": "Hi"}])
        
        # 断言
        assert result == "Hello"
    
    def test_retry_on_failure(self, llm_client, mocker):
        """测试失败重试机制"""
        # 模拟第一次失败，第二次成功
        mock_create = mocker.patch('openai.ChatCompletion.create')
        mock_create.side_effect = [
            Exception("Network error"),
            mocker.Mock(choices=[mocker.Mock(message=mocker.Mock(content="Success"))])
        ]
        
        result = llm_client.chat([{"role": "user", "content": "Test"}])
        
        assert result == "Success"
        assert mock_create.call_count == 2
```

### 3. 集成测试示例

```python
import pytest
from src.workers.tasks import generate_outline_task

class TestWorkflow:
    @pytest.mark.integration
    def test_full_chapter_generation(self, test_novel_setup):
        """测试完整的章节生成流程"""
        novel_name = "测试小说"
        chapter_num = 1
        
        # 1. 生成大纲
        outline_result = generate_outline_task(novel_name, chapter_num)
        assert outline_result["status"] == "success"
        
        # 2. 生成正文
        content_result = generate_content_task(novel_name, chapter_num)
        assert content_result["status"] == "success"
        
        # 3. 审稿
        critique_result = critique_content_task(novel_name, chapter_num)
        assert critique_result["overall_score"] >= 75
```

### 4. 运行测试

```bash
# 运行所有测试
pytest

# 运行单个文件
pytest tests/unit/test_llm.py

# 运行特定测试
pytest tests/unit/test_llm.py::TestLLMClient::test_chat_basic

# 查看覆盖率
pytest --cov=src --cov-report=html
```

## 贡献指南

### 1. 提交 Pull Request

**PR 检查清单**：
- [ ] 代码通过所有测试
- [ ] 添加了必要的单元测试
- [ ] 更新了相关文档
- [ ] 遵循代码规范（Black + Flake8）
- [ ] Commit 信息符合规范
- [ ] 没有遗留的 TODO 或 FIXME

**PR 模板**：
```markdown
## 变更说明
简要描述本次 PR 的目的和主要变更。

## 变更类型
- [ ] 新功能
- [ ] Bug 修复
- [ ] 文档更新
- [ ] 代码重构
- [ ] 性能优化

## 测试
描述如何测试这些变更。

## 截图（如果适用）
添加相关截图。

## 相关 Issue
Closes #123
```

### 2. 代码审查

**审查重点**：
- 功能正确性
- 代码可读性
- 性能影响
- 安全性
- 测试覆盖率

**审查流程**：
1. 审查代码 → 提出意见
2. 作者修改 → 重新提交
3. 再次审查 → 批准合并

### 3. 发布流程

**版本号规则**（Semantic Versioning）：
```
MAJOR.MINOR.PATCH

1.2.3
↑ ↑ ↑
│ │ └─ PATCH: Bug 修复
│ └─── MINOR: 新功能（向后兼容）
└───── MAJOR: 重大变更（不向后兼容）
```

**发布步骤**：
```bash
# 1. 更新版本号
# 编辑 version.py 或 pyproject.toml

# 2. 更新 CHANGELOG.md
# 记录所有变更

# 3. 创建标签
git tag -a v1.2.0 -m "Release version 1.2.0"

# 4. 推送标签
git push origin v1.2.0

# 5. 创建 GitHub Release
# 在 GitHub 上创建 Release，附上 CHANGELOG
```

## 常见开发问题

### 1. 环境依赖冲突

**问题**：安装新依赖后，其他模块报错。

**解决**：
```bash
# 重新生成 requirements.txt
pip freeze > requirements.txt

# 或更新 environment.yml
conda env export > environment.yml
```

### 2. Celery Worker 无法连接 Redis

**问题**：Worker 启动失败，显示 "Cannot connect to Redis"。

**解决**：
```bash
# 检查 Redis 是否运行
docker ps | grep redis

# 重启 Redis
docker-compose restart

# 检查端口是否被占用
netstat -an | findstr 6379
```

### 3. Streamlit 页面不刷新

**问题**：修改代码后，Streamlit 页面不自动更新。

**解决**：
```bash
# 启用自动重载
streamlit run src/gui/app.py --server.runOnSave true

# 或手动刷新（按 R）
```

## 最佳实践

### 1. 模块化设计

**单一职责原则**：
```python
# ❌ 不好：一个函数做太多事情
def process_chapter(novel_name, chapter_num):
    # 生成大纲
    outline = generate_outline(...)
    # 生成正文
    content = generate_content(...)
    # 生成图片
    image = generate_image(...)
    # 保存文件
    save_files(...)

# ✅ 好：每个函数只做一件事
def generate_outline(novel_name, chapter_num):
    # 只负责生成大纲
    pass

def generate_content(novel_name, chapter_num, outline):
    # 只负责生成正文
    pass
```

### 2. 配置外部化

**避免硬编码**：
```python
# ❌ 不好
MAX_RETRIES = 8
MODEL_NAME = "gpt-4"

# ✅ 好
from src.core.config import Settings

config = Settings.load_from_yaml("config/settings.yaml")
MAX_RETRIES = config.llm.max_retries
MODEL_NAME = config.llm.model_name
```

### 3. 优雅的资源管理

**使用上下文管理器**：
```python
# ✅ 推荐
with open("file.txt", "r") as f:
    content = f.read()

# 数据库连接
with db_session() as session:
    result = session.query(...)
```

## 相关文档

- [系统架构](ARCHITECTURE.md)
- [工作流程](WORKFLOW.md)
- [快速开始](../README.md#-quick-start)
- [故障排查](TROUBLESHOOTING.md)
