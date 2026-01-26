# 前端页面文档

本文档描述 Prometheus Forge 前端 SPA 中八个主要页面的**介绍**、**架构**与**技术**实现，便于开发与维护时快速对齐能力与数据流。

顶栏导航顺序：**首页** → **写作** → **检索** → **审批** → **阅读** → **Prompt** → **监控** → **帮助**。路由与入口见 [App.tsx](../web/src/App.tsx)、[MainLayout.tsx](../web/src/components/layout/MainLayout.tsx)。

---

## 1. 首页 (Home)

**路由**：`/`  
**组件**：`web/src/pages/Home.tsx`

### 介绍

- **用途**：产品落地页与快捷入口。展示品牌标题（Prometheus Forge）、slogan（Igniting Creative Intelligence Through Event-Driven Orchestration）、能力简介与快捷导航。
- **面向用户**：首次访问用户、需要快速跳转到写作/阅读/监控等功能的用户。
- **能力简介**：多智能体流水线、自动反馈环、端到端可观测、向量与上下文（ChromaDB + 近期章节与大纲）。

### 架构

- **在系统中的位置**：入口页，无业务状态与持久化；仅通过路由跳转进入写作、阅读、监控等页面。
- **与其它模块的关系**：使用 `useConcepts` 解析「监控」等展示文案，与帮助页维护的「系统概念」一致；快捷链接指向 `/writer`、`/reader`、`/workflow`，以及 `/resources`（当前路由将 `/resources` 重定向到 `/`，即回到首页）。

### 技术

- **状态**：无业务 API 请求；`useConcepts()` 用于术语展示。
- **UI**：静态 Hero + 能力卡片（FEATURES）+ 快捷导航按钮（QUICK_LINKS），基于 Tailwind 与渐变背景。
- **关键依赖**：`react-router-dom`（`useNavigate`）、`useConcepts`、`lucide-react`。

---

## 2. 写作 (Writer)

**路由**：`/writer`  
**组件**：`web/src/pages/Writer.tsx`

### 介绍

- **用途**：小说创作与工作流控制中心。用户在此选择小说与章节，编辑正文/大纲，进行向量检索，并启动各类工作流（生成新章节、仅大纲、仅正文、仅审批、仅媒体等）。
- **面向用户**：作者、编辑，需在统一界面完成选书、看目录、写/改内容、触发 AI 流水线并查看任务状态。

### 架构

- **在系统中的位置**：核心创作与编排入口。左侧为小说与章节目录，中部为正文/大纲/检索三个 Tab 与编辑器或检索区，右侧为按「流程类型」划分的启动区块及该类型下的任务列表。
- **数据流**：
  - **小说与章节**：`useNovels`、`useChapters`、`useChapterContent`、`useCreateChapter`、`useSaveChapter`、`useDeleteChapter`，对应 novels/chapters 相关 API（`chaptersApi`、services）。
  - **工作流**：`useWorkflowState`、`useStartWorkflow`、`useWorkflowTasks`、`workflowApi`；流程类型常量如 `WORKFLOW_ID_GENERATE_CHAPTER`、`WORKFLOW_ID_OUTLINE_ONLY` 等与后端一致。
  - **检索**：`retrievalApi` 的检索接口，用于「检索」Tab 内的向量搜索；结果类型 `RetrievalSearchItem`。

### 技术

- **布局**：`react-resizable-panels`（PanelGroup / Panel / PanelResizeHandle）实现左-中-右可调面板。
- **组件**：`ProjectSwitcher`、`ChapterList`、`EditorArea`（来自 `components/writer/`）；右侧为 `WorkflowLaunchBlock`（内联组件），按流程类型展示「启动」按钮与任务列表。
- **状态**：`selectedNovelId`、`selectedChapterIndex` 持久化到 `localStorage`（`writer_selectedNovelId`、`writer_selectedChapterIndex`）；`editMode` 在 `body` | `outline` | `retrieval` 间切换；检索侧有 `retrievalQuery`、`retrievalResults`、`retrievalLoading`。
- **API / Hooks**：`useNovels`、`useChapters`、`useChapterContent`、`useCreateChapter`、`useSaveChapter`、`useDeleteChapter`、`useWorkflowState`、`useStartWorkflow`、`useWorkflowTasks`、`workflowApi`、`chaptersApi`、`retrievalApi`；`useConcepts` 用于流程类型等术语。

