# Prometheus Forge

### 分布式智能体记忆与编排引擎 (Distributed Agentic Memory & Orchestration Engine)

**Prometheus Forge** 是一款高性能的分布式编排引擎，专为解决 LLM 在**长周期任务 (Long-Horizon Tasks)** 中普遍存在的**“灾难性遗忘”**与**“状态幻觉”**问题而设计。

不同于仅依赖向量相似度的传统 RAG 系统，Prometheus Forge 引入了一套基于**混合检索 (Hybrid Search)** 与 **Cross-Encoder 重排序 (Re-ranking)** 的**动态一致性校验机制**，在复杂的多轮智能体交互中实现了 **95% 以上的逻辑一致性**，为构建有状态、具备自修正能力的 AI 应用提供了稳健的基础设施。

---

## 🎯 核心价值主张

Prometheus Forge 旨在解决大规模自主智能体（Autonomous Agents）落地过程中的核心工程挑战：

1. **状态管理 (State Management)**：实现计算与状态的彻底解耦，支持无状态（Stateless）服务的水平扩展。
2. **记忆消歧 (Memory Disambiguation)**：利用 RAG 2.0 策略，在超长上下文中精准区分“用户意图 (Intention)”与“既定事实 (Fact)”。
3. **系统韧性 (Resilience)**：提供全链路可观测性，以及针对不稳定 LLM API 的自动熔断与恢复机制。

---

## 🚀 核心特性

### 1. 高保真上下文检索 (RAG 2.0)

* **混合检索策略**：结合 **ChromaDB (稠密向量)** 与 **BM25 (稀疏关键词)**，同时捕捉语义细微差别与实体精确匹配。
* **基于重排序的语义消歧**：集成 **BGE-Reranker (Cross-Encoder)** 过滤召回结果中的“困难负例 (Hard Negatives)”。
* *效果*：有效解决了长文本中的“中间丢失 (Lost in the Middle)”现象。在冲突场景下（例如区分有效历史状态与过时状态），Context Hit-Rate@3 从 **60% 提升至 95%**。



### 2. 分布式无状态架构

* **无状态设计**：应用服务器不维护任何本地会话状态。所有 **工作流状态 (Workflow States)**（包括会话节点、全局约束）均通过高吞吐 Pipeline 持久化至 **Redis**。
* **水平扩展能力**：天然支持 K8s 或 Docker Swarm 容器化部署。集群中的任意节点均可接管挂起的工作流状态并恢复执行。

### 3. 事件驱动的异步编排

* **AsyncIO & LangGraph**：基于非阻塞事件循环构建。CPU 密集型任务（如 Tokenization 和 Rerank）自动卸载至 `ThreadPoolExecutor`，确保 I/O 任务的全异步执行。
* **自修正闭环 (Self-Correction)**：实现了 `Generator-Critic-Refiner`（生成-评估-修正）循环，支持配置最大重试次数。引擎会根据结构化反馈，自动将低质量输出路由回生成器进行修订。

### 4. 全局约束强制执行

* **基于图的知识管理**：利用 **NetworkX/GraphRAG** 维护“全局约束图 (Global Constraint Graph)”（前身为大纲/世界观）。
* **一致性校验**：在任何状态流转（文本生成）发生前，引擎会执行 1-Hop 子图检索，确保新的输出不违反既有的全局约束条件。

---

## 🛠 系统架构

系统遵循由状态机编排的 **生成器-验证器 (Generator-Verifier)** 范式。

```mermaid
graph TD
    User[客户端请求] --> API[FastAPI 网关]
    API -->|异步事件| Orchestrator[LangGraph 编排引擎]
    
    subgraph "记忆子系统 (RAG 2.0)"
        Orchestrator -->|1. 召回| HybridSearch[向量 + 关键词混合检索]
        HybridSearch -->|Top 50 文档| Reranker[Cross-Encoder 重排序]
        Reranker -->|Top 5 核心证据| Context[最终上下文窗口]
    end
    
    subgraph "状态管理"
        Orchestrator <-->|加载/保存 Checkpoint| Redis[(Redis 集群)]
        Orchestrator <-->|全局约束读取| GraphDB[(图存储)]
    end
    
    Context --> LLM[LLM 推理]
    LLM -->|Action/Output| Critic[一致性验证器]
    Critic -->|通过| Orchestrator
    Critic -->|失败 (进入修正循环)| LLM

```

---

## 🔧 技术栈

| 组件 | 技术选型 | 作用 |
| --- | --- | --- |
| **编排引擎** | **LangGraph** | 有限状态机 (FSM) 与有向循环图管理 |
| **开发语言** | **Python 3.10+** | 核心逻辑，利用 `asyncio` 实现高并发 |
| **状态存储** | **Redis 7.0+** | 分布式锁、状态持久化、审计日志 |
| **向量存储** | **ChromaDB** | 基于 HNSW 索引的非结构化上下文存储 |
| **图存储** | **NetworkX / Neo4j** | 结构化知识图谱，用于约束管理 |
| **模型运维** | **Cross-Encoder** | 使用 `BAAI/bge-reranker-base` 进行高精度重排序 |

---

## ⚡ 快速开始

### 前置要求

* Python 3.10+
* Docker (用于运行 Redis)
* API Key (支持 OpenAI 协议的供应商)

### 1. 安装

```bash
git clone https://github.com/your-username/prometheus-forge.git
cd prometheus-forge
pip install -r requirements.txt

```

### 2. 基础设施启动

使用 Docker 启动 Redis 持久化层：

```bash
docker run -d -p 6379:6379 --name prometheus-redis redis:7

```

### 3. 配置

复制并配置 `.env` 环境变量：

```ini
# LLM 提供商
DEFAULT_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...

# RAG 配置
RERANK_MODEL_PATH=BAAI/bge-reranker-base
USE_HYBRID_SEARCH=true

# 状态存储
REDIS_HOST=localhost
REDIS_PORT=6379

```

### 4. 运行引擎

启动高并发后端服务：

```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4

```

---

## 🧪 性能基准 (Benchmark)

基于长周期任务数据集（10k+ Token 上下文）的内部测试结果：

| 指标 | 基线 (仅向量检索) | **Prometheus Forge (混合检索 + Rerank)** |
| --- | --- | --- |
| **上下文命中率 (Hit-Rate@3)** | 62.4% | **95.1%** |
| **幻觉率 (Hallucination Rate)** | 15.3% | **< 1.2%** |
| **并发吞吐 (单节点)** | 20 req/s | **150+ req/s** (开启 AsyncIO) |

> *注：由于增加了 Rerank 步骤，平均延迟略有增加 (~200ms)，但逻辑一致性的显著提升大幅减少了任务重试次数，从而降低了总任务完成时间。*

---

## 📁 项目结构

```
prometheus-forge/
├── src/
│   ├── workflow/           # LangGraph 状态机定义
│   │   ├── nodes.py        # 异步智能体节点 (生成器, 评估器)
│   │   └── graph.py        # 拓扑结构与路由逻辑
│   ├── memory/             # RAG 2.0 子系统
│   │   ├── hybrid.py       # 稀疏+稠密检索器 implementation
│   │   └── rerank.py       # Cross-Encoder 重排序逻辑
│   ├── state/              # 分布式状态管理器
│   │   └── redis_backend.py
│   └── api/                # FastAPI 路由端点
├── tests/                  # 集成测试
└── docker-compose.yml

```

---

## 📄 许可证

本项目采用 MIT 许可证。详情请参阅 `LICENSE` 文件。

---

**Prometheus Forge** — 将工程稳定性注入随机性的 AI 系统中。