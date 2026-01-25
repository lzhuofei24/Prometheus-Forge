# Prometheus Forge 系统功能与架构说明

本文档详细描述 Prometheus Forge 的**系统功能**与**系统架构**，包括前端页面、API、智能体、数据存储、分层设计和数据流，便于开发、运维与二次扩展。

---

## 目录

- [一、系统功能](#一系统功能)
  - [1.1 前端功能](#11-前端功能)
  - [1.2 API 功能](#12-api-功能)
  - [1.3 智能体功能](#13-智能体功能)
  - [1.4 数据与配置](#14-数据与配置)
- [二、系统架构](#二系统架构)
  - [2.1 分层架构](#21-分层架构)
  - [2.2 核心组件与依赖](#22-核心组件与依赖)
  - [2.3 数据流与工作流](#23-数据流与工作流)
  - [2.4 部署与扩展](#24-部署与扩展)
- [三、附录](#三附录)

---

## 一、系统功能

### 1.1 前端功能

前端为单页应用（SPA），使用 React + TypeScript + Vite 构建，通过导航在以下页面间切换。

| 路由 | 页面 | 功能简述 |
|------|------|----------|
| `/` | **Home（首页）** | 系统入口，展示项目名称与导航，可跳转到写作、阅读、工作流、资源监控。 |
| `/writer` | **Writer（写作工作台）** | 选择小说与章节，编辑正文/大纲，发起工作流；展示当前草稿与工作流状态。 |
| `/reader` | **Reader（阅读器）** | 按小说与章节阅读已保存的正文与大纲，支持切换章节。 |
| `/workflow` | **WorkflowMonitor（工作流监控）** | 以图（节点+边）形式展示工作流拓扑（Start → 各智能体），支持编辑路由规则；下方为实时追踪时间线，显示每个事件的类型、来源、时间与详情。 |
| `/resources` | **ResourceMonitor（资源监控）** | 展示各 Celery 队列长度、Controller 在线状态、Worker 状态等，便于运维与排障。 |

**通用能力**

- **后端连通性**：多数页面对 API 做健康检查或数据请求，并显示「后端在线/离线」等状态。
- **多语言**：通过 i18n 支持中英文切换（若已配置）。
- **主题**：支持亮色/暗色切换（若已实现）。

**技术栈**

- React 19、TypeScript、Tailwind CSS、TanStack Query、React Router、React Flow（工作流图）。

---

### 1.2 API 功能

API 层由 FastAPI 提供，挂载在 `src.api.main`，默认端口 **8000**。主要路由与职责如下。

#### 根与健康

| 方法与路径 | 说明 |
|------------|------|
| `GET /` | 根路径，返回 API 名称与版本。 |
| `GET /health` | 健康检查，返回 `api`、`redis`、`database` 等组件的状态，用于前端或负载均衡探测。 |
| `POST /admin/reload-config` | 从 `config/settings.yaml` 重新加载配置并刷新容器内配置，无需重启进程。 |

#### 工作流（`/workflow` 相关

- **发起工作流**：接收小说名称、章节号等，创建 `workflow_id`，初始化 Redis 状态，并向 Controller 队列投递「工作流已启动」类事件，由 Controller 驱动后续智能体。
- **查询状态**：按 `workflow_id` 查询当前阶段、草稿内容、是否完成等。
- **追踪日志**：按 `workflow_id` 返回审计日志列表，供前端「工作流监控」页时间线展示。

（具体路径与请求体以 `docs/API.md` 及 OpenAPI ` /docs` 为准。）

#### 小说与章节（`/novels` 等）

- 小说列表、章节列表、章节内容/大纲的增删改查。
- 与 SQLite 中 `novels`、`chapters`、`chapter_drafts` 等表对接，部分接口会使用 Redis 缓存以减轻数据库压力。

#### 监控（`/monitor` 等）

- **资源**：如 `GET /monitor/resources`，汇总各 Celery 队列长度、Controller 是否在线等，供「资源监控」页使用。
- **队列操作**：例如对指定队列做 purge（清空待执行任务），便于运维或排错。
- **Controller**：如触发 Controller 启动、对某智能体做禁用/启用等（若已实现）。

所有接口均使用 Pydantic 做请求/响应校验，并支持 CORS（允许前端开发端口如 5173、3000）。

---

### 1.3 智能体功能

智能体以 **Celery Worker** 形式运行，每个智能体绑定一个「待处理队列」。**Controller** 是独立的 Celery 任务，消费「工作流事件」，按状态机决定下一步将任务投递到哪一个智能体队列。智能体之间**不直接调用**，仅通过「事件 + 状态」协作。

#### 1. Architect（架构师）

- **队列**：`architect_pending`
- **职责**：根据小说名、章节号及既有上下文，生成该章节的**大纲**（标题、摘要、场景列表、插画描述等）。
- **输入**：来自工作流状态（如 novel_name、chapter_index、前文摘要等）。
- **输出**：大纲结构写入状态与持久层，并发出 `OUTLINE_GENERATED` 类事件，驱动下一步。

#### 2. Writer（写手）

- **队列**：`writer_pending`
- **职责**：根据大纲与上下文撰写**章节正文**；若带「修订」标记，则结合 Critic 的反馈进行重写。
- **输入**：大纲、前文上下文、可选反馈文案。
- **输出**：正文写入草稿与状态，并发出 `CONTENT_WRITTEN` 类事件。

#### 3. Critic（审稿员）

- **队列**：`critic_pending`
- **职责**：对当前章节正文做**质量评分（0–100）**并产出改进建议。
- **输入**：当前草稿正文。
- **输出**：分数、优劣势、建议；若分数 &lt; 75，由 Controller 再次向 Writer 投递修订任务（可配置最大修订次数，如 3 次）。

#### 4. Censor（审查员）

- **队列**：`censor_pending`
- **职责**：**敏感词与内容合规**检查。
- **机制**：先与本地敏感词表（如 `config/sensitive_words.txt`）匹配；若通过再可选走 LLM 深度审查。
- **输出**：是否敏感、原因、检查方式等，并发出 `CONTENT_CENSORED` 类事件。

#### 5. Knowledge（档案员）

- **队列**：`knowledge_pending`
- **职责**：从正文中**抽取实体**（角色、地点、物品等），更新 RAG 向量库与滚动摘要，供后续章节检索。
- **输出**：发出 `KNOWLEDGE_UPDATED` 类事件。

#### 6. Media（媒体）

- **队列**：`media_pending`
- **职责**：根据大纲中的场景描述或正文片段，生成**章节配图**（若启用）。
- **输出**：图片落盘或入库，并在状态中记录资源路径或 URL。

#### Controller（控制器）

- **队列**：`controller_pending`
- **职责**：消费「工作流事件」，维护当前工作流的状态机，按顺序向对应智能体队列投递任务（如先 Architect → 再 Writer → 再 Critic → 若需修订则再 Writer → 再 Censor → Knowledge → Media）。
- **实现**：通常以 Celery 任务形式存在（如 `src.workers.controller_tasks`），由 API 在「工作流启动」时向该队列投递首条事件。

---

### 1.4 数据与配置

#### 持久化存储（SQLite）

- **novels**：小说元信息（标题、创建时间等）。
- **chapters**：章节元信息（所属小说、序号、标题等）。
- **chapter_drafts**：章节草稿与版本（正文、大纲、对应章节与版本号等）。部分实现会区分「当前草稿」与历史版本。

库文件通常位于 `data/` 下（如 `data/novel_content_db/prometheus_forge.db`），具体以 `config` 或环境变量为准。

#### Redis

- **Celery**：用作 Broker 与 Result Backend（常见为 db 0/1）。
- **工作流状态**：当前阶段、草稿快照、修订次数等，键名多与 `workflow_id` 相关。
- **审计日志**：按工作流汇总的「事件列表」，供前端时间线消费。
- **缓存**：章节内容、全局设置、LLM 响应等可配置 TTL 的缓存，以减轻 DB 与 API 压力。
- **Controller 心跳**：如 `system:controller:heartbeat`，用于资源监控页判断 Controller 是否在线。

#### ChromaDB

- **用途**：RAG 向量检索。
- **内容**：由原著或已写正文切片、嵌入后写入；Knowledge 等会更新或增量写入。
- **使用场景**：Writer、Architect 等需要「与已有内容语义相近」的片段时，通过检索接口查询。

#### 配置来源

- **环境变量（.env）**：API Key（如 `OPENROUTER_API_KEY`、`SILICONFLOW_API_KEY`）、Redis 主机/端口、数据库路径等。
- **config/settings.yaml**：LLM 模型、智能体参数、路径、提示词模板路径等。
- **config/prompts/**：各环节的提示词模板（如 extraction、writing、critique 等）。
- **config/sensitive_words.txt**：Censor 使用的敏感词列表。

---

## 二、系统架构

### 2.1 分层架构

系统在逻辑上分为以下层级（自顶向下）：

```
┌─────────────────────────────────────────────────────────────────┐
│  表现层 (Presentation)                                           │
│  React SPA：Home / Writer / Reader / WorkflowMonitor / Resource  │
│  通过 HTTP 调用 FastAPI，部分数据通过 TanStack Query 缓存与轮询   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ HTTP/REST
┌───────────────────────────────▼─────────────────────────────────┐
│  API 层 (FastAPI)                                                │
│  路由：workflow、novels、monitor；健康检查；配置热重载            │
│  依赖：Core（配置、DB、状态、容器）、Services（业务封装）         │
└───────────────────────────────┬─────────────────────────────────┘
                                │ 写 Redis / 投递 Celery
┌───────────────────────────────▼─────────────────────────────────┐
│  调度与状态层                                                     │
│  Controller（Celery）：消费工作流事件，更新状态机，投递智能体任务  │
│  State Manager / Dispatcher 等：维护 Redis 中的工作流状态与事件   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ 任务入队 (Redis Queue)
┌───────────────────────────────▼─────────────────────────────────┐
│  Worker 层 (Celery)                                              │
│  Architect / Writer / Critic / Censor / Knowledge / Media        │
│  各占独立队列，无跨进程直接调用                                   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ 读/写 DB、Redis、Chroma、文件
┌───────────────────────────────▼─────────────────────────────────┐
│  数据层                                                          │
│  SQLite、Redis、ChromaDB、工作区文件系统 (workspace)              │
└─────────────────────────────────────────────────────────────────┘
```

表现层仅与 API 层通信；API 层不直接调用智能体逻辑，只写状态、发事件或投递 Celery 任务；智能体通过队列与共享状态/事件协作。

---

### 2.2 核心组件与依赖

#### 后端目录与职责（概要）

| 目录/模块 | 职责 |
|-----------|------|
| `src.api` | FastAPI 应用、路由挂载、中间件；启动时初始化 DB 与容器。 |
| `src.api.routers` | workflow / novels / monitor 等路由实现。 |
| `src.api.services` | 与 DB、状态、外部服务交互的业务封装（如 novel_service、import_service）。 |
| `src.core` | 配置加载、LLM 客户端、数据库连接、状态管理、Dispatcher、依赖注入容器等。 |
| `src.workers` | Celery 应用与任务定义（如 tasks_new、controller_tasks）、各 handler（architect、writer、critic、censor、knowledge、media）。 |
| `src.agents` | 与 LLM 直接相关的逻辑（大纲生成、正文生成、审稿、设定提取等），被 Worker 层调用。 |
| `src.rag` | 索引与检索（ChromaDB），供 agents 或 workers 使用。 |
| `src.utils` | 文件管理、导入导出等通用工具。 |

#### 前端目录与职责（概要）

| 目录/模块 | 职责 |
|-----------|------|
| `web/src/pages` | 各页面组件（Home、Writer、Reader、WorkflowMonitor、ResourceMonitor）。 |
| `web/src/components` | 可复用 UI（布局、工作流图、表单、按钮等）。 |
| `web/src/api` | 对后端 REST 的封装与类型定义。 |
| `web/src/hooks` | 数据与副作用逻辑（如 useNovels、useWorkflow、useMonitor）。 |

Controller 与各智能体的**执行顺序与依赖**由「工作流状态机 + 事件类型」决定，而不是写死在单一块代码中，便于通过配置或图编辑扩展。

---

### 2.3 数据流与工作流

#### 从「用户发起」到「工作流结束」的流程

1. **用户** 在写作页选择小说与章节，点击「开始工作流」。
2. **前端** 调用 `POST /workflow/start`（或等价接口），传入 novel_name、chapter_index 等。
3. **API** 生成 `workflow_id`，在 Redis 中初始化该工作流的状态（阶段、章节信息等），并向 Controller 队列投递「工作流已启动」事件。
4. **Controller** 收到事件，根据状态机将「生成大纲」任务投递到 `architect_pending`。
5. **Architect Worker** 执行完成后，写回大纲到状态/DB，并写入审计日志，同时发出 `OUTLINE_GENERATED` 类事件（或由 Controller 轮询/订阅状态变化）。
6. **Controller** 根据新状态，向 `writer_pending` 投递「撰写正文」任务。
7. **Writer Worker** 完成后写回正文，发出 `CONTENT_WRITTEN`。
8. **Controller** 向 `critic_pending` 投递「审稿」任务。
9. **Critic Worker** 返回分数与建议；若 &lt; 75，Controller 再向 Writer 投递「修订」任务（带反馈），重复步骤 7–9 直至通过或达最大次数。
10. **Controller** 依次投递 Censor → Knowledge → Media（若启用）；每步完成都会写审计日志并更新状态。
11. 当所有必需步骤完成后，工作流标记为完成；**前端** 通过轮询或拉取「追踪日志」接口，在 WorkflowMonitor 页展示时间线与图状态。

以上为逻辑顺序；实现上事件可能是「Controller 消费 Redis 中的事件流」或「各 Worker 完成后写入某结构再由 Controller 轮询」，以代码与 `docs/ARCHITECTURE.md` 为准。

#### 监控与可观测性

- **资源监控**：前端定期请求 `GET /monitor/resources`，展示各队列长度、Controller 心跳、Worker 在线情况。
- **工作流追踪**：前端按 `workflow_id` 拉取「追踪日志」或「事件列表」，在 WorkflowMonitor 中以时间线形式展示。
- **日志**：建议使用结构化日志（如 JSON），包含 `workflow_id`、`agent`、`task_id`、`event_type`，便于在日志系统中按工作流或智能体过滤。

---

### 2.4 部署与扩展

#### 开发环境

- **Redis**：`docker-compose up -d`。
- **API**：`uvicorn src.api.main:app --reload --port 8000`。
- **Worker**：在项目根目录执行 `start_all_workers.bat`（Windows），或按队列逐个启动 Celery worker；Controller 单独使用 `controller_pending` 队列的 worker。
- **前端**：`cd web && npm run dev`。
- **一键多标签页（若使用 Windows Terminal）**：`start_all_tabs.bat` 可同时起 API、前端与全部 Worker。

#### 生产或类生产

- 使用 `start_all.bat` / `stop_all.bat` / `restart_all.bat` 等脚本统一启停后端与 Worker（具体以仓库内脚本为准）。
- 前端构建：`cd web && npm run build`，将产物挂到 Nginx 或其他静态托管，并配置 API 代理到后端地址。

#### 水平扩展

- 每个智能体对应一个队列，可单独增加该队列的 Worker 数量（如多开几个 Writer Worker），以实现并行处理多个工作流中的「撰写」任务。
- Redis、SQLite、ChromaDB 的部署方式（单机/集群、路径、网络）需根据规模在配置与运维中统一约定。

#### 配置热重载

- 调用 `POST /admin/reload-config` 可在不重启 API 进程的前提下，重新加载 `config/settings.yaml` 及依赖该配置的模块（如通过容器或全局设置注入的部分）。Worker 若需新配置，通常需重启或自行监听配置变更。

---

## 三、附录

### 3.1 关键路径与文件（供检索）

| 用途 | 路径或说明 |
|------|------------|
| API 入口 | `src/api/main.py` |
| 工作流路由 | `src/api/routers/workflow.py` |
| 小说/章节路由 | `src/api/routers/novels.py` |
| 监控路由 | `src/api/routers/monitor.py` |
| Controller 任务 | `src/workers/controller_tasks.py` |
| 智能体任务定义 | `src/workers/tasks_new.py`、handlers 子目录 |
| 前端路由与页面 | `web/src/App.tsx`、`web/src/pages/*` |
| 工作流监控页 | `web/src/pages/WorkflowMonitor.tsx` |
| 配置 | `config/settings.yaml`、`.env` |
| 敏感词表 | `config/sensitive_words.txt` |

### 3.2 脚本与工具（概要）

- **start_all_tabs.bat**：在 Windows Terminal 中分标签页启动 API、前端、以及 Architect/Writer/Critic/Censor/Knowledge/Media/Controller 各 Worker。
- **start_all_workers.bat**：仅启动上述 Celery Worker，不启 API 与前端。
- **scripts/**：安装依赖、迁移、测试、清理队列等（见 `scripts/README.md`、`docs/SCRIPTS.md`）。
- **tools/**：如 `switch_model.py`、`diagnose_network.py` 等（见 `docs/PROJECT_STRUCTURE.md`）。

### 3.3 相关文档

| 文档 | 内容 |
|------|------|
| [README.md](../README.md) / [README-zh.md](../README-zh.md) | 项目简介、快速开始、文档索引。 |
| [API.md](API.md) | 接口路径、请求/响应示例。 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 历史版架构与模块说明。 |
| [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) | 系统概览与工作流简述。 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发环境与贡献流程。 |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 常见问题与排查。 |

---

*文档版本与项目状态以仓库内实际代码与配置为准；若接口或组件有变更，请以代码和 OpenAPI 文档为准。*
