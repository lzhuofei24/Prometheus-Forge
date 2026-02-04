# Prometheus Forge - 核心架构深度技术文档 (v4.0 Final)

## 1. 基础设施与中间件深度解析 

本系统架构核心在于解决 Python 异步生态与 CPU 密集型计算的冲突，以及分布式环境下的状态一致性。

### 1.1 存储层

- **Redis Cluster (核心状态存储)**
  - **作用**：LangGraph 的 Checkpointer 后端，实现应用层无状态化。
  - **键值设计**：
    - `checkpoint:{thread_id}`: **Hash** 结构。存储当前的 Graph State（节点快照、变量堆栈）。
    - `msg_buffer:{thread_id}`: **List** 结构。存储异步写入的中间消息（Stream Buffer）。
  - **关键技术**：
    - **Pipeline**: 在状态更新时，使用 `pipe = redis.pipeline()` 将 `HSET` (更新状态) 和 `RPUSH` (写入日志) 打包成原子操作，减少 **RTT (Round-Trip Time)**。
- **ChromaDB (语义记忆)**
  - **配置**：
    - **Distance Function**: Cosine Similarity (余弦相似度)。
    - **HNSW Config**: `M=16`, `ef_construction=200` (平衡构建速度与召回精度)。
- **Neo4j (图记忆 - 结构化内核)**
  - **作用**：提供硬逻辑约束与实体关系存储。
  - **数据结构**：Labeled Property Graph (属性图)。
  - **检索算法**：`Cypher Query` (1-Hop Subgraph) —— 提取实体的一阶邻居子图，防止上下文爆炸，为 LLM 提供结构化约束。

### 1.2 调度与执行层 

本系统采用 **“双轨编排（Dual-Track Orchestration）”** 与 **“统一执行层（Unified Execution Layer）”** 相结合的异构架构，旨在解决 Python 在高并发场景下的 GIL 瓶颈，并实现实时交互与离线治理的资源解耦。

#### A. 在线控制流 - LangGraph

- **定位**：**I/O 密集型 · 实时会话状态机**。
  - 负责处理用户的实时指令、意图路由及多轮对话的上下文维护。
- **运行机制**：
  - 运行在 **FastAPI** 主进程的 `asyncio` Event Loop 中，基于 WebSocket/HTTP 响应，确保高并发下的非阻塞 I/O。
- **状态管理 (Stateless Design)**：
  - 采用 **Checkpoint** 机制。每执行完一个 Step，自动将当前图状态（Graph State, 包含变量堆栈与消息历史）序列化并原子写入 **Redis Cluster**，实现应用层的完全无状态化。
- **调度策略 (Delegate Pattern)**：
  - **轻量级逻辑**（如 Prompt 组装、API 聚合）：在本地 Event Loop 中异步执行。
  - **重计算/重写入**：作为 **Producer**，将任务封装为 Payload 投递至 Celery，自身仅负责异步等待结果或直接返回（Fire-and-Forget），避免阻塞主线程心跳。

#### B. 离线控制流 - Controller

- **定位**：**I/O 密集型 · 后台批处理调度器**。
  - 负责系统的自我维护、数据闭环与长周期治理，与具体用户会话解耦。
- **运行机制**：
  - 独立的守护进程 (Daemon)，基于 **APScheduler** 或 **Cron** 时间触发。
- **核心场景**：
  - **记忆固化 (Memory Consolidation)**：每晚定时扫描活跃用户的 Short-term Memory，批量生成摘要并写入图数据库。
  - **索引重建 (Index Rebuilding)**：当 Embedding 模型版本更新时，触发全量数据的重新向量化。
- **调度策略**：
  - 实现 **Batch Fan-out (批量扇出)**。单次调度可一次性生成数千个子任务（Jobs）推入 Celery 队列，实现高吞吐处理。

#### C. 统一数据计算流 - Celery + Redis

- **定位**：**分布式算力底座**。
  - 作为统一的消费者 (Consumer)，同时承接来自 LangGraph (在线) 和 Controller (离线) 的任务，利用多进程模型绕过 Python GIL 限制。
- **资源隔离配置 (Queue Isolation)**：
  - **`compute_queue` (高优先级)**：
    - *任务*：Cross-Encoder Rerank, 实体抽取。
    - *配置*：**Prefork 模型**，并发数 = CPU 核数。专为 **CPU 密集型**任务设计，确保在线业务的低延迟。
  - **`io_queue` (默认/低优先级)**：
    - *任务*：Graph DB 写入, 日志审计, 记忆归档。
    - *配置*：**高并发模式** (如 concurrency=20+)。专为 **I/O 密集型**任务设计，利用等待时间处理更多吞吐。
- **关键配置**：
  - `worker_concurrency=4` (针对计算队列，避免上下文切换)。
  - `prefetch_multiplier=1` (开启 **Fair Dispatching**，防止长任务阻塞 Worker，实现负载均衡)。
- **调用协议**：
  - **Fire-and-Forget (即发即弃)**：用于日志/记忆写入。LangGraph 发送后立即返回，不等待 Celery 确认，将用户感知的 Latency 降至最低。
  - **Async Result (异步等待)**：用于 Rerank。LangGraph 发送后通过 `await asyncio.sleep` 轮询 Redis 结果，实现非阻塞的同步调用。

------

#### D. 架构组件对比

