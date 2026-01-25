# Novel-Agent API 参考

## 目录

- [Core API](#core-api)
- [Agents API](#agents-api)
- [Workers API](#workers-api)
- [Utils API](#utils-api)

## Core API

### LLMClient

统一的 LLM 调用接口。

#### 初始化

```python
from src.core.llm import LLMClient

client = LLMClient(
    provider="openrouter",          # API 提供商
    base_url="https://openrouter.ai/api/v1",
    api_key="your_api_key",
    model_name="deepseek/deepseek-chat",
    temperature=1.0,
    max_tokens=8192
)
```

#### 方法

##### `chat(messages, temperature=None, max_tokens=None, stream=False)`

发送聊天请求到 LLM。

**参数**：
- `messages` (list): OpenAI 格式的消息列表
- `temperature` (float, optional): 采样温度，覆盖默认值
- `max_tokens` (int, optional): 最大生成 tokens，覆盖默认值
- `stream` (bool): 是否使用流式输出

**返回**：
- `str`: LLM 生成的文本内容

**示例**：
```python
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
]

response = client.chat(messages)
print(response)  # "Hello! How can I help you today?"
```

**异常**：
- `LLMError`: LLM 调用失败
- `NetworkError`: 网络连接失败

---

### Settings

配置加载和管理。

#### 类方法

##### `load_from_yaml(config_path)`

从 YAML 文件加载配置。

**参数**：
- `config_path` (Path): 配置文件路径

**返回**：
- `Settings`: 配置对象

**示例**：
```python
from pathlib import Path
from src.core.config import Settings

config = Settings.load_from_yaml(Path("config/settings.yaml"))

print(config.llm.model_name)  # "deepseek/deepseek-chat"
print(config.agents["writer"].temperature)  # 0.9
```

---

### PromptRouter

Prompt Registry 管理器。

#### 初始化

```python
from src.core.prompt_manager import PromptRouter

router = PromptRouter(
    persist_directory="./data/chroma_db",
    collection_name="prompt_registry"
)
```

#### 方法

##### `add_prompt(name, content, metadata=None)`

添加提示词到 Registry。

**参数**：
- `name` (str): 提示词名称（唯一标识）
- `content` (str): 提示词内容
- `metadata` (dict, optional): 元数据（如标签、分类）

**返回**：
- `bool`: 是否成功

**示例**：
```python
router.add_prompt(
    name="writing_style_guideline",
    content="Write in a narrative style with rich descriptions...",
    metadata={"category": "writing", "tags": ["style", "narrative"]}
)
```

##### `query(query_text, top_k=5)`

检索相似提示词。

**参数**：
- `query_text` (str): 查询文本
- `top_k` (int): 返回前 K 个结果

**返回**：
- `list[dict]`: 匹配的提示词列表，每个元素包含 `name`, `content`, `similarity`

**示例**：
```python
results = router.query("如何描写战斗场景", top_k=3)

for result in results:
    print(f"{result['name']}: {result['similarity']:.2f}")
    print(result['content'][:100])
```

---

## Agents API

### ArchitectAgent (Builder)

章节结构规划 Agent。

#### 初始化

```python
from src.agents.builder import ArchitectAgent

agent = ArchitectAgent(
    llm_client=llm_client,
    prompt_router=prompt_router
)
```

#### 方法

##### `generate_outline(novel_name, chapter_num, context=None)`

生成章节大纲。

**参数**：
- `novel_name` (str): 小说名称
- `chapter_num` (int): 章节编号
- `context` (str, optional): 额外上下文信息

**返回**：
- `dict`: 大纲结构

**返回格式**：
```json
{
  "title": "第一章：觉醒",
  "summary": "主角在平凡的一天中发现了异常...",
  "scenes": [
    {
      "scene_number": 1,
      "description": "早晨，主角的卧室",
      "characters": ["主角"],
      "key_events": ["闹钟响起", "发现手机上的神秘消息"]
    },
    {
      "scene_number": 2,
      "description": "学校走廊",
      "characters": ["主角", "同学A"],
      "key_events": ["遇到同学", "听说奇怪传闻"]
    }
  ],
  "scene_description": "清晨的卧室，阳光透过窗帘洒在床上...",
  "themes": ["觉醒", "神秘"]
}
```

---

### WriterAgent (Novelist)

正文内容生成 Agent。

#### 初始化

```python
from src.agents.novelist import WriterAgent

agent = WriterAgent(
    llm_client=llm_client,
    prompt_router=prompt_router
)
```

#### 方法

##### `generate_content(novel_name, chapter_num, outline, context=None)`

生成章节正文。

**参数**：
- `novel_name` (str): 小说名称
- `chapter_num` (int): 章节编号
- `outline` (dict): 章节大纲
- `context` (str, optional): 额外上下文信息

**返回**：
- `str`: Markdown 格式的正文内容

**示例**：
```python
outline = agent_architect.generate_outline("都市传说", 1)
content = agent_writer.generate_content("都市传说", 1, outline)

print(len(content))  # 约 3000-5000 字
```

---

### CriticAgent (Editor)

内容审稿 Agent。

#### 初始化

```python
from src.agents.editor import CriticAgent

agent = CriticAgent(
    llm_client=llm_client,
    prompt_router=prompt_router
)
```

#### 方法

##### `critique(novel_name, chapter_num, content, outline=None)`

审稿并评分。

**参数**：
- `novel_name` (str): 小说名称
- `chapter_num` (int): 章节编号
- `content` (str): 章节正文
- `outline` (dict, optional): 章节大纲（用于对比）

**返回**：
- `dict`: 审稿结果

**返回格式**：
```json
{
  "overall_score": 85,
  "character_consistency": 90,
  "plot_coherence": 85,
  "writing_quality": 80,
  "emotional_impact": 85,
  "strengths": [
    "人物刻画生动，性格鲜明",
    "情节紧凑，冲突设计合理"
  ],
  "weaknesses": [
    "部分环境描写重复",
    "对话略显生硬"
  ],
  "suggestions": [
    "减少冗余的环境描写",
    "增加对话的口语化程度"
  ]
}
```

---

## Workers API

### Celery Tasks

所有任务都通过 Celery 异步执行。

#### 大纲生成任务

```python
from src.workers.tasks import generate_outline_task

# 异步调用
task = generate_outline_task.delay("都市传说", 1)

# 等待结果
result = task.get(timeout=300)  # 最多等待 5 分钟

print(result)
```

#### 正文生成任务

```python
from src.workers.tasks import generate_content_task

task = generate_content_task.delay("都市传说", 1)
result = task.get(timeout=600)  # 最多等待 10 分钟
```

#### 审稿任务

```python
from src.workers.tasks import critique_content_task

task = critique_content_task.delay("都市传说", 1)
result = task.get(timeout=180)
```

#### 图片生成任务

```python
from src.workers.tasks import generate_image_task

task = generate_image_task.delay("都市传说", 1)
result = task.get(timeout=180)

# 返回格式
{
  "status": "success",
  "image_path": "workspace/都市传说/chapters/chapter_001/assets/image.png"
}
```

#### 音频生成任务

```python
from src.workers.tasks import generate_audio_task

task = generate_audio_task.delay("都市传说", 1, use_full_text=False)
result = task.get(timeout=120)

# 返回格式
{
  "status": "success",
  "audio_path": "workspace/都市传说/chapters/chapter_001/assets/audio.mp3"
}
```

#### 并行执行多个任务

```python
from celery import group
from src.workers.tasks import generate_image_task, generate_audio_task

# 并行生成图片和音频
job = group([
    generate_image_task.si("都市传说", 1),
    generate_audio_task.si("都市传说", 1)
])

result = job.apply_async()
results = result.get()  # 等待所有任务完成

print(results)
# [
#   {"status": "success", "image_path": "..."},
#   {"status": "success", "audio_path": "..."}
# ]
```

---

## Utils API

### ProjectManager

文件和目录管理工具。

#### 初始化

```python
from src.utils.file_manager import ProjectManager

manager = ProjectManager(workspace_root="./workspace")
```

#### 方法

##### `get_novel_path(novel_name)`

获取小说根目录路径。

**参数**：
- `novel_name` (str): 小说名称

**返回**：
- `Path`: 小说目录路径

**示例**：
```python
path = manager.get_novel_path("都市传说")
print(path)  # Path('workspace/都市传说')
```

##### `get_chapter_path(novel_name, chapter_num)`

获取章节目录路径。

**参数**：
- `novel_name` (str): 小说名称
- `chapter_num` (int): 章节编号

**返回**：
- `Path`: 章节目录路径

**示例**：
```python
path = manager.get_chapter_path("都市传说", 1)
print(path)  # Path('workspace/都市传说/chapters/chapter_001')
```

##### `list_chapters(novel_name)`

列出所有章节。

**参数**：
- `novel_name` (str): 小说名称

**返回**：
- `list[int]`: 章节编号列表（排序）

**示例**：
```python
chapters = manager.list_chapters("都市传说")
print(chapters)  # [1, 2, 3, 5, 7]
```

##### `load_content(file_path)`

加载文件内容。

**参数**：
- `file_path` (Path): 文件路径

**返回**：
- `str | dict | list`: 文件内容（根据扩展名自动解析）

**支持格式**：
- `.json`: 解析为 dict/list
- `.md`, `.txt`: 返回字符串
- `.yaml`, `.yml`: 解析为 dict

**示例**：
```python
# 加载 Markdown
content = manager.load_content(Path("workspace/都市传说/chapters/chapter_001/content.md"))

# 加载 JSON
outline = manager.load_content(Path("workspace/都市传说/chapters/chapter_001/outline.json"))
```

##### `save_content(file_path, content)`

保存文件内容。

**参数**：
- `file_path` (Path): 文件路径
- `content` (str | dict | list): 要保存的内容

**示例**：
```python
# 保存 Markdown
manager.save_content(
    Path("workspace/都市传说/chapters/chapter_001/content.md"),
    "# 第一章\n\n正文内容..."
)

# 保存 JSON
manager.save_content(
    Path("workspace/都市传说/chapters/chapter_001/outline.json"),
    {"title": "第一章", "scenes": []}
)
```

---

### JSONUtils

JSON 数据处理工具。

#### 函数

##### `parse_json_from_response(text)`

从 LLM 响应中提取 JSON。

**参数**：
- `text` (str): LLM 响应文本

**返回**：
- `dict | list`: 解析后的 JSON 对象

**功能**：
- 自动去除 Markdown 代码块标记
- 处理注释（// 和 /* */）
- 修复常见的 JSON 错误

**示例**：
```python
from src.utils.json_utils import parse_json_from_response

response = '''
```json
{
  "title": "第一章",  // 标题
  "scenes": [
    {"description": "场景1"}
  ]
}
```
'''

data = parse_json_from_response(response)
print(data["title"])  # "第一章"
```

##### `validate_outline_structure(outline)`

验证大纲结构是否合法。

**参数**：
- `outline` (dict): 大纲数据

**返回**：
- `tuple[bool, str]`: (是否合法, 错误信息)

**示例**：
```python
from src.utils.json_utils import validate_outline_structure

outline = {
    "title": "第一章",
    "scenes": [
        {"scene_number": 1, "description": "场景描述"}
    ]
}

is_valid, error = validate_outline_structure(outline)
if not is_valid:
    print(f"验证失败: {error}")
```

---

## 错误处理

### 异常类型

```python
from src.core.exceptions import (
    NovelAgentError,      # 基础异常
    LLMError,             # LLM 相关异常
    ValidationError,      # 数据验证异常
    FileOperationError,   # 文件操作异常
    NetworkError          # 网络异常
)
```

### 使用示例

```python
try:
    response = llm_client.chat(messages)
except LLMError as e:
    logger.error(f"LLM 调用失败: {e}")
    # 重试或降级处理
except NetworkError as e:
    logger.warning(f"网络异常: {e}")
    # 等待后重试
except ValidationError as e:
    logger.error(f"数据验证失败: {e}")
    # 返回错误给用户
```

---

## 配置参考

### Settings.yaml 结构

```yaml
llm:
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
  api_key_env: "OPENROUTER_API_KEY"
  model_name: "deepseek/deepseek-chat"
  context_window: 65536
  max_tokens: 8192
  temperature: 1.0

agents:
  architect:
    temperature: 0.7
    max_tokens: 8192
    description: "规划章节结构"
  
  writer:
    temperature: 0.9
    max_tokens: 8192
    description: "生成正文内容"
  
  critic:
    temperature: 0.5
    max_tokens: 4096
    description: "审稿评估"

media:
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
  api_key_env: "OPENROUTER_API_KEY"
  image_model: "google/gemini-2.5-flash-image"

paths:
  raw_data: "./data/raw"
  chroma_db: "./data/chroma_db"
  workspace: "./workspace"

chunking:
  chunk_size: 1000
  chunk_overlap: 200
```

---

## 相关文档

- [系统架构](ARCHITECTURE.md)
- [开发指南](DEVELOPMENT.md)
- [快速开始](../README.md#-quick-start)
