# Prometheus Forge

**Igniting Creative Intelligence Through Event-Driven Orchestration**

*普罗米修斯工坊 / 火种工坊*

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.9-blue.svg)](https://www.typescriptlang.org/)
[![Celery](https://img.shields.io/badge/Celery-5.3+-green.svg)](https://docs.celeryq.dev/)
[![Redis](https://img.shields.io/badge/Redis-7.0+-red.svg)](https://redis.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

事件驱动的多智能体小说创作系统，具备全链路可观测、向量检索上下文、知识图谱与自动质量反馈环。

---

## 概述

**Prometheus Forge** 是一套基于事件与队列的分布式 AI 小说创作编排引擎。采用 **FastAPI + React** 前后端分离架构，**Celery + Redis** 作为任务与状态中间件，**ChromaDB** 做向量检索，**SQLite** 做小说与章节持久化，**GraphRAG** 构建知识图谱。

### 核心能力

- **多智能体流水线**：Architect → Writer → Censor → Critic →（按需修订）→ Media / Knowledge，由 **Controller** 根据完成事件驱动下一步
- **自动反馈环**：Critic 评分（0–100）；若 < 75 则触发 Writer 修订，最多可配置次数（默认 3 次）
- **端到端可观测**：每个智能体步骤写入审计日志，前端「工作流监控」页展示实时追踪与拓扑图
- **向量与结构化上下文**：ChromaDB 与近期章节、大纲等共同支撑长线剧情一致性
- **知识图谱可视化**：2-Hop 同心圆布局的 GraphRAG 探索界面，支持时空维度过滤与节点聚焦

---

## 功能概览

### 多智能体系统

| 智能体 | 队列 | 职责 |
|--------|------|------|
| **Architect** | `architect_pending` | 根据上下文生成章节大纲（标题、场景、插画描述等） |
| **Writer** | `writer_pending` | 按大纲撰写正文；支持带 Critic 反馈的修订 |
| **Censor** | `censor_pending` | 敏感词表 + 可选 LLM 安全审查 |
| **Critic** | `critic_pending` | 质量评分与改进建议；< 75 分触发修订 |
| **Knowledge** | `knowledge_pending` | 从正文抽取实体关系，更新 RAG 向量库与知识图谱 |
| **Media** | `media_pending` | 按场景描述生成章节配图（可选） |

**Controller** 作为独立进程，监听各智能体的 `*_completed` 队列，按路由规则将下一步任务投递到对应 `*_pending` 队列，智能体之间仅通过事件与状态协作，无直接调用。

### 前端页面（React SPA）

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 首页 (Home) | 入口、品牌与能力简介、快捷导航 |
| `/writer` | 写作 (Writer) | 选小说与章节，编辑正文/大纲/检索，发起工作流，查看任务与状态 |
| `/retrieval` | 检索 (RetrievalAssistant) | 管理各小说章节的向量索引，供写作页检索使用 |
| `/inspector` | 索引洞察 (IndexInspector) | 向量索引透视与知识图谱可视化，支持 2-Hop 同心圆布局 |
| `/approvals` | 审批 (ApprovalAssistant) | 按启动形式与运行筛选待审批项，对比待写入与原有内容，通过/拒绝 |
| `/reader` | 阅读 (Reader) | 按小说与章节阅读已保存正文（Markdown 渲染） |
| `/prompts` | Prompt (PromptManager) | 按 key + 流程类型管理提示词模板 |
| `/workflow` | 监控 (WorkflowMonitor) | 工作流拓扑图、实时追踪、Controller 与队列状态、启动与清理 |
| `/help` | 帮助 (Help) | 系统概念管理，统一全站术语（如「流程类型」「运行」） |

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19、TypeScript、Vite、Tailwind CSS、TanStack Query、React Flow、react-force-graph-2d |
| API | FastAPI、Pydantic、SQLAlchemy（async + aiosqlite） |
| 任务与状态 | Celery（solo 池）、Redis（Broker / 工作流状态 / 审计日志） |
| 持久化 | SQLite（小说、章节、草稿、提示词模板） |
| 向量检索 | ChromaDB、Sentence Transformers（bge-small-zh） |
| 知识图谱 | GraphRAG（实体抽取、关系构建、时空属性） |
| LLM | OpenAI 兼容 API（OpenRouter、SiliconFlow 等） |

---

## 快速开始

### 环境要求

- **Python 3.10+**（推荐 Conda）
- **Node.js 18+**
- **Docker**（用于 Redis）
- **Redis**（如通过 `docker-compose up -d` 启动）

### 1. 克隆与环境

```bash
git clone <your-repo-url>
cd novel-agent

conda env create -f environment.yml
conda activate novel-agent
```

### 2. 环境变量与配置

```bash
cp .env.example .env
# 编辑 .env：配置 OPENROUTER_API_KEY 或 SILICONFLOW_API_KEY 等
```

### 3. 启动 Redis

```bash
docker-compose up -d
```

### 4. 启动后端与 Worker

**方式 A：一键多标签页（Windows Terminal）**

会依次启动 API、前端以及全部 Celery Worker（含 Controller）：

```bash
start_all_tabs.bat
```

**方式 B：分别启动**

```bash
# 终端 1：API
uvicorn src.api.main:app --reload --port 8000

# 终端 2：所有 Worker（Architect / Writer / Critic / Censor / Knowledge / Media / Controller）
start_all_workers.bat

# 或按需单独启动某个 Worker，例如：
# celery -A src.workers.tasks_new worker -n architect@%h -Q architect_pending -c 1 -P solo --loglevel=info
```

### 5. 启动前端

```bash
cd web
npm install
npm run dev
```

- 前端：**http://localhost:5173**
- API：**http://localhost:8000**
  - 健康检查：`GET http://localhost:8000/health`
  - 接口文档：`http://localhost:8000/docs`

### 6. 快速自检

1. 打开 **http://localhost:5173**，确认后端状态为「在线」
2. 进入 **写作**，选择或新建小说与章节，发起一次工作流
3. 打开 **监控**，观察拓扑图与追踪时间线是否随执行更新
4. 进入 **索引洞察**，查看向量索引与知识图谱可视化

---

## 项目结构

```
novel-agent/
├── src/
│   ├── api/              # FastAPI 应用与路由（workflow, novels, monitor, inspector）
│   ├── core/             # 配置、LLM、状态管理、Controller、Dispatcher、DB
│   ├── workers/          # Celery 任务（tasks_new, controller_tasks）与各 Agent Handler
│   ├── agents/           # 与 LLM 交互的逻辑（builder, editor, novelist, writer 等）
│   ├── rag/              # ChromaDB 索引与检索
│   ├── utils/            # 文件管理、导入等
│   └── gui/              # Streamlit GUI（可选）
├── web/                  # React 前端（Vite + TS）
│   └── src/
│       ├── pages/        # 各页面组件
│       ├── components/   # 可复用组件
│       ├── hooks/        # 自定义 Hooks
│       └── api/          # API 客户端
├── config/               # settings.yaml、prompts、sensitive_words.txt
├── data/                 # SQLite、ChromaDB、小说内容库
├── workspace/            # 用户创作目录（由 .gitignore 排除）
├── scripts/              # 辅助脚本（数据库迁移、测试等）
├── docs/                 # 架构、API、开发与排障文档
├── start_all_tabs.bat    # 一键启动所有服务（多标签页）
└── start_all_workers.bat # 仅启动 Celery Worker
```

---

## 核心特性

### 1. 事件驱动架构

智能体之间完全解耦，通过 Redis 队列与事件通信。Controller 作为中央调度器，根据工作流状态自动路由任务。

### 2. 自动质量反馈环

Critic 智能体对生成内容进行评分，低于阈值时自动触发 Writer 修订，形成闭环优化。

### 3. 向量检索增强

基于 ChromaDB 的语义搜索，支持长线剧情一致性维护。可在写作页进行上下文检索，辅助创作。

### 4. 知识图谱可视化

- **2-Hop 同心圆布局**：点击节点自动聚焦，中心节点 + 直接邻居（Level 1）+ 间接邻居（Level 2）形成同心圆结构
- **时空维度过滤**：通过章节滑块过滤不同时间点的关系网络
- **节点语义化展示**：根据节点类型（人物/地点/物品/概念）使用不同颜色和大小
- **关系标签**：连线上的关系名称清晰可见，支持彩色区分

### 5. 全链路可观测

工作流监控页面提供实时拓扑图、追踪时间线、队列状态等，便于调试与运维。

---

## 内容合规与工作区

- **代码与提示词**：各智能体使用的系统提示均要求遵守适用法律法规与内容安全规范，不诱导生成违法、政治敏感、色情或其它有害内容
- **工作区**：`workspace/` 用于用户创作的小说与资源，已通过 `.gitignore` 排除在版本控制之外。请勿在其中存放违禁内容；用户对本地工作区内容负责

---

## 文档索引

完整文档列表与阅读顺序见 **[docs/README.md](docs/README.md)**。常用入口：

| 文档 | 说明 |
|------|------|
| [系统概览](docs/SYSTEM_OVERVIEW.md) | 架构、智能体、队列、技术栈概览 |
| [快速参考](docs/QUICK_REFERENCE.md) | 一页纸速查：启动方式、常用命令 |
| [前端页面文档](docs/PAGES.md) | 首页、写作、检索、索引洞察、审批、阅读、Prompt、监控、帮助——各页介绍、架构与技术说明 |
| [架构详解](docs/ARCHITECTURE.md) | 分层、模块、队列与 Controller、数据流与扩展 |
| [API 参考](docs/API.md) | FastAPI 路由与请求/响应说明 |
| [开发指南](docs/DEVELOPMENT.md) | 开发环境与扩展方式 |
| [故障排查](docs/TROUBLESHOOTING.md) | 常见问题与处理 |

---

## 路线图

- **当前**：事件驱动流水线、可观测 UI、自动修订环、向量与结构化上下文、知识图谱可视化
- **计划**：RAG 与检索增强、可选本地 LLM（如 Ollama）、WebSocket/流式输出、多小说与权限细化、图谱编辑功能

---

## 许可证

MIT。详见 [LICENSE](LICENSE)。

---

## 致谢

[FastAPI](https://fastapi.tiangolo.com/)、[React](https://react.dev/)、[Celery](https://docs.celeryq.dev/)、[Redis](https://redis.io/)、[ChromaDB](https://www.trychroma.com/)、[react-force-graph-2d](https://github.com/vasturiano/react-force-graph)。