| **维度**           | **LangGraph (在线编排)**       | **Controller (离线调度)**      | **Celery (统一执行)**     |
| ------------------ | ------------------------------ | ------------------------------ | ------------------------- |
| **核心职责**       | **逻辑编排 (Reasoning)**       | **任务分发 (Dispatching)**     | **物理执行 (Execution)**  |
| **资源属性**       | **I/O 密集型** (API/Redis等待) | **I/O 密集型** (DB扫描/MQ发送) | **CPU / 重 I/O 密集型**   |
| **关注对象**       | 单个用户会话 (Session)         | 全局系统/批量数据 (Batch)      | 单个任务单元 (Task)       |
| **触发机制**       | **事件驱动** (WebSocket/HTTP)  | **时间驱动** (Cron) / 管理指令 | **队列驱动** (被上游调用) |
| **延迟敏感度**     | **高** (ms ~ s 级，用户在等)   | **低** (min ~ hour 级)         | **中** (取决于队列优先级) |
| **状态维护**       | 强状态 (Context, Memory)       | 无状态或仅维护游标             | 无状态 (Stateless)        |
| **与 Celery 关系** | **生产者** (按需下发)          | **生产者** (批量扇出)          | **消费者** (实际干活)     |

## 2. 核心 Agent 微服务详解

系统包含 5 个核心智能体，形成从意图识别、安全拦截、执行、校验到记忆存储的完整闭环。

### Agent A: Task Planner (任务规划器)

- **输入**: `User_Query` ("我要退货"), `Global_State` (User_Level: VIP)

- **Step 1: 意图分类 (Intent Classification)**

  - **Prompt**:

    Plaintext

    ```
    请将用户的查询归类为以下意图之一：[REFUND_REQUEST (退款请求), ORDER_STATUS (订单状态), PRODUCT_FAQ (产品咨询), CHITCHAT (闲聊)]。
    
    输入: "这耳机音质太差了，我不想要了"
    输出: REFUND_REQUEST
    ```

- **Step 2: DAG 生成 (DAG Compilation)**

  - **逻辑**: 根据意图加载对应的 SOP 模板。

  - **Prompt Strategy**: Few-Shot + Grammar Constraint (JSON)

  - **Prompt**:

    Plaintext

    ```
    你是一名工作流架构师 (Workflow Architect)。基于用户意图 'REFUND_REQUEST'，生成一个 JSON 格式的执行计划。
    
    可用工具 (Available Tools): [Tool_Check_Order, Tool_Check_Policy, Tool_Generate_Reply]。
    约束条件 (Constraint): 必须在检查政策之前先检查订单状态。
    
    输出示例:
    {
      "steps": [
        {"id": "s1", "tool": "Tool_Check_Order", "args": {"key": "status"}},
        {"id": "s2", "tool": "Tool_Check_Policy", "args": {"intent": "refund"}},
        {"id": "s3", "tool": "Tool_Generate_Reply"}
      ]
    }
    ```

  - **输出**: `Plan_Object` 传入 State。

#### 1. 通用场景

**适用范围**：系统入口，或者类似 Siri/ChatGPT 的通用助手模式，负责处理杂项或路由到垂直领域。

##### Step 1: 意图分类

Python

```
GENERAL_INTENT_PROMPT = """
### 角色
你是一个全能型 AI 助手的中控大脑。请分析用户输入，将其归类为以下核心意图之一。

### 意图定义
1. **DOMAIN_ROUTING** (领域路由): 用户通过自然语言请求特定的业务服务（如"我要退款"、"帮我选个礼物"）。
2. **INFO_QA** (通用问答): 询问事实性知识、天气、百科等（如"现在几点了"、"香蕉的热量"）。
3. **TASK_EXECUTION** (工具执行): 需要调用通用工具完成的任务（如"帮我定个闹钟"、"计算 1+1"）。
4. **CHITCHAT** (闲聊): 无明确目的的对话。

### 示例
Input: "这双鞋怎么退货？" -> Output: DOMAIN_ROUTING (Target: AfterSales)
Input: "推荐一款适合跑步的耳机" -> Output: DOMAIN_ROUTING (Target: Recommendation)
Input: "北京今天天气怎么样？" -> Output: TASK_EXECUTION
Input: "你真笨" -> Output: CHITCHAT

### 当前任务
Input: "{user_query}"
Output:
"""
```

##### Step 2: DAG 生成

Python

```
GENERAL_DAG_PROMPT = """
### 角色
你是一名任务调度员。基于用户意图，生成 JSON 执行计划。

### 可用工具
- Router_Dispatch(domain): 将任务转发给垂直领域的子 Agent (domain可选: 'after_sales', 'recommendation').
- Tool_Web_Search(query): 联网搜索信息。
- Tool_Calculator(expression): 数学计算。
- Tool_General_Chat(query): 调用通用 LLM 进行回复。

### 约束
1. 如果意图是 DOMAIN_ROUTING，必须使用 Router_Dispatch。
2. 如果是闲聊，直接使用 Tool_General_Chat。

### 输出示例
User: "我要投诉你们客服"
Output:
{{
  "steps": [
    {{ "id": "1", "tool": "Router_Dispatch", "args": {{ "domain": "after_sales" }} }}
  ]
}}

### 当前任务
User: "{user_query}"
Output:
"""
```

------

#### 2. 售后场景

**适用范围**：退款、物流查询、投诉。

