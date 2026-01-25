# Prometheus Forge 架构详解

本文描述当前系统的分层架构、核心组件、事件与队列模型、数据流及扩展方式。与「系统功能」相关的页面与 API 清单见 [SYSTEM_FUNCTIONS_AND_ARCHITECTURE.md](SYSTEM_FUNCTIONS_AND_ARCHITECTURE.md)。

---

## 目录

- [系统概览](#系统概览)
- [分层架构](#分层架构)
- [事件与队列模型](#事件与队列模型)
- [核心模块](#核心模块)
- [数据流](#数据流)
- [扩展与运维](#扩展与运维)

---

## 系统概览

Prometheus Forge 采用**事件驱动 + 分布式任务**：前端与 API 负责请求与展示，实际章节生成由多类 **Celery Worker** 执行，**Controller** 通过 Redis 的「完成队列」驱动下一步，智能体之间**仅通过事件与共享状态**协作，无进程间直接调用。

### 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| 前端 | React 19、TypeScript、Vite、Tailwind、TanStack Query、React Flow | 单页应用，写作 / 阅读 / 工作流监控 / 资源监控 |
| API | FastAPI、Pydantic、SQLAlchemy（async + aiosqlite） | 工作流启停、小说与章节 CRUD、监控与管控 |
| 任务队列 | Celery 5.3+、Redis | Broker / Result Backend；每类 Agent 独占 `*_pending` 队列 |
| 编排 | Controller（独立进程） + Redis List（`*_completed`） | 消费完成事件，按路由规则投递下一类任务 |
| 持久化 | SQLite | 小说、章节、草稿、审稿数据 |
| 状态与日志 | Redis | 工作流状态、审计日志、心跳、队列深度 |
| 向量 | ChromaDB、SentenceTransformers（bge-small-zh） | 检索与上下文增强 |
| LLM | OpenAI 兼容 API（OpenRouter、SiliconFlow 等） | 由 `src.core.llm.LLMClient` 统一封装 |

---

## 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    展示层 (Presentation)                          │
│              React SPA — Home / Writer / Reader /                 │
│              WorkflowMonitor / ResourceMonitor                    │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP (REST)
┌─────────────────────────────▼───────────────────────────────────┐
│                     API 层 (FastAPI)                              │
│   /workflow/* 启停与状态  /novels、/novels/…/chapters  CRUD      │
│   /monitor/resources、/health、/admin/reload-config               │
└─────────────────────────────┬───────────────────────────────────┘
                              │ send_task → Redis (Broker)
┌─────────────────────────────▼───────────────────────────────────┐
│                   任务层 (Celery Workers)                         │
│  architect_pending → ArchitectHandler                            │
│  writer_pending    → WriterHandler     (含 revise)               │
│  critic_pending    → CriticHandler                               │
│  censor_pending    → CensorHandler                               │
│  knowledge_pending → KnowledgeHandler                            │
│  media_pending     → MediaHandler                                │
│  controller_pending→ Controller 循环（消费 *_completed）          │
└─────────────────────────────┬───────────────────────────────────┘
                              │ Redis List (*_completed)
                              │ StateManager (状态/审计)
┌─────────────────────────────▼───────────────────────────────────┐
│                   编排层 (Controller)                             │
│  blpop(architect_completed, writer_completed, …)                 │
│  → 路由规则 → send_task(下一 Agent, 对应 *_pending)               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                   数据层 (Data)                                   │
│  Redis: Broker、Backend、工作流状态、审计日志、心跳、队列长度      │
│  SQLite: novels / chapters / chapter_drafts 等                    │
│  ChromaDB: 向量索引                                               │
│  文件系统: workspace/ 章节与资源文件                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 事件与队列模型

### 队列命名与职责

| 类型 | 队列名 | 消费者 | 说明 |
|------|--------|--------|------|
| Celery 任务队列 | `architect_pending` … `censor_pending` | 同名 Celery Worker | 各 Agent 的待执行任务 |
| Celery 任务队列 | `controller_pending` | Controller Worker | 仅用于承载 `controller.run_loop` 长任务，不用于「下一步」投递 |
| Redis List（完成） | `architect_completed` … `censor_completed` | Controller 进程内 `blpop` | Agent 完成后写入，Controller 据此派发下一步 |
| Redis List（挂起） | `*_suspended` | 运维/监控 | Agent 被禁用时任务暂存，可后续恢复 |

路由与入口在 `src.core.celery_config` 中统一配置；Controller 的监听队列与路由规则在 `src.core.controller.CentralController` 中定义。

### 工作流生命周期

1. **启动**：前端或调用方请求 `POST /workflow/start`，传入 `novel_name`、`chapter_num`。API 生成 `workflow_id`，初始化 Redis 状态，并直接 `send_task("architect.generate_outline", queue="architect_pending", args=[workflow_id, novel_name, chapter_num])`。
2. **Architect → Writer → Censor → Critic**：每个 Agent 的 Handler 在结束后调用基类 `_post_process`，将结果写入 `{agent}_completed`（Redis List）。Controller 的 `run_loop` 使用 `blpop(listen_queues)` 取出消息，根据 `source` 与路由规则决定下一跳，再 `send_task(下一 Agent 任务, 对应 _pending 队列)`。
3. **Critic 分支**：  
   - 若 `score >= 75`：向 `media_pending`、`knowledge_pending` 各投递一任务（并行），二者完成后不再派发新 Agent，工作流在 Controller 侧视为结束。  
   - 若 `score < 75` 且 `revision_count < 3`：向 `writer_pending` 投递修订任务（`writer.revise_content`），并递增 `revision_count`；Writer 完成后再走 Censor → Critic，直到达标或达最大修订次数。
4. **结束**：当某步之后没有「下一 Agent」时，Controller 将对应 workflow 状态置为 `completed`；若任一步骤上报 `status != SUCCESS`，则置为 `failed` 并记录错误信息。

### Controller 路由规则摘要

（与 `CentralController._build_routing_rules` 一致，具体以代码为准。）

- **architect** → 总是派发到 **writer**。
- **writer** → **censor**。
- **censor** → **critic**（若未命中敏感则继续；否则可配置为不派发或走旁路）。
- **critic**：  
  - `score >= 75` → **media**、**knowledge**（多路并行）；  
  - 否则且未超修订次数 → **writer**（修订）。

---

## 核心模块

### 1. API（`src/api/`）

- **main.py**：FastAPI 应用、CORS、`/health`、`/admin/reload-config`，挂载各路由。
- **routers/workflow.py**：`POST /workflow/start` 启动作业并投递 Architect；`GET /workflow/{id}/state`、`/workflow/{id}/trace` 查询状态与审计日志。
- **routers/novels.py**：小说与章节的创建、列表、内容/大纲的读写，依赖 `NovelService` 与 SQLite。
- **routers/monitor.py**：队列长度、Controller 心跳、Worker 禁用/执行中状态等，供 ResourceMonitor 使用；可含队列 purge、Controller 启停等运维接口。

### 2. Core（`src/core/`）

- **controller.py**：`CentralController` 实现 `run_loop()`，对 `*_completed` 做 `blpop`，解析 JSON 后调用 `decide_next_step`、`dispatch_task`，并更新 `StateManager` 中的 workflow 状态。
- **state_manager.py**：以 Redis 存储 workflow 状态（如 `novel_name`、`chapter_num`、`outline`、`draft_content`、`critique_score`、`revision_count` 等）与按 workflow 聚合的审计日志，供 API 与 Controller 使用。
- **dispatcher.py**：接收事件载荷（如来自 Handler 的完成事件），可做日志、统计或二次派发；与「下一步派发」的主要逻辑在 Controller 内。
- **events.py**：定义 `EventType`、`EventSource`、`AuditLogEntry`、`EventPayload` 等，统一事件类型与审计字段。
- **celery_config.py**：Celery app、Broker/Backend、各 `*_pending` 及 `controller_pending` 队列、任务路由、worker 池（如 solo）等。
- **app_settings.py**：从环境或配置读取 Redis 地址、数据库路径等，供 API、Worker、Controller 复用。
- **database.py / db_service.py**：SQLite 连接、会话、Novel/Chapter 等实体的访问封装。
- **llm.py**：`LLMClient` 对 OpenAI 兼容 API 的封装（模型、温度、重试等）。
- **config.py**：基于 YAML 的 `Settings`，包含模型、路径、Agent 相关参数等。
- **container.py**：依赖注入容器，用于在 API 或 Worker 内解析 StateManager、Cache、LLM 等。
- **workflow_lock.py**：基于 Redis 的锁，避免同一 workflow 被多 Worker 并发写。

### 3. Workers 与 Handlers（`src/workers/`）

- **tasks_new.py**：定义并注册各 Agent 的 Celery 任务（如 `architect.generate_outline`、`writer.write_content`、`writer.revise_content`、`critic.critique_content` 等），在任务体内初始化 `StateManager`、`Dispatcher`、`LLMClient`、`ProjectManager` 等，并调用对应 Handler 的 `execute`。
- **controller_tasks.py**：定义 `controller.run_loop` 等任务；Controller Worker 启动后通过 `worker_ready` 信号拉起 `run_loop`，在进程内执行 `CentralController.run_loop()`。
- **base.py**：`BaseAgentHandler` 抽象基类，实现 `execute` 的模板流程（`_pre_process` → `_process` → `_post_process`），其中 `_post_process` 负责更新状态、写审计、向 Dispatcher 发事件、并 `rpush` 到 `{agent}_completed`。
- **handlers/**：各 Agent 的具体逻辑。  
  - **architect.py**：拉取上下文与设定，调用 LLM 生成大纲，写入状态与文件。  
  - **writer.py**：按大纲与上下文生成或修订正文，写入草稿与状态。  
  - **critic.py**：对正文评分与建议，写入状态。  
  - **censor.py / knowledge.py / media.py：敏感词与可选 LLM 审查、实体抽取与 RAG 更新、配图生成等。

### 4. Agents（`src/agents/`）

与 LLM 直接交互的「纯逻辑」组件，被 Handlers 或旧版 tasks 调用，负责组 prompt、调 `LLMClient`、解析结果。包括但不限于：

- **builder.py**：上下文组装、token 控制。  
- **editor.py**：审稿/润色相关 prompt 与解析。  
- **novelist.py** / **writer.py**：章节与场景级写作逻辑。  
- **planner.py**：与架构/规划相关的 prompt。  
- **reviewers/**：人物/剧情/风格等专项检查（若被接入流水线）。

### 5. RAG（`src/rag/`）

- **indexer.py**：将文本切片、向量化后写入 ChromaDB。  
- **retriever.py**：按查询向量做相似检索，供写作或知识更新使用。

### 6. 前端（`web/src/`）

- **pages/Home.tsx**：首页与导航。  
- **pages/Writer.tsx**：小说/章节选择、正文与大纲编辑、工作流启动与状态展示。  
- **pages/Reader.tsx**：按小说与章节阅读已保存内容。  
- **pages/WorkflowMonitor.tsx**：工作流图（React Flow）与追踪时间线，数据来自 `/workflow/{id}/state`、`/workflow/{id}/trace`。  
- **pages/ResourceMonitor.tsx**：队列长度、Controller 在线、Worker 状态等，数据来自 `/monitor/resources` 等。

---

## 数据流

### 章节生成主流程（简化）

```
用户在前端点击「发起工作流」
    → POST /workflow/start { novel_name, chapter_num }
    → API 生成 workflow_id，StateManager.init_workflow(...)
    → send_task(architect.generate_outline, architect_pending, [workflow_id, novel_name, chapter_num])
    → 返回 { workflow_id, status: "started", task_id }

Architect Worker 执行
    → ArchitectHandler.execute(workflow_id, { novel_name, chapter_num })
    → 读设定/前文 → LLM 生成大纲 → 写状态与 outline 文件
    → _post_process: 更新状态、写审计、rpush(architect_completed, payload)

Controller run_loop
    → blpop(architect_completed, …) 取到 architect 的 payload
    → decide_next_step("architect", data) → ["writer"]
    → dispatch_task(workflow_id, "writer") → send_task(writer.write_content, writer_pending, [workflow_id])

Writer Worker → 同理完成后 rpush(writer_completed) → Controller → censor_pending → …

Critic 完成后
    → 若 score>=75：dispatch media + knowledge；二者均完成后不再派发，status=completed
    → 若 score<75 且 revision_count<3：dispatch writer.revise_content，revision_count+1
```

前端通过轮询或跳转调用 `GET /workflow/{id}/state` 与 `GET /workflow/{id}/trace` 展示进度与时间线。

### 状态与审计的存储

- **状态**：以 `workflow:{id}` 等形式存在 Redis（见 `StateManager`），包含 `novel_name`、`chapter_num`、`outline`、`draft_content`、`critique_score`、`critique_comments`、`revision_count`、`status` 等。
- **审计日志**：按 workflow 聚合的列表，每条包含时间、来源、事件类型、详情等，用于 Trace 时间线。
- **持久化**：章节正文与大纲在流程中会写入 SQLite（通过 db_service）及/或 workspace 下文件，具体以实现为准。

---

## 扩展与运维

### 水平扩展

- 每类 Agent 对应一个 `*_pending` 队列，可对同一队列启动多个 Worker（若任务无强顺序需求）。  
- Controller 仅需单实例，多实例会竞态消费同一 `*_completed`，一般不扩容。  
- Redis、SQLite 可按需改为集群或独立 DB，需同步改动 `app_settings`、`database`、`StateManager` 等。

### 增加新 Agent

1. 在 `celery_config` 中增加新队列与路由（如 `new_agent_pending`、`new_agent.*`）。  
2. 在 Controller 的 `listen_queues` 与 `_build_routing_rules` 中增加 `new_agent_completed` 及从谁→到新 Agent、从新 Agent→到谁的规则。  
3. 在 `src/workers/handlers/` 下实现新 Handler（继承 `BaseAgentHandler`），在 `tasks_new` 中注册新任务并调用该 Handler。  
4. 在 `base.py` 的 `_get_agent_name` / `_get_source` 等中增加对新 Agent 的映射（若使用统一完成推送）。

### 配置与密钥

- 应用配置：`config/settings.yaml`，可由 `POST /admin/reload-config` 热更部分内容。  
- 密钥与环境相关：`.env`（不纳入版本库），如 `OPENROUTER_API_KEY`、`SILICONFLOW_API_KEY`、Redis  Host/Port 等，通过 `app_settings` 或 `Settings` 读取。

### 监控与排错

- **资源与队列**：`GET /monitor/resources` 提供各 `*_pending` / `*_completed` 长度、Controller 心跳、Agent 禁用/执行中标记。  
- **工作流**：`GET /workflow/{id}/state`、`/workflow/{id}/trace` 用于排查单次运行进度与事件顺序。  
- **日志**：Worker 与 API 使用标准 logging；结构化日志见 `structured_logger`，便于按 `workflow_id`、`agent` 检索。

### 部署形态

- **单机**：Redis（Docker）、API（uvicorn）、前端（npm run build + 静态托管）、所有 Celery Worker + Controller 同机运行，SQLite 与 ChromaDB 放本地目录。  
- **多机**：API 与前端可放在 Web 层；Worker 按队列分组部署到不同节点，共享同一 Redis Broker 与 DB 路径（或迁到 PostgreSQL 等），Controller 仍建议单实例。

---

## 相关文档

- [系统功能与架构](SYSTEM_FUNCTIONS_AND_ARCHITECTURE.md) — 功能清单与接口概览  
- [API 参考](API.md) — 路由与请求/响应  
- [故障排查](TROUBLESHOOTING.md) — 常见问题与处理  
- [项目结构](PROJECT_STRUCTURE.md) — 目录与文件组织
