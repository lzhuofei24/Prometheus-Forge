# 图片生成功能说明

## 概述

Novel-Agent 使用 OpenRouter 的 **Gemini 2.5 Flash Image** 模型（又名 "Nano Banana"）进行图片生成。这是一个原生图片生成模型，支持上下文理解和多轮对话。

## 技术架构

### 模型信息

- **模型名称**：`google/gemini-2.5-flash-image`
- **发布时间**：2025年10月
- **上下文窗口**：32,768 tokens
- **特点**：
  - 原生图片生成能力
  - 支持上下文理解
  - 可控制宽高比
  - 返回 base64 编码的 PNG 图片

### 定价

| 项目 | 价格 |
|------|------|
| 输入 tokens | $0.30/M |
| 输出 tokens | $2.50/M |
| 图片生成 | $30/M tokens |
| 音频 | $1/M tokens |

**单次生图成本**：约 $0.03-0.05（根据提示词长度）

## 工作流程

### 1. 场景描述提取

从章节大纲中提取 `scene_description` 字段：

```json
{
  "scene_description": "夜晚的废弃工厂，月光透过破碎的窗户洒在斑驳的地面上..."
}
```

如果大纲中没有场景描述，则使用章节前500字作为描述。

### 2. 提示词优化

使用 LLM 将中文场景描述转换为适合图片生成的英文提示词：

**System Prompt**：
```
You are an expert AI Art Prompter for a visual novel.
Your task is to convert the given scene description into a detailed Stable Diffusion/Flux prompt.

CRITICAL SAFETY GUIDELINES:
1. NO GORE / NO EXPLICIT VIOLENCE
2. Atmosphere over Grime
3. SFW: Ensure the prompt is Safe For Work
4. Style: Cinematic, 8k, highly detailed, anime style

Output ONLY the English prompt, no explanations.
```

**输出示例**：
```
A mysterious abandoned factory at night, moonlight streaming through broken windows onto 
weathered concrete floors, dramatic shadows, cinematic lighting, hyper-realistic, 
anime style, 8k resolution, highly detailed
```

### 3. API 调用

使用 OpenRouter API 调用 Gemini 2.5 Flash Image：

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    default_headers={
        "HTTP-Referer": "http://localhost",
        "X-Title": "Novel-Agent"
    }
)

response = client.chat.completions.create(
    model="google/gemini-2.5-flash-image",
    messages=[
        {
            "role": "user",
            "content": f"Generate a high-quality image: {image_prompt}"
        }
    ],
    extra_body={
        "image_config": {
            "aspect_ratio": "1:1"
        }
    }
)
```

### 4. 图片提取

Gemini 2.5 Flash Image 在响应的 `message.images` 字段中返回 base64 编码的图片：

```python
message = response.choices[0].message

if hasattr(message, 'images') and message.images:
    for img_item in message.images:
        if isinstance(img_item, dict) and 'image_url' in img_item:
            url = img_item['image_url'].get('url', '')
            if url.startswith('data:image/'):
                # 提取 base64 数据
                import base64
                base64_str = url.split(',', 1)[1]
                image_data = base64.b64decode(base64_str)
                
                # 保存图片
                with open(image_path, "wb") as f:
                    f.write(image_data)
```

### 5. 降级策略

如果 API 调用失败（网络错误、限流、余额不足等），系统会自动生成**优化 Mock 图片**：

**Mock 图片特性**：
- 1024x1024 像素
- 渐变背景（深蓝到浅蓝）
- 半透明蒙版增加质感
- 显示章节号和提示词信息
- 轻微模糊滤镜
- 文件大小约 20-30 KB

## 配置说明

### 环境变量 (.env)

```env
# OpenRouter API Key（文本和图片共用）
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx

# 可选配置
OPENROUTER_SITE_URL=https://github.com/your-repo/novel-agent
OPENROUTER_APP_NAME=Novel-Agent-Local
```

### 全局配置 (config/settings.yaml)

```yaml
media:
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
  api_key_env: "OPENROUTER_API_KEY"
  image_model: "google/gemini-2.5-flash-image"
  site_url: "https://github.com/your-repo/novel-agent"
  app_name: "Novel-Agent-Local"
```

## 使用示例

### 通过 Celery 任务

```python
from src.workers.tasks import generate_image_task

# 为第 9 章生成插画
result = generate_image_task(
    novel_name="都市传说",
    chapter_num=9
)

# 返回结果
{
    "status": "success",
    "image_path": "workspace/都市传说/chapters/chapter_009/assets/image.png"
}
```

### 直接调用 API

```python
import os
from openai import OpenAI
import base64

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