**核心逻辑**：线性锁死，禁止跳步，逻辑严密。

##### Step 1: 意图分类

Python

```
AFTERSALES_INTENT_PROMPT = """
### 角色
你是一名资深电商售后判责专家。请精准识别用户意图。

### 意图定义
1. **REFUND_REQUEST** (退款申请): 明确要求退货退款，包含质量问题、不喜欢等理由。
2. **LOGISTICS_QUERY** (物流查询): 询问发货时间、包裹位置、催发货。
3. **POLICY_CONSULT** (政策咨询): 询问保修期、价保规则等，未明确表示要退款。
4. **COMPLAINT** (投诉反馈): 对服务或体验表达强烈不满，情绪激动。

### 状态感知
用户等级: {user_level} (若为 VIP，COMPLAINT 的优先级提升)

### 当前任务
Input: "{user_query}"
Output:
"""
```

##### Step 2: DAG 生成 (SOP 严格模式)

Python

```
AFTERSALES_DAG_PROMPT = """
### 角色
你是一名严格遵守 SOP 的售后流程架构师。

### 可用工具
- Tool_Check_Order(order_id): [必选] 查询订单状态、发货时间、收货时间。
- Tool_Check_Policy(intent, sku_category): [必选] 查询该商品类目的售后规则（如：已激活电子产品不可退）。
- Tool_Check_Logistics(order_id): 查询物流轨迹。
- Tool_Calc_Refund_Amount(order_id): 计算可退金额（扣除优惠券）。
- Tool_Generate_Reply(tone): 生成最终回复。

### 业务约束 (Hard Constraints)
1. **铁律**：处理 'REFUND_REQUEST' 时，必须**先**调用 `Tool_Check_Order` 确认订单存在且状态正确，**再**调用 `Tool_Check_Policy` 判断资格。严禁直接生成回复。
2. 如果是 VIP 用户，Tone (语调) 参数应设为 'apologetic_priority'。

### 输出示例
User: "这手机发热严重，我要退货" (User: VIP)
Output:
{{
  "steps": [
    {{ "id": "s1", "tool": "Tool_Check_Order", "args": {{ "key": "latest" }} }},
    {{ "id": "s2", "tool": "Tool_Check_Policy", "args": {{ "issue": "quality_defect" }}, "dependency": "s1" }},
    {{ "id": "s3", "tool": "Tool_Generate_Reply", "args": {{ "tone": "apologetic_priority" }}, "dependency": "s2" }}
  ]
}}

### 当前任务
User_Intent: {intent}
User_Level: {user_level}
Output:
"""
```

------

#### 3. 推荐场景

**适用范围**：导购、选品、比价。

**核心逻辑**：动态决策，模糊需求先反问（Ask），明确需求去召回（Recall）。

##### Step 1: 意图分类

Python

```python
REC_INTENT_PROMPT = """
### 角色
你是一名能够洞察用户潜在需求的金牌导购。

### 意图定义
1. **FUZZY_NEED** (模糊需求): 用户有购买意向但无具体参数（如"想买个礼物送女朋友"、"推荐个手机"）。
2. **SPECIFIC_SEARCH** (精准搜索): 用户有明确参数（如"耐克白色板鞋 42码"、"2000元以内的降噪耳机"）。
3. **COMPARISON** (商品比价): 用户在纠结两个或多个具体商品（如"iPhone 15 和 15 Pro 买哪个"）。
4. **FEEDBACK_ADJUST** (反馈调整): 用户对上一轮推荐不满意，提出修改意见（如"太贵了"、"换个颜色"）。

### 当前任务
Input: "{user_query}"
Output:
"""
```

##### Step 2: DAG 生成 (探索模式)

Python

```python
REC_DAG_PROMPT = """
### 角色
你是一名擅长引导式销售的导购策划师。

### 可用工具
- Tool_Ask_Clarification(question): [反问] 当需求模糊时，向用户提问以明确需求（预算/场景/偏好）。
- Tool_Search_Recall(keywords, filters): [召回] 从商品库检索候选集。
- Tool_Get_User_Profile(user_id): [画像] 获取用户历史偏好（品牌/价格敏感度）。
- Tool_Compare_Items(item_ids): [对比] 对比商品参数。
- Tool_Generate_Pitch(strategy): [推销] 生成带有卖点的推荐语。

### 策略约束 (Soft Strategy)
1. **冷启动策略**：如果意图是 'FUZZY_NEED' 且用户画像为空，**必须**先调用 `Tool_Ask_Clarification`，不要盲目推荐。
2. **个性化策略**：如果意图是 'SPECIFIC_SEARCH'，先调用 `Tool_Get_User_Profile`，再调用 `Tool_Search_Recall`，以便后续 Rerank 使用。
3. **纠偏策略**：如果意图是 'FEEDBACK_ADJUST'，根据用户反馈修改 `Tool_Search_Recall` 的 filters 参数。

### 输出示例
User: "想买个游戏本" (Intent: FUZZY_NEED)
Output:
{{
  "steps": [
    {{ "id": "s1", "tool": "Tool_Get_User_Profile", "args": {{ "key": "gaming_preference" }} }},
    {{ "id": "s2", "tool": "Tool_Ask_Clarification", "args": {{ "question": "主要玩什么游戏？预算大概多少？" }}, "dependency": "s1" }}
  ]
}}

User: "我要买 Switch 游戏机" (Intent: SPECIFIC_SEARCH)
Output:
{{
  "steps": [
    {{ "id": "s1", "tool": "Tool_Get_User_Profile", "args": {{ "key": "all" }} }},
    {{ "id": "s2", "tool": "Tool_Search_Recall", "args": {{ "keyword": "Nintendo Switch", "category": "console" }} }},
    {{ "id": "s3", "tool": "Tool_Generate_Pitch", "args": {{ "strategy": "highlight_games" }}, "dependency": "s2" }}
  ]
}}

### 当前任务
User_Intent: {intent}
Output:
"""
```