---

## 3. 检索 (Retrieval Assistant)

**路由**：`/retrieval`  
**组件**：`web/src/pages/RetrievalAssistant.tsx`

### 介绍

- **用途**：管理所有小说的向量索引。用户可按「已索引小说」筛选，对选中小说查看已索引章节，并执行「添加索引」或「删除索引」；未选书时展示「按小说添加索引」的入口。
- **面向用户**：需要为某本书、某几章建立或维护 ChromaDB 索引的用户；索引供「写作」页的「检索」Tab 使用。

### 架构

- **在系统中的位置**：向量索引管理端。与 RAG/ChromaDB 对应；写作页的检索能力依赖此处维护的索引。
- **数据流**：
  - 已索引列表：`retrievalApi.listIndexed()`，按小说聚合（`IndexedNovel`）。
  - 小说与章节列表：`useNovels`、`useChapters`，与写作/阅读共用数据源。
  - 变更：`retrievalApi.addIndex(novel_id, chapter_index)`、`retrievalApi.deleteIndex(novel_id, chapter_index?)`，成功后使 `['retrieval']` 查询失效以刷新列表。

### 技术

- **状态**：`selectedNovelId`、`addingNovelId`、`addingChapterIndex`；TanStack Query 的 `['retrieval', 'indexed']`、`addIndexMutation`、`deleteIndexMutation`。
- **UI**：左侧「已索引小说」列表 + 右侧选中书下的「已索引章节」与按章「添加索引」/「删除索引」；`retrievalApi` 来自 `api/client.ts`。
- **关键依赖**：`useNovels`、`useChapters`、`retrievalApi`、`IndexedNovel`。

---

## 4. 审批 (Approval Assistant)

**路由**：`/approvals`  
**组件**：`web/src/pages/ApprovalAssistant.tsx`

### 介绍

- **用途**：对待写入内容进行人工审批。左侧三层导航为「启动形式 → 运行 → 待审批项」，右侧对比「待写入内容」与「原有内容」，支持正文/大纲切换，提供通过/拒绝操作。
- **面向用户**：编辑、审核员，在流水线产生待写入草稿后做终审决策。

### 架构

- **在系统中的位置**：工作流中「待审批」节点的处置界面。与后端审批服务（approval_service、approvals 路由）协同，通过/拒绝后更新工作流与章节状态。
- **数据流**：
  - 启动形式与运行列表：`approvalsApi.listWorkflowTypesWithPending('pending')`、`approvalsApi.listWorkflowsWithPending('pending', workflowType?)`。
  - 待审批列表与详情：`approvalsApi.listPending('pending', workflowId?, workflowType?)`、`approvalsApi.getDetail(pendingId)`。
  - 操作：`approvalsApi.approve(id)`、`approvalsApi.reject(id)`；通过后会失效 `['approvals']` 与 `['novels', novelId, 'chapters']`，保证写作/阅读侧目录与内容一致。

### 技术

- **轮询**：上述列表与类型查询 `refetchInterval: 10000`（约 10 秒）。
- **术语**：`useConcepts` 的 `getConceptLabel('run')` 用于「运行」等文案，与帮助页概念一致。
- **UI**：三层左侧栏（启动形式 / 运行 / 待审批项）+ 右侧对比视图（`viewMode: 'body' | 'outline'`）、通过/拒绝按钮；使用 `WORKFLOW_TYPE_LABELS`、`PendingItem`、`PendingDetail` 等类型与常量（`api/client`）。