response = client.chat.completions.create(
    model="google/gemini-2.5-flash-image",
    messages=[
        {
            "role": "user",
            "content": "Generate a high-quality image: A mysterious dark alley at night"
        }
    ],
    extra_body={
        "image_config": {
            "aspect_ratio": "1:1"
        }
    }
)

# 提取图片
message = response.choices[0].message
if hasattr(message, 'images') and message.images:
    img_item = message.images[0]
    url = img_item['image_url']['url']
    base64_str = url.split(',', 1)[1]
    image_data = base64.b64decode(base64_str)
    
    with open("output.png", "wb") as f:
        f.write(image_data)
```

## 故障排查

### 问题：图片生成失败，但任务继续

**症状**：
- Worker 日志显示 "Gemini 生图失败"
- 最终生成了 Mock 图片（20-30 KB）

**可能原因**：
1. 网络连接不稳定（超时、连接重置）
2. OpenRouter 限流（429 错误）
3. API Key 配置错误
4. 账户余额不足

**解决方案**：
1. 检查网络连接
2. 确认 `.env` 文件中的 `OPENROUTER_API_KEY` 是否正确
3. 访问 [OpenRouter Dashboard](https://openrouter.ai) 检查余额
4. 等待几分钟后重试（如果是限流）

### 问题：HTTP 429 Too Many Requests

**原因**：OpenRouter 免费层限流

**解决方案**：
- 降低生成频率
- 升级到付费计划
- 或者接受 Mock 图片作为临时方案

### 问题：图片质量不满意

**优化方向**：
1. **优化提示词**：
   - 增加细节描述（lighting, atmosphere, mood）
   - 明确艺术风格（anime, realistic, painterly）
   - 添加质量关键词（8k, highly detailed, masterpiece）

2. **调整场景描述**：
   - 在大纲生成时提供更详细的场景描述
   - 强调视觉元素（颜色、光线、构图）

3. **修改 System Prompt**：
   - 编辑 `src/workers/tasks.py` 中的 `illustrator_system_prompt`
   - 添加特定的风格指令

## 最佳实践

### 提示词设计

**推荐模板**：
```
[主题] + [环境] + [光线] + [风格] + [质量标签]
```

**示例**：
```
A lone warrior standing on a cliff edge, 
stormy ocean below, 
dramatic sunset lighting, 
cinematic anime style, 
8k resolution, 
highly detailed, 
masterpiece quality
```

### 成本控制

1. **批量生成**：一次性生成多章插画可以减少 API 调用开销
2. **选择性生成**：只为重要章节生成插画
3. **重用图片**：相似场景可以共享图片
4. **监控消费**：定期检查 OpenRouter 账单

### 性能优化

1. **并发控制**：`media_queue` 支持并发2-4个任务
2. **超时设置**：单次调用超时 120 秒
3. **重试机制**：网络错误自动重试 3 次
4. **降级策略**：失败后立即生成 Mock，不阻塞流程

## 替代方案

如果 Gemini 2.5 Flash Image 不满足需求，可以考虑：

### 1. 其他 OpenRouter 模型

- `black-forest-labs/flux-schnell`：速度快，但需要付费
- `stability-ai/stable-diffusion-xl`：经典模型

### 2. 本地部署

- 优点：无 API 成本，无网络依赖
- 缺点：需要 GPU（至少 8GB VRAM），下载模型慢
- 参考：之前版本的 Flux.1 Schnell NF4 方案（已废弃）

### 3. 纯 Mock 模式

- 修改 `src/workers/tasks.py`，直接跳到 Mock 生成
- 适合测试或预算有限的场景

## 相关文件

| 文件 | 说明 |
|------|------|
| `src/workers/tasks.py` | 图片生成任务实现 |
| `config/settings.yaml` | 全局配置文件 |
| `.env` | 环境变量（API Key） |
| `environment.yml` | Python 依赖 |

## 更新日志

### 2026-01-24

- ✅ 切换到 Gemini 2.5 Flash Image（付费模型）
- ✅ 支持 base64 图片提取
- ✅ 优化 Mock 图片（渐变背景 + 美化）
- ✅ 移除本地生图依赖（torch, diffusers）
- ✅ 增加重试和错误处理

### 历史记录

- **2025-01**：使用 OpenRouter Flux.2 Flex（通过 Chat API）
- **2025-01**：尝试 Pollinations.ai（免费，网络不稳定）
- **2025-01**：尝试本地 Flux.1 Schnell NF4（网络下载失败）
- **2025-01**：使用 Google Gemini Free（频繁限流）
- **2024-12**：使用 SiliconFlow Kolors（已废弃）