这是一个非常完善且工业级的风控架构。

引入 **“敏感词库 (Trie/DFA)”** 处理固定词汇，保留 **“Regex”** 处理模式特征，最后用 **“LLM”** 处理语义和场景差异。这形成了 **L1 (毫秒级/低成本) -> L2 (秒级/高智能)** 的漏斗式过滤，是目前大厂最标准的做法。

以下是更新后的 **Agent B** 描述，你可以直接替换原文档中的对应部分。

------

### Agent B: Compliance Guard (合规风控网关) 

- **定位**: 双向安全防火墙 (Bi-directional Firewall)。采用 **“漏斗式 (Funnel)”** 过滤机制，平衡性能与准确率。
- **输入**: `User_Input` (进站) 或 `Executor_Response` (出站)。

#### Step 1: L1 确定性拦截

- **机制**: **AC 自动机 (敏感词库)** + **Regex (正则引擎)** 并行扫描。毫秒级阻断，不消耗 LLM Token。
- **分工**:
  - **敏感词库 : 拦截 **固定违规词**。
    - *覆盖*: 脏话 (Profanity)、涉政敏感词、竞品名称（如在推荐场景拦截“拼多多”）、黑产黑话。
  - **正则引擎 : 拦截 **结构化风险**。
    - *覆盖*: PII 隐私信息 (手机号 `1[3-9]\d{9}`、身份证)、Prompt 注入攻击特征 (`Ignore previous...`)、SQL 注入特征。

#### Step 2: L2 语义审计 —— *场景化适配*

- **机制**: 调用轻量级 LLM (或专门的 Safety Model) 进行语义判断。
- **策略**: **Policy Injection (策略注入)**。根据当前的 `Config.scenario` 动态加载不同的 System Prompt 侧重点。

**通用 Prompt 模板 (Dynamic Template):**

Python

```
PROMPT_TEMPLATE = """
角色: 你是 {scenario} 场景下的内容安全审核员。
任务: 判断文本是否违反以下特定安全红线。

### 场景红线 (Scenario Red Lines):
{safety_policy}

### 基础红线 (Base Red Lines):
1. 辱骂、仇恨言论、色情暴力。
2. 诱导诈骗（如索要密码）。

### 当前输入: "{text}"
输出: [SAFE] 或 [UNSAFE]
"""
```

**场景 A: 售后场景配置 (After-Sales Mode)**

- **注入策略 (`{safety_policy}`)**:

  > "1. 严禁 AI 承诺未授权的资金赔偿。\n2. 严禁索要用户支付密码或 CVV 码。\n3. 允许用户发送手机号/订单号进行身份验证（Override L1 Regex）。"

**场景 B: 推荐场景配置 (Recommendation Mode)**

- **注入策略 (`{safety_policy}`)**:

  > "1. 严禁虚假宣传 (Over-claiming)，商品功能必须基于事实。\n2. 严禁违反广告法（如使用'国家级'、'第一'等极限词）。\n3. 严禁拉踩竞争对手品牌。"

#### Step 3: 决策与反馈 

- **Block**: 拦截并返回预设话术（如 *"很抱歉，您的请求包含敏感内容，无法处理"*）。
- **Pass**: 放行至 Executor 或用户端。

### Agent C: Context-Aware Executor (RAG 核心执行器)

- **定位**: 系统的“大脑皮层”。负责执行检索增强生成 (RAG)，将外部知识转化为最终回复。
- **架构特性**: 采用 **策略注入 (Policy Injection)** 模式。代码逻辑通用（Rewrite -> Retrieve -> Rerank -> Generate），但**检索源**、**排序权重**和**生成指令**随场景配置动态切换。

#### 核心流水线

##### **Step 1: 查询重写 (Query Rewrite)**

- **目的**: 消除指代歧义，生成独立语义查询。

- **Prompt**:

  > "将用户的查询重写为包含完整上下文的独立句子。例如将 '能退吗？' 重写为 '我能退货这款已拆封的 iPhone 15 Pro 吗？'"

##### **Step 2: 混合检索 (Hybrid Retrieval)**

- **机制**: 并行执行 **Vector Search** (非结构化文档) + **Graph Search** (结构化实体)。
- **动态配置**: 根据 `Config.scenario` 决定检索哪个 Database 和 Sub-graph。

##### **Step 3: Cross-Encoder 重排序 (Rerank)**

- **模型**: `BAAI/bge-reranker-v2-m3`。
- **机制**: 对 `(Query, Doc)` 拼接打分，输出相关性 Logits。
- **作用**: 语义消歧与质量把控。

##### **Step 4: 生成 (Generation)**

- **机制**: 将检索结果注入 System Prompt 的 `{context}` 槽位。

#### **场景 A: 通用/路由场景**

