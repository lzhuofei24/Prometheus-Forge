# Novel-Agent 快速参考手册

一页纸速查手册，包含最常用的命令和操作。

## 🚀 快速启动

### Windows 一键启动

```bash
START_HERE.bat
```

然后在新终端：
```bash
conda activate novel-agent
streamlit run src/gui/app.py
```

### 手动启动

```bash
# 1. Redis
docker-compose up -d

# 2. Workers
start_workers.bat

# 3. Streamlit
streamlit run src/gui/app.py
```

---

## 📦 环境管理

### 创建环境

```bash
conda env create -f environment.yml
conda activate novel-agent
```

### 安装依赖

```bash
# 快速安装（推荐）
scripts\quick_install.bat

# 使用 Conda
scripts\install_dependencies.bat

# 使用 pip
scripts\install_dependencies_pip.bat
```

### 验证环境

```bash
celery --version
streamlit --version
python -c "import redis; print('Redis OK')"
python -c "import chromadb; print('ChromaDB OK')"
```

---

## 🔑 配置 API Key

### 设置环境变量

```bash
# 复制模板
copy .env.example .env

# 编辑 .env 文件，设置：
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
```

### 验证配置

```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('API Key:', os.getenv('OPENROUTER_API_KEY')[:10] + '...')"
```

---

## 📝 常用操作

### 创建新章节

1. 打开 Streamlit (`http://localhost:8501`)
2. 选择小说
3. 点击 "➕ 新建章节"
4. 在侧边栏查看进度

### 查看章节内容

1. 在章节列表点击章节号
2. 查看：
   - 📄 正文
   - 📊 大纲
   - 📋 审稿评分
   - 🖼️ 插画
   - 🎵 音频

### 管理提示词

1. 切换到 "🔖 Prompt Registry 管理" 标签
2. 点击 "➕ 添加新提示词"
3. 输入名称和内容
4. 点击保存

---

## 🛠️ 常用命令

### Docker 管理

```bash
# 启动 Redis
docker-compose up -d

# 查看状态
docker ps

# 重启 Redis
docker-compose restart

# 停止 Redis
docker-compose down

# 查看日志
docker-compose logs -f
```

### Celery 管理

```bash
# 启动 Workers（使用脚本）
start_workers.bat

# 手动启动单个 Worker
celery -A src.workers.tasks worker -Q text_queue -c 1 --loglevel=info --pool=solo

# 查看任务列表（需要安装 Flower）
celery -A src.workers.tasks flower --port=5555

# 清空队列
celery -A src.workers.tasks purge
```

### Streamlit 管理

```bash
# 启动（默认端口 8501）
streamlit run src/gui/app.py

# 指定端口
streamlit run src/gui/app.py --server.port 8502

# 开发模式（自动重载）
streamlit run src/gui/app.py --server.runOnSave true

# 清除缓存
streamlit cache clear
```

---

## 🐛 快速故障排查

### Redis 连接失败

```bash
# 检查 Docker
docker ps

# 重启 Redis
docker-compose restart

# 检查端口
netstat -an | findstr 6379
```

### Celery Worker 错误

```bash
# 检查环境
conda activate novel-agent
celery --version

# 重启 Workers
# 按 Ctrl+C 停止，然后运行：
start_workers.bat
```

### API 调用失败

```bash
# 检查 API Key
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(os.getenv('OPENROUTER_API_KEY'))"

# 测试网络连接
curl https://openrouter.ai/api/v1/models
```

### 图片生成失败

- 检查 OPENROUTER_API_KEY 是否设置
- 检查 OpenRouter 账户余额
- 失败时会自动生成 Mock 图片（正常行为）

---

## 📊 文件路径速查

### 配置文件

| 文件 | 路径 | 用途 |
|------|------|------|
| 全局配置 | `config/settings.yaml` | LLM、Agent、Media 配置 |
| 环境变量 | `.env` | API Key 和密钥 |
| 依赖列表 | `environment.yml` | Python 依赖 |
| Docker 配置 | `docker-compose.yml` | Redis 服务配置 |

### 数据文件