---

## 5. 阅读 (Reader)

**路由**：`/reader`  
**组件**：`web/src/pages/Reader.tsx`

### 介绍

- **用途**：按小说与章节阅读已保存的正文，支持 Markdown 渲染、上一章/下一章、侧栏折叠与全屏等。
- **面向用户**：作者与读者，用于通读已持久化的章节内容，不涉及编辑与工作流。

### 架构

- **在系统中的位置**：只读消费端。与写作页共用「小说 + 章节」数据源与 `ProjectSwitcher`、`ChapterList`，但不调用工作流、审批或检索 API。
- **数据流**：`useNovels`、`useChapters`、`useChapterContent`；章节正文由 `chaptersApi.get(novelId, chapterIndex)` 提供（含 wordcount 等查询）。无审批、工作流、检索依赖。

### 技术

- **布局**：`react-resizable-panels`，左栏小说/章节、中部正文区域；支持窄屏与侧栏显隐。
- **正文展示**：`ReactMarkdown` 渲染 `chapterContent?.content`。
- **状态**：`selectedNovelId`、`selectedChapterIndex`、`showNav`、`showSidebar`、`isNarrow` 等；可选 `wordCounts` 用于章节字数展示（来自多查询 `useQueries` 聚合）。
- **组件**：与写作共用 `ProjectSwitcher`、`ChapterList`；阅读特有导航（上一章/下一章、全屏等）。

---

## 6. Prompt (Prompt Manager)

**路由**：`/prompts`  
**组件**：`web/src/pages/PromptManager.tsx`

### 介绍

- **用途**：按 key + workflow_type 管理提示词模板。左侧为「系统预期 key」与库中已有项的合并列表，右侧为选中项的 description / content 编辑，支持按流程类型筛选。
- **面向用户**：运营或高级用户，需要调整各智能体所用提示词以控制风格、合规或流程行为。

### 架构

- **在系统中的位置**：配置层。模板被 Architect、Writer、Critic 等智能体通过 `prompt_loader` 等从 DB 加载，此处提供集中编辑与按流程类型维度的视图。
- **数据流**：
  - 模板列表与预期 key：`promptApi.getAll(workflowFilter?)`、`promptApi.getExpectedKeys()`；流程类型列表来自 `workflowApi.getTypes()`。
  - 单条加载与更新：`promptApi.getByKey(key, workflowType)`、`promptApi.update(...)`（Payload 类型 `PromptUpdatePayload`）。
  - 合并逻辑：前端将「预期 key」与库中 (key, workflow_type) 合并为统一列表，缺项以 placeholder 形式展示便于新建。

### 技术

- **筛选**：`workflowFilter` 为 `null`（全部）、`''`（默认）或流程类型 id；与 `getAll`、合并列表联动。
- **类型**：`PromptTemplate`、`PromptUpdatePayload`、`ListItem`（含 placeholder 分支），`itemId(item)` 使用 `key + \x00 + workflow_type` 作为稳定 id。
- **术语**：`useConcepts` 用于「流程类型」等展示用词。

---

## 7. 监控 (Workflow Monitor)

**路由**：`/workflow`  
**组件**：`web/src/pages/WorkflowMonitor.tsx`

### 介绍

- **用途**：工作流拓扑可视化与运行时观测。左侧为大块 React Flow 拓扑图（开始 → 架构师 → 写作 → 审核 → 决策 → 批评家 → 决策 → 媒体等），可按流程类型切换；右侧为日志、流程类型切换、启动、队列清理、刷新等控制与状态。
- **面向用户**：运维与开发，用于观察 Controller 是否在线、各 agent 队列与任务状态，以及拓扑与执行顺序。

### 架构