- **目标**: 准确回答百科类问题或进行意图路由。

- **检索策略**:

  - *Vector*: 检索全站 FAQ、帮助中心文档。
  - *Graph*: 不启用或仅检索基础元数据。

- **Rerank 策略**: 标准相关性排序，阈值 `Score > 0.5`。

- **生成 Prompt**:

  Plaintext

  ```
  系统指令: 你是一个乐于助人的 AI 助手。请基于上下文回答用户问题。如果信息不足，请诚实地回答“我不知道”。
  ```

#### **场景 B: 售后场景 **

- **目标**: **高一致性 (Consistency)**。严格执行政策，零幻觉。

- **检索策略**:

  - *Graph (P0)*: 必须锚定 `Order_ID`，检索 **User-Order-Policy** 子图（如：订单状态、剩余保修天数）。
  - *Vector (P1)*: 检索具体的售后条款文本。

- **Rerank 策略**: **逻辑冲突过滤**。

  - 如果 Graph 显示 `Status=Shipped`，则 Cross-Encoder 会自动压低“未发货退款流程”文档的得分。

- **生成 Prompt**:

  Plaintext

  ```
  系统指令: 你是一名专业的售后判责专员。
  语气要求: **专业、客观、坚定 (Firm)**。
  约束: 
  1. 严格 (STRICTLY) 基于【事实】和【政策】回答。
  2. 严禁做出未授权的承诺（如“肯定能退”）。
  3. 如果用户不符合退款条件，请礼貌拒绝并解释条款原因。
  ```

#### **场景 C: 推荐场景**

- **目标**: **高探索性 (Exploration)**。激发购买欲，匹配个性化偏好。

- **检索策略**:

  - *Vector*: 检索商品描述 (Description)、用户评论 (Review)。
  - *Graph*: 检索 **User-Interest-Item** 子图（如：用户偏好品牌、历史点击类目）。

- **Rerank 策略**: **个性化加权 (Personalization Boost)**。

  - 修改打分公式: `Final_Score = Semantic_Score * 0.7 + User_Interest_Match * 0.3`。
  - *解释*: 既要语义相关，又要符合用户口味（如用户喜欢“红色”，则红色商品加分）。

- **生成 Prompt**:

  Plaintext

  ```python
  系统指令: 你是一名热情且有品位的金牌导购。
  语气要求: **热情 (Enthusiastic)、有说服力 (Persuasive)**。
  约束:
  1. 重点突出商品中与【用户画像】（如预算、风格）相匹配的卖点 (Selling Points)。
  2. 使用“为您精选”、“性价比极高”等引导性词汇。
  3. 不要堆砌参数，要构建使用场景。
  ```

这是重构后的 **Agent D** 描述。

为了体现架构的灵活性，我将 **Consistency Auditor** 定义为系统的 **“质量保证官 (QA)”**，并引入了 **“校验策略模式 (Validation Strategy Pattern)”**。它不再仅仅是简单的代码比对，而是根据场景在 **确定性校验 (Deterministic)** 和 **语义校验 (Semantic)** 之间切换。

------

### Agent D: Consistency Auditor (逻辑验证器)

- **定位**: AI 回复的 **“单元测试 (Unit Test)”** 模块。
- **架构特性**: 实现了 **Test-Driven Generation (测试驱动生成)**。它独立于生成器（Executor），利用 Graph Memory 中的“硬事实 (Ground Truth)”对生成的回复进行**事后审计**。

#### 1. 核心流水线

**Step 1: 事实主张抽取 (Claim Extraction)**

- **目的**: 将非结构化的自然语言回复转化为结构化的可验证数据点。

- **Prompt**:

  > "请从 AI 的回复中提取关键事实主张 (Key Claims)，输出为 JSON 格式。包括：动作 (Action)、金额 (Amount)、承诺 (Promise)、商品参数 (Specs)。"

**Step 2: 差异化校验 (Differentiated Verification)**

- **机制**: **混合校验引擎**。
  - **Rule Engine**: Python 代码执行硬逻辑比对（比大小、比日期）。
  - **NLI Model**: 语义蕴含模型判断逻辑冲突（矛盾/中立/蕴含）。
- **动态配置**: 根据 `Config.scenario` 加载不同的校验规则集。

**Step 3: 决策与反馈 (Decision & Feedback)**

- **Pass**: 放行输出。
- **Fail**: 触发 **Self-Correction (自愈)** 机制。将错误原因（Feedback）回传给 Executor，要求重试。

------

#### 2. 场景化策略配置

##### **场景 A: 售后场景 **

- **目标**: **零容错 (Zero Tolerance)**。绝对的逻辑正确与合规。

- **校验策略**: **Rule-Based (强规则基)**。

- **核心逻辑**:

  1. **状态一致性**: 提取的 `Action` 必须与 Graph 中的 `Order_Status` 兼容。（如：状态是 `Shipped`，则 `Cancel_Order` 必须报错）。
  2. **数值准确性**: 提取的 `Refund_Amount` 必须 `<=` 订单实付金额。
  3. **时效性**: `Current_Date` - `Receive_Date` 必须 `<=` 政策限制天数。

- **Prompt (Extraction)**:

  ```python
  任务: 提取售后承诺。
  输入: "您可以退货，退款金额 200 元。"
  输出: {"action": "return_goods", "amount": 200.0, "currency": "CNY"}
  ```