| 类型 | 路径 | 说明 |
|------|------|------|
| 小说工作区 | `workspace/{novel_name}/` | 生成的内容 |
| 章节目录 | `workspace/{novel_name}/chapters/chapter_{num:03d}/` | 章节文件 |
| 大纲 | `.../outline.json` | 章节结构 |
| 正文 | `.../content.md` | Markdown 正文 |
| 审稿 | `.../critique.json` | 审稿结果 |
| 插画 | `.../assets/image.png` | 场景插画 |
| 音频 | `.../assets/audio.mp3` | 音频朗读 |

### 全局设定

| 文件 | 路径 | 说明 |
|------|------|------|
| 人物档案 | `workspace/{novel_name}/global/bios.json` | 角色设定 |
| 世界观 | `workspace/{novel_name}/global/world.md` | 世界观设定 |
| 剧情梗概 | `workspace/{novel_name}/global/story_summary.md` | 全书梗概 |

---

## 🔗 常用 URL

| 服务 | URL | 说明 |
|------|-----|------|
| Streamlit GUI | http://localhost:8501 | Web 界面 |
| Celery Flower | http://localhost:5555 | 任务监控（可选） |
| OpenRouter Dashboard | https://openrouter.ai | API 管理 |
| ChromaDB | - | 嵌入式数据库（无 Web 界面） |

---

## ⌨️ 快捷键

### Streamlit 界面

| 快捷键 | 功能 |
|--------|------|
| `R` | 刷新页面 |
| `C` | 清除缓存 |
| `?` | 显示帮助 |

### 终端操作

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + C` | 停止进程 |
| `Ctrl + Break` | 强制终止 |
| `Ctrl + Shift + C` | 复制 |
| `Ctrl + Shift + V` | 粘贴 |

---

## 📈 性能调优

### Worker 并发调整

```bash
# 文本 Worker（根据显存调整）
celery -A src.workers.tasks worker -Q text_queue -c 1  # 8GB 显存
celery -A src.workers.tasks worker -Q text_queue -c 2  # 16GB+ 显存

# 多模态 Worker（可以更高）
celery -A src.workers.tasks worker -Q media_queue -c 4
```

### Redis 内存优化

```yaml
# docker-compose.yml
services:
  redis:
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

### Streamlit 性能

```bash
# 禁用文件监听（生产环境）
streamlit run src/gui/app.py --server.fileWatcherType none

# 限制上传大小
streamlit run src/gui/app.py --server.maxUploadSize 200
```

---

## 💰 成本估算

### 文本生成（DeepSeek-V3）

| 使用量 | 输入成本 | 输出成本 | 总计 |
|--------|----------|----------|------|
| 10 章 | ~$0.05 | ~$0.30 | ~$0.35 |
| 50 章 | ~$0.25 | ~$1.50 | ~$1.75 |
| 100 章 | ~$0.50 | ~$3.00 | ~$3.50 |

### 图片生成（Gemini 2.5 Flash Image）

| 使用量 | 成本 |
|--------|------|
| 10 张 | ~$0.50 |
| 50 张 | ~$2.50 |
| 100 张 | ~$5.00 |

### 月度预算参考

| 使用强度 | 文本 | 图片 | 总计 |
|---------|------|------|------|
| 低频（10章/月） | $0.35 | $0.50 | ~$1 |
| 中频（50章/月） | $1.75 | $2.50 | ~$5 |
| 高频（200章/月） | $7.00 | $10.00 | ~$20 |

**注意**：音频生成使用 Edge-TTS（完全免费）。

---

## 📞 获取帮助

### 查看日志

```bash
# Worker 日志（在 Worker 终端查看）
# Streamlit 日志（在 Streamlit 终端查看）

# Redis 日志
docker-compose logs redis

# 保存日志到文件
docker-compose logs > redis.log
```

### 报告问题

1. 收集信息：
   - 错误日志
   - 系统版本信息
   - 复现步骤

2. 创建 Issue：
   - GitHub Issues: https://github.com/your-org/novel-agent/issues
   - 附上日志和截图

### 社区支持

- 📖 查看文档：[docs/README.md](docs/README.md)
- 🐛 故障排查：[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- 💬 讨论区：GitHub Discussions

---

**快速链接**：
- [完整文档](docs/README.md)
- [启动指南](../README.md#-quick-start)
- [架构设计](docs/ARCHITECTURE.md)
- [API 参考](docs/API.md)

---

**最后更新**: 2026-01-24  
打印此页备查 📄