- **在系统中的位置**：可观测性与控制前端。消费 `/monitor/resources` 等接口提供的 Controller 状态、队列长度、任务统计；拓扑与边的配置可与后端「流程类型」对应，支持按类型切换不同 DAG（如生成新章节、仅大纲、仅正文、仅审批、仅媒体）。
- **数据流**：
  - 监控数据：`useMonitorStats`（内部调用 monitor 相关 API，如 `/monitor/resources`）；`usePurgeQueue`、`usePurgeAllQueues` 用于队列清理。
  - 拓扑：节点与边由本地常量（如 `DEFAULT_EDGES_TEMPLATE`、`WORKFLOW_EDGES`）与 `workflowId` 决定；布局可持久化到 `localStorage`（key 前缀 `novel-agent-flow-layout-{workflowId}`），支持保存/恢复与重置。
  - 流程类型与启动：`WORKFLOW_OPTIONS`、`WORKFLOW_ID_*` 与启动逻辑、DispatchTerminal/ControllerLogicPanel 等组件配合。

### 技术

- **React Flow**：`@xyflow/react`，`AgentNode`、`StartNode`、`DecisionNode`，自定义边样式（普通/成功/修订）与标记；支持拖拽连线、编辑节点/边，并通过 `EditElementDialog` 修改显示文案或样式。
- **组件**：`DispatchTerminal`、`ControllerLogicPanel`、`AgentNode`/`StartNode`/`DecisionNode`、`EditElementDialog`（见 `components/monitor/`、`components/monitor/flow/`）。
- **Hooks**：`useMonitorStats`、`usePurgeQueue`、`usePurgeAllQueues`；类型 `AgentMetric` 等来自 `types`。

---

## 8. 帮助 (Help)

**路由**：`/help`  
**组件**：`web/src/pages/Help.tsx`

### 介绍

- **用途**：系统概念管理。列表展示 key / label / description / scope，支持对任意概念的 label、description 进行编辑并保存；用于全站术语统一（如「流程类型」「运行」等）。
- **面向用户**：配置管理员或希望统一界面用词的用户；修改后影响写作、审批、监控等依赖 `useConcepts` 的页面。

### 架构

- **在系统中的位置**：全站「概念」数据的管理界面。概念来自后端 `/api/help/concepts`，由 `helpApi.getConcepts`、`helpApi.updateConcept` 读写；前端通过 `useConcepts` 在各页解析 key → label/description，保证导航、按钮、说明等用语一致。
- **数据流**：只与 help API 交互；无小说、章节、工作流、检索等依赖。

### 技术

- **API**：`helpApi.getConcepts()`、`helpApi.updateConcept(key, { label, description })`；类型 `SystemConcept`。
- **状态**：`editingKey`、`editLabel`、`editDesc`；`updateMutation` 成功后失效 `['help', 'concepts']` 并退出编辑。
- **UI**：卡片列表 + 行内编辑（输入 label/description，保存/取消）；依赖 `Card`、`ScrollArea`、`Button` 等 UI 组件。

---

## 路由与 API 对照摘要

| 页面   | 路由       | 主要 API / 数据源 |
|--------|------------|-------------------|
| 首页   | `/`        | 无业务 API；`useConcepts` |
| 写作   | `/writer`  | novels/chapters、workflow、retrieval |
| 检索   | `/retrieval` | retrieval（listIndexed/addIndex/deleteIndex）、useNovels/useChapters |
| 审批   | `/approvals` | approvals（listWorkflowTypesWithPending、listWorkflowsWithPending、listPending、getDetail、approve、reject） |
| 阅读   | `/reader`  | novels/chapters、chaptersApi.get |
| Prompt | `/prompts` | prompt（getAll、getExpectedKeys、getByKey、update）、workflow.getTypes |
| 监控   | `/workflow` | monitor（resources 等）、purge 相关 |
| 帮助   | `/help`    | help（getConcepts、updateConcept） |

后端路由挂载见 `src/api/main.py`（workflow、monitor、novels、prompts、approvals、help、retrieval 等）；前端 API 封装见 `web/src/api/client.ts` 与 `web/src/api/services.ts`。