- **校验逻辑 (Python 伪代码)**:

  ```python
  if claim['action'] == 'return_goods' and order['status'] == 'ACTIVATED':
      raise LogicError("已激活商品不可退货")
  if claim['amount'] > order['payment_amount']:
      raise LogicError("退款金额超出实付")
  ```

##### **场景 B: 推荐场景**

- **目标**: **事实准确 (Factually Correct)**。防止参数造假，但允许营销修饰。

- **校验策略**: **Fact-Check (事实核查)**。

- **核心逻辑**:

  1. **库存/价格核查**: 推荐的商品 ID 必须在 Graph 中存在，且 `Stock > 0`，价格与当前数据库一致。
  2. **属性反幻觉**: AI 描述的卖点（如“防水”）必须在商品属性表里为 `True`。
  3. **风格一致性**: 检查回复语调是否足够热情（语义打分），但这属于软约束。

- **Prompt (Extraction)**:

  ```python
  任务: 提取商品参数描述。
  输入: "这款耳机支持主动降噪，续航 50 小时。"
  输出: {"sku_features": ["ANC", "battery_50h"]}
  ```

- **校验逻辑 (Python 伪代码)**:

  ```Python
  real_features = graph_db.get_features(sku_id)
  for feature in claim['sku_features']:
      if feature not in real_features:
          raise HallucinationError(f"商品不具备 {feature} 功能")
  ```

##### **场景 C: 通用场景**

- **目标**: **常识一致性 (Common Sense)**。

- **校验策略**: **NLI (自然语言推理)**。

- **核心逻辑**:

  - 检查 AI 回复是否自相矛盾（如前一句说“不知道”，后一句开始瞎编）。
  - 检查是否违背基本常识（如“香蕉是蓝色的”）。

- **Prompt (Verification)**:

  ```
  任务: 判断以下回复是否自相矛盾或违背常识。
  上下文: 用户问天气。
  回复: "现在是晚上，太阳很大。"
  输出: [CONFLICT]
  ```

------

#### 3. 决策流程图解

1. **Auditor 介入**:
   - 如果是 **售后**: 跑 Python 脚本比对金额和日期。 -> **发现错误**: "退款金额 200 > 实付 199"。
   - 如果是 **推荐**: 跑数据库查询比对库存。 -> **发现错误**: "推荐商品 ID 101 无货"。
2. **反馈回路 (Feedback Loop)**:
   - Auditor 将 `"Error: 退款超额"` 注入 Prompt。
   - LangGraph 路由回 Agent C (Executor)。
   - Executor 收到报错，重新生成："抱歉，刚看错了，最高只能退 199 元。"

### Agent E: Knowledge Manager (异步记忆固化引擎)

- **定位**: 系统的 **“海马体”**。负责异步 ETL 任务，将非结构化的对话日志转化为结构化的图谱节点和向量索引，实现“越用越懂你”。
- **架构特性**: **完全异步 (Fully Async)**。运行在 **Celery Worker** 中，通过 Fire-and-Forget 模式触发，确保记忆写入过程 **零延迟 (Zero-Latency)** 影响用户体验。

#### 1. 核心流水线 

**Step 1: 增量信息抽取 (Incremental Information Extraction)**

- **机制**: 监听对话结束事件，读取 Redis 中的 Session History。
- **Prompt**: 调用 LLM 从对话中提取 **Entity (实体)**, **Relation (关系)**, **Attribute (属性)**。

**Step 2: 实体链接与归一化 (Entity Linking & Normalization)**

- **目的**: 防止图谱分裂。
- **逻辑**: 将用户口语（"大钩子鞋"）映射为标准 SKU 实体（"Nike"）。如果实体不存在，则创建新节点。

**Step 3: 双路存储 (Dual-Write Storage)**

- **Graph DB**: `MERGE` 操作更新实体属性（用于逻辑检索）。
- **Vector DB**: 将本次对话摘要 `Upsert` 到向量库（用于语义检索）。

------

#### 2. 场景化策略配置 

##### **场景 A: 推荐场景 **

- **目标**: **构建动态画像 (Dynamic Profiling)**。捕捉用户的审美、预算和品牌偏好。

- **抽取重点**:

  - **显性偏好**: "我喜欢红色" -> `(User)-[:LIKES]->(Color:Red)`
  - **隐性特征**: 用户拒绝了 5000 元的商品 -> `(User)-[:HAS_TAG]->(Price_Sensitive)`
  - **负反馈**: "不要发邮政" -> `(User)-[:DISLIKES]->(Logistics:EMS)`

- **Prompt 模板**:

  Plaintext

  ```
  任务: 从对话中分析用户画像 (User Profile)。
  输入: "这件始祖鸟太贵了，只要透气好就行，牌子无所谓。"
  输出 JSON:
  {
    "budget_sensitivity": "High",
    "brand_loyalty": "Low",
    "functional_needs": ["Breathable"],
    "rejected_brands": ["Arc'teryx"]
  }
  ```

- **写入逻辑 (Cypher)**:

  Cypher

  ```
  MATCH (u:User {id: $uid})
  MERGE (t:Tag {name: "Price_Sensitive"})
  MERGE (u)-[:HAS_TAG]->(t)
  ```

##### **场景 B: 售后场景 **

- **目标**: **纠纷证据留存 (Dispute Evidence)**。记录争议焦点、用户情绪变化、协商结果。

- **抽取重点**:

  - **事实断言**: "屏幕裂了" -> `(Order)-[:HAS_ISSUE]->(Screen_Damage)`
  - **情绪曲线**: "开始很愤怒 -> 后来满意" -> 用于服务质量分析。
  - **承诺记录**: "客服承诺赔偿 50 元" -> 存入 Graph 防止后续赖账。

- **Prompt 模板**:

  Plaintext

  ```
  任务: 提取售后关键事实 (Key Facts) 与 最终协商结果 (Resolution)。
  输入: "虽然你们发货慢，但看在退了运费的份上，我就不投诉了。"
  输出 JSON:
  {
    "issue_type": "Logistics_Delay",
    "resolution": "Refund_Shipping_Fee",
    "customer_satisfaction": "Neutral",
    "complaint_status": "Withdrawn"
  }
  ```

- **写入逻辑 (Cypher)**:

  Cypher

  ```
  MATCH (o:Order {id: $oid})
  CREATE (e:Event {type: "Dispute_Resolution", time: timestamp()})
  CREATE (o)-[:HAS_EVENT]->(e)
  ```

##### **场景 C: 通用场景 **

- **目标**: **基础信息补全 (Basic Info)**。

- **抽取重点**: 用户的昵称、地理位置、常用语言。

- **Prompt**:

  > "提取用户的基本属性：姓名、所在地、语言偏好。"

## 3. 场景化适配：Config 与 Prompt 差异 (Pluggable)

通过加载不同的 `Config.yaml`，系统内核不变，行为模式改变。

### 场景一：电商售后争议裁决 

- **Config**: `mode: strict_consistency`

- **Task Planner**: 锁定为线性 DAG。禁止跳过“验单”步骤。

- **Executor**:

  - **Prompt**: 注入 Tone 指令：

    > "语调要求：专业且富有同理心 (Empathetic)，但在执行政策时需保持坚定 (Firm)。"

- **Auditor**:

  - **类型**: Rule-Based (规则基)。
  - **逻辑**: 硬编码业务规则。例如 `if refund_amount > order_amount: raise Error` (防止赔付超额)。

### 场景二：个性化商品推荐 

- **Config**: `mode: exploration`

- **Task Planner**: 动态 DAG。允许循环推荐。

- **Executor**:

  - **Rerank**: 修改公式 `Final_Score = Semantic * 0.7 + User_Interest * 0.3`。

  - **Prompt**: 注入 Sales 指令：

    > "重点突出那些与用户提取的偏好 (Preferences) 相匹配的商品卖点。"

- **Auditor**:

  - **类型**: Quality-Check (质量检查)。
  - **逻辑**: 检查幻觉（如捏造功能）。允许适当的营销修饰。



这是为您构建的 **第 4 模块：工作流编排与执行机制**。

这一部分是系统“动起来”的样子。它详细描述了 **LangGraph 如何定义状态机**，以及 **Controller 如何切入离线任务**，并给出了三个场景下的具体流转时序。

------

## 4. 工作流编排与执行机制

本模块定义了系统的**动态行为**。基于 **LangGraph** 的状态机机制管理在线会话流转，配合 **Controller** 管理离线任务触发，实现从用户指令到最终交付的端到端执行。

### 4.1 全局状态定义 

在 LangGraph 中，所有 Agent 共享同一个状态对象（State），数据在节点间无缝流转。

```python
class AgentState(TypedDict):
    # 基础信息
    session_id: str
    user_id: str
    user_level: str  # e.g., "VIP", "NORMAL"
    
    # 消息堆栈
    messages: List[BaseMessage]  # 完整的对话历史
    
    # 工作流控制
    intent: str  # Planner 识别的意图
    dag_plan: Dict  # Planner 生成的 JSON 执行计划
    current_step_index: int  # 当前执行到 DAG 的哪一步
    
    # 执行中间态
    executor_draft: str  # Executor 生成的草稿回复
    auditor_feedback: str  # Auditor 的驳回意见 (如有)
    
    # 扩展槽位 (用于 Celery 异步任务)
    async_task_ids: List[str]  # 记录发往 Celery 的 Task ID
```

------

### 4.2 核心拓扑结构 

系统采用 **“带自愈环的线性主干 (Linear Backbone with Self-Correction Loop)”** 拓扑结构。

**节点流转逻辑 (Node Transitions):**

1. **START** -> `Node_Compliance_In` (进站风控)
2. `Node_Compliance_In` -> `Node_Planner` (意图与规划)
3. `Node_Planner` -> `Node_Executor` (执行与生成)
4. `Node_Executor` -> `Node_Auditor` (逻辑校验)
5. `Node_Auditor` --(Pass)--> `Node_Compliance_Out` (出站风控)
6. `Node_Auditor` --(Fail)--> `Node_Executor` (**回环重试**: 携带 Feedback 让 Executor 重写)
7. `Node_Compliance_Out` -> **END** (返回用户)
   - *并行分支*: 在到达 END 时，触发 `Node_Knowledge_Manager` (异步 Celery 任务)。

------

### 4.3 场景化工作流详解

#### 场景 A: 通用场景 (General / Routing)

- **特征**: 短链路，侧重于快速分发或简单问答。

1. **User Input**: "北京天气怎么样？"
2. **Compliance (In)**: [Pass] 无敏感词。
3. **Planner**:
   - Intent: `TASK_EXECUTION`
   - DAG: `[Tool_Web_Search(query="Beijing Weather")]`
4. **Executor**:
   - 调用 `Tool_Web_Search` 获取数据。
   - 生成回复: "北京今天晴，气温 25度..."
5. **Auditor**:
   - 策略: **NLI (常识校验)**。
   - 检查: 回复无自相矛盾。 -> [Pass]
6. **Knowledge Manager**: (跳过，无长期记忆价值)

#### 场景 B: 售后场景 (After-Sales / Strict Mode)

- **特征**: **强顺序依赖 (Sequential Dependency)**，包含 Celery 重计算。

1. **User Input**: "我买的耳机坏了，要退款。"
2. **Planner**:
   - Intent: `REFUND_REQUEST`
   - DAG: `[Step1: Check_Order, Step2: Check_Policy, Step3: Generate_Reply]`
3. **Executor (Loop)**:
   - *Step 1*: 调用本地 Tool 查订单状态 (Redis)。 -> "Status: Delivered"
   - *Step 2*: **Call Celery (Rerank)**。因为政策文档多，需异步重排序。
     - LangGraph 挂起 (`await asyncio.sleep`)，轮询 Redis 等待 Rerank 结果。
     - Celery Worker 返回: "Top1 Policy: 电子产品损坏可退。"
   - *Step 3*: 生成草稿 "可以退款，请寄回..."
4. **Auditor**:
   - 策略: **Rule-Based (规则基)**。
   - 抽取: `Action=Refund`。
   - 校验: `Order_Status=Delivered` 且 `Policy=Allow`。 -> [Pass]
5. **Knowledge Manager**:
   - **Fire-and-Forget**: 向 Celery 发送 `task_extract_dispute`，记录售后纠纷。

#### 场景 C: 推荐场景 

- **特征**: **多轮交互 (Multi-turn)**，Auditor 负责反事实检查。

1. **User Input**: "推荐个 500 元的跑鞋。"
2. **Planner**:
   - Intent: `SPECIFIC_SEARCH`
   - DAG: `[Step1: Get_Profile, Step2: Search_Recall, Step3: Generate_Pitch]`
3. **Executor**:
   - *Step 1*: 读取 Graph (User 喜欢 "Nike", 厌恶 "红色")。
   - *Step 2*: 召回商品。
   - *Step 3*: 生成推荐语 "这款 Nike Pegasus 是蓝色的，刚好 499 元..."
4. **Auditor**:
   - 策略: **Fact-Check (事实核查)**。
   - 发现异常: 推荐语说 "499元"，但数据库最新价格是 "599元"。
   - **Action**: 抛出 `Feedback("Price Mismatch: DB says 599")`，路由回 Executor。
5. **Executor (Retry)**:
   - 修正回复: "抱歉，价格刚更新为 599 元，稍微超了预算，但性能很棒..."
6. **Knowledge Manager**:
   - **Fire-and-Forget**: 向 Celery 发送 `task_update_profile`，记录用户对价格敏感。

------

### 4.4 命令执行与控制器集成

这里定义了 **LangGraph (在线)** 与 **Controller (离线)** 如何协同工作。

#### 1. 在线命令调用 (LangGraph -> Tool/Celery)

在 LangGraph Node 内部，根据任务类型选择调用方式：

- **Type I: 同步原子工具 (Sync Atomic Tools)**

  - *例子*: 正则匹配、简单的 SQL 查询、Prompt 组装。
  - *方式*: 直接在 `async def node_function()` 中执行。
  - *耗时*: < 50ms。

- **Type II: 异步 I/O 工具 (Async I/O Tools)**

  - *例子*: 请求 OpenAI API、查询 ChromaDB。
  - *方式*: `await async_client.query(...)`。
  - *耗时*: 100ms ~ 3s (不阻塞 Event Loop)。

- **Type III: 重计算/副作用任务 (Offloaded Tasks)**

  - *例子*: Cross-Encoder Rerank、写入 Neo4j。
  - *方式*: **Celery Signature**。

  Python

  ```
  # Node_Executor 代码片段
  from celery_app import task_rerank, task_write_graph
  
  # 场景 1: 需要结果 (Blocking wait)
  result = task_rerank.apply_async(args=[query, docs], queue='compute_queue')
  while not result.ready():
      await asyncio.sleep(0.1)  # 释放控制权给 Event Loop
  rerank_score = result.get()
  
  # 场景 2: 不需结果 (Fire-and-Forget)
  task_write_graph.apply_async(args=[entities], queue='io_queue')
  # 直接 return，进入下一个 Node
  ```

#### 2. 离线命令调度 (Controller -> Celery)

**Controller** 是一个独立运行的 Cron 进程，不经过 LangGraph，直接操作 Celery。

- **工作流示例：每日记忆固化**

  1. **Trigger**: `02:00 AM` (APScheduler)。

  2. **Scan**: Controller 从 Redis 扫描 `active_users_last_24h`。

  3. **Fan-out**:

     Python

     ```
     # Controller 代码片段
     for user_id in user_list:
         # 批量推送到 io_queue，不占在线计算资源
         celery_app.send_task(
             'tasks.consolidate_memory',
             args=[user_id],
             queue='io_queue'
         )
     ```

  4. **Execute**: Celery Worker (IO Queue) 慢慢消化这些任务，更新 Graph。

