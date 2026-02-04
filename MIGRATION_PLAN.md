# Migration Plan: Novel-Agent → Prometheus Forge v3.0

**Document Date**: 2026-02-05
**Target Architecture**: Distributed Agentic Orchestration Engine
**Migration Complexity**: HIGH (Major architectural refactoring)
**Estimated Duration**: 8-12 weeks (phased rollout)

---

## Executive Summary

This plan transforms **Novel-Agent** from a domain-specific novel generation system into **Prometheus Forge**, a generalized distributed agentic orchestration engine. The migration involves:

1. **Abstraction**: Decouple business logic (novels) from orchestration framework
2. **Architectural Upgrade**: Complete LangGraph migration + add Celery distributed execution
3. **Multi-Scenario Support**: Transform from single-purpose to pluggable scenario system
4. **Infrastructure Modernization**: Redis Cluster, Neo4j, advanced RAG pipeline

**Key Principle**: Build generic orchestration engine, then plug "Novel Generation" back in as Scenario #1.

---

## 1. Refactoring Map: File-Level Transformation

### 1.1 Core Infrastructure Layer

| Current File | Target File | Transformation Type | Notes |
|-------------|-------------|---------------------|-------|
| `src/core/state.py` | `src/core/graph_state.py` | 🔄 Refactor | Extract domain-agnostic `AgentState` base class |
| `src/core/state_manager.py` | `src/core/checkpoint_manager.py` | 🔄 Refactor | Rename to align with LangGraph terminology; add Pipeline support |
| `src/core/llm.py` | `src/core/llm_client.py` | 🔄 Refactor | Remove hardcoded model switches; add provider registry |
| `src/core/database.py` | `src/core/persistence/relational.py` | 📦 Move | Organize under `persistence/` module |
| `src/core/db_service.py` | `src/core/persistence/db_service.py` | 📦 Move | Migrate to async patterns (remove sync wrappers) |
| `src/core/prompt_loader.py` | `src/core/prompt_engine.py` | 🔄 Refactor | Add versioning, A/B testing, caching |
| `src/core/config.py` | `src/core/config_loader.py` | 🔄 Refactor | Add scenario-based config injection |
| `src/core/events.py` | `src/core/event_bus.py` | 🔄 Refactor | Implement pub/sub pattern for event streaming |
| ❌ N/A | `src/core/celery_app.py` | ➕ New | Celery app initialization with queue routing |

### 1.2 Agent Layer (Generic Orchestration)

| Current File | Target File | Transformation Type | Notes |
|-------------|-------------|---------------------|-------|
| `src/agents/*` | ❌ **DELETED** | 🗑️ Retire | Legacy agents fully replaced by LangGraph nodes |
| `src/workers/handlers/architect.py` | `src/agents/task_planner.py` | ♻️ Generalize | Extract generic planning logic; move novel-specific to scenario |
| `src/workers/handlers/censor.py` | `src/agents/compliance_guard.py` | ♻️ Generalize | Implement L1 (Regex/Trie) + L2 (LLM) filtering |
| `src/workers/handlers/writer.py` | `src/agents/executor.py` | ♻️ Generalize | Rename to "Executor"; make RAG pipeline configurable |
| `src/workers/handlers/critic.py` | `src/agents/consistency_auditor.py` | ♻️ Generalize | Add differentiated validation strategies |
| `src/workers/handlers/knowledge.py` | `src/agents/knowledge_manager.py` | ♻️ Generalize | Offload to Celery; add ETL pipeline |
| `src/workers/handlers/media.py` | ❌ **DELETED** or `scenarios/novel/media_handler.py` | 🔀 Move | Domain-specific, move to scenario module |
| `src/workers/base.py` | `src/agents/base_agent.py` | 🔄 Refactor | Rename; add scenario awareness |
| `src/workers/controller_tasks.py` | `src/controller/scheduler.py` | 📦 Move | Implement APScheduler-based offline controller |

### 1.3 Workflow Orchestration Layer

| Current File | Target File | Transformation Type | Notes |
|-------------|-------------|---------------------|-------|
| `src/workflow/graph.py` | `src/workflow/graph_builder.py` | 🔄 Refactor | Add scenario-based graph construction |
| `src/workflow/nodes.py` | `src/workflow/node_registry.py` | 🔄 Refactor | Implement dynamic node registration |
| `src/workflow/state.py` | `src/workflow/workflow_state.py` | 🔄 Refactor | Add scenario-specific state extensions |
| `src/workflow/import_graph.py` | `scenarios/novel/import_graph.py` | 🔀 Move | Domain-specific workflow → scenario module |
| ❌ N/A | `src/workflow/execution_engine.py` | ➕ New | Central workflow executor with Celery integration |

### 1.4 RAG & Memory Layer

| Current File | Target File | Transformation Type | Notes |
|-------------|-------------|---------------------|-------|
| `src/rag/indexer.py` | `src/memory/vector_indexer.py` | 📦 Move + 🔄 Refactor | Rename module to "memory"; add incremental indexing |
| `src/rag/retriever.py` | `src/memory/hybrid_retriever.py` | 🔄 Refactor | Implement Vector + Graph parallel retrieval |
| `src/rag/graph_store.py` | `src/memory/graph_memory.py` | 🔄 Refactor | Add Neo4j integration; implement 1-Hop subgraph extraction |
| ❌ N/A | `src/memory/reranker.py` | ➕ New | Cross-Encoder reranking (Celery task) |

### 1.5 API Layer

| Current File | Target File | Transformation Type | Notes |
|-------------|-------------|---------------------|-------|
| `src/api/main.py` | `src/api/app.py` | 🔄 Refactor | Remove domain-specific routes; add scenario registry |
| `src/api/models.py` | `src/persistence/models/base.py` | 📦 Move | Split into `base.py` + scenario-specific models |
| `src/api/routers/novels.py` | `scenarios/novel/routers/novel_router.py` | 🔀 Move | Domain-specific API → scenario module |
| `src/api/routers/workflow.py` | `src/api/routers/workflow_router.py` | 🔄 Refactor | Keep as generic workflow execution endpoint |
| `src/api/routers/prompts.py` | `src/api/routers/prompt_router.py` | ✅ Keep | Generic prompt management API |
| `src/api/routers/monitor.py` | `src/api/routers/monitor_router.py` | ✅ Keep | Generic monitoring API |
| `src/api/services/novel_service.py` | `scenarios/novel/services/novel_service.py` | 🔀 Move | Domain-specific service |
| `src/api/services/import_service.py` | `scenarios/novel/services/import_service.py` | 🔀 Move | Domain-specific service |
| `src/api/websocket.py` | `src/api/websocket_manager.py` | ✅ Keep | Generic WebSocket broadcast |

### 1.6 Scenario Module (New Structure)

| Current Location | Target File | Transformation Type | Notes |
|-----------------|-------------|---------------------|-------|
| `src/agents/novelist.py` (logic) | `scenarios/novel/novel_scenario.py` | ♻️ Extract | Business logic moved here |
| `src/agents/builder.py` (logic) | `scenarios/novel/context_builder.py` | ♻️ Extract | Character/world context assembly |
| `src/api/models.py` (Novel, Chapter) | `scenarios/novel/models.py` | 🔀 Move | Domain models |
| `config/prompts/*.yaml` | `scenarios/novel/prompts/*.yaml` | 🔀 Move | Novel-specific prompts |
| ❌ N/A | `scenarios/novel/config.yaml` | ➕ New | Scenario-specific configuration |
| ❌ N/A | `scenarios/novel/__init__.py` | ➕ New | Scenario registration hook |

### 1.7 Controller Module (New - Offline Scheduler)

| Target File | Source | Transformation Type | Notes |
|-------------|--------|---------------------|-------|
| `src/controller/scheduler.py` | New | ➕ New | APScheduler-based cron daemon |
| `src/controller/memory_consolidation.py` | `src/workers/handlers/knowledge.py` | ♻️ Generalize | Nightly memory archival job |
| `src/controller/index_rebuilder.py` | New | ➕ New | Batch vector index rebuilding |
| `src/controller/health_checker.py` | New | ➕ New | System health monitoring job |

### 1.8 Celery Tasks Module (New - Distributed Execution)

| Target File | Current Source | Transformation Type | Notes |
|-------------|---------------|---------------------|-------|
| `src/tasks/__init__.py` | New | ➕ New | Celery app + task registry |
| `src/tasks/compute_tasks.py` | New (extract from handlers) | ➕ New | CPU-intensive: Rerank, entity extraction |
| `src/tasks/io_tasks.py` | New (extract from handlers) | ➕ New | I/O-intensive: DB writes, graph updates |
| `src/tasks/memory_tasks.py` | `src/workers/handlers/knowledge.py` | ♻️ Generalize | Memory consolidation tasks |

---

## 2. Gap Analysis: AS-IS vs TO-BE

### 2.1 Architecture Comparison

| Component | Current (Novel-Agent) | Target (Prometheus Forge v3.0) | Gap |
|-----------|----------------------|--------------------------------|-----|
| **Orchestration** | LangGraph (partial) + legacy agents | LangGraph (complete) | 🟡 Medium |
| **Execution Layer** | Sync/async mix, single-threaded | Celery multi-worker (prefork) | 🔴 Critical |
| **State Management** | Redis (string-based) + SQLite | Redis Cluster (Hash+Pipeline) + SQLite | 🟠 High |
| **Graph Memory** | ChromaDB only | ChromaDB + Neo4j (hybrid) | 🔴 Critical |
| **Prompt System** | Database (basic) | Versioned + A/B testing + caching | 🟠 High |
| **Agent Architecture** | Domain-coupled handlers | Generic agents + scenario plugins | 🔴 Critical |
| **Offline Processing** | None | APScheduler Controller | 🔴 Critical |
| **Compliance** | Basic censor node | L1 (Regex/Trie) + L2 (LLM) funnel | 🟠 High |
| **Validation** | Basic critic scoring | Differentiated strategies (Rule/NLI) | 🟠 High |

### 2.2 Functional Gap Matrix

| Feature | Current Support | Target Requirement | Implementation Gap |
|---------|----------------|-------------------|-------------------|
| **Multi-Scenario Support** | ❌ None (novel-only) | ✅ Pluggable scenarios | Full refactoring needed |
| **Intent Classification** | ❌ None | ✅ Planner with Few-Shot | Build from scratch |
| **DAG Compilation** | ❌ Fixed workflow | ✅ Dynamic DAG generation | Planner agent refactor |
| **L1 Compliance (Regex/Trie)** | ❌ None | ✅ AC automaton + Regex | Implement AC automaton |
| **L2 Compliance (LLM)** | ✅ Basic LLM check | ✅ Policy injection | Enhance prompt system |
| **Hybrid Retrieval** | ⚠️ Vector only | ✅ Vector + Graph parallel | Add Neo4j integration |
| **Cross-Encoder Rerank** | ❌ None | ✅ BAAI/bge-reranker-v2-m3 | Implement as Celery task |
| **Fact Extraction** | ❌ None | ✅ Claim extraction for audit | Build Auditor agent |
| **Async Memory Write** | ⚠️ Partial | ✅ Fire-and-Forget Celery | Migrate to Celery |
| **Entity Linking** | ❌ None | ✅ Normalization to knowledge graph | Build ETL pipeline |
| **Dual-Write Storage** | ❌ None | ✅ Graph + Vector simultaneous | Implement in Knowledge Manager |
| **Batch Processing** | ❌ None | ✅ Controller fan-out | Build APScheduler controller |
| **Resource Isolation** | ❌ None | ✅ Compute vs IO queue separation | Configure Celery queues |

### 2.3 Data Model Gaps

| Domain Concept | Current Implementation | Target Implementation | Migration Action |
|---------------|----------------------|----------------------|------------------|
| **Characters** | Embedded JSON in NovelSetting | Nodes in Neo4j + embeddings in Chroma | Extract to graph entities |
| **Relationships** | Implicit in text | Explicit edges: (User)-[:LIKES]->(Item) | Build relationship extraction |
| **User Profile** | ❌ Not modeled | (User)-[:HAS_TAG]->(Price_Sensitive) | Create user profiling system |
| **Events** | AuditLogEntry (flat) | (Order)-[:HAS_EVENT]->(Dispute) | Migrate to graph events |
| **Prompts** | Single version in DB | Versioned with A/B testing metadata | Add versioning schema |
| **Checkpoints** | Redis hash (untyped) | Typed State with metadata | Implement typed checkpointer |

### 2.4 Technical Infrastructure Gaps

| Infrastructure | Current | Target | Action Required |
|---------------|---------|--------|-----------------|
| **Redis** | Single instance | Redis Cluster | Deploy cluster + update clients |
| **Graph DB** | ❌ None | Neo4j | Deploy Neo4j + write Cypher queries |
| **Vector DB** | ChromaDB (basic) | ChromaDB (HNSW optimized) | Tune: M=16, ef_construction=200 |
| **Task Queue** | Redis list (manual) | Celery + Redis broker | Setup Celery workers |
| **Scheduler** | ❌ None | APScheduler | Implement controller daemon |
| **Monitoring** | Basic WebSocket | Structured logging + metrics | Add observability stack |

---

## 3. Migration Strategy: Phased Rollout

### Phase 0: Preparation (Week 1-2)

**Goal**: Set up foundational infrastructure without breaking existing system

#### Tasks:
1. **Deploy Infrastructure**
   - [ ] Redis Cluster setup (3 masters + 3 replicas)
   - [ ] Neo4j deployment + initial schema design
   - [ ] Celery workers deployment (2 queues: compute_queue, io_queue)
   - [ ] APScheduler controller process setup

2. **Create New Module Structure**
   ```
   mkdir -p src/agents src/memory src/controller src/tasks scenarios/novel
   ```

3. **Database Schema Extensions**
   - [ ] Add `prompt_versions` table (versioning support)
   - [ ] Add `scenario_configs` table
   - [ ] Add `user_profiles` table (for future multi-user support)

4. **Testing Infrastructure**
   - [ ] Setup pytest framework
   - [ ] Create test fixtures for agents
   - [ ] Implement integration test harness

**Risk Mitigation**:
- All new infrastructure runs parallel to existing system
- No breaking changes to current API
- Feature flags control new code paths

---

### Phase 1: Core Agent Abstraction (Week 3-5)

**Goal**: Build generic agent framework while keeping novel generation working

#### 1.1 Extract Generic Agents

**Task Planner Agent** (`src/agents/task_planner.py`)
```python
class TaskPlannerAgent:
    def __init__(self, scenario_config: ScenarioConfig):
        self.intent_classifier = scenario_config.intent_classifier
        self.dag_compiler = scenario_config.dag_compiler

    async def plan(self, user_query: str, global_state: Dict) -> Plan:
        # Generic planning logic
        intent = await self.classify_intent(user_query)
        dag = await self.compile_dag(intent, global_state)
        return Plan(intent=intent, dag=dag)
```

**Migration Steps**:
- [x] Copy `src/workers/handlers/architect.py` → `src/agents/task_planner.py`
- [ ] Extract novel-specific logic to `scenarios/novel/novel_planner.py`
- [ ] Create `PlannerConfig` with intent prompts + DAG templates
- [ ] Update workflow graph to use new agent

**Compliance Guard Agent** (`src/agents/compliance_guard.py`)
```python
class ComplianceGuard:
    def __init__(self, scenario_config: ScenarioConfig):
        self.l1_filter = RegexTrie(scenario_config.blacklist)
        self.l2_llm = LLMClient()
        self.safety_policy = scenario_config.safety_policy

    async def check(self, text: str, direction: str) -> CheckResult:
        # L1: Deterministic (ms-level)
        if self.l1_filter.match(text):
            return CheckResult(blocked=True, reason="L1_HIT")

        # L2: Semantic (LLM)
        is_safe = await self.l2_llm.check_safety(text, self.safety_policy)
        return CheckResult(blocked=not is_safe)
```

**Migration Steps**:
- [ ] Copy `src/workers/handlers/censor.py` → `src/agents/compliance_guard.py`
- [ ] Implement AC automaton for L1 filtering
- [ ] Add policy injection mechanism for L2
- [ ] Create compliance config: `scenarios/novel/compliance_policy.yaml`

**Executor Agent** (`src/agents/executor.py`)
```python
class ExecutorAgent:
    def __init__(self, scenario_config: ScenarioConfig):
        self.retriever = HybridRetriever(
            vector_db=ChromaDB(),
            graph_db=Neo4jClient(),
            strategy=scenario_config.retrieval_strategy
        )
        self.reranker = CeleryReranker()  # Offloaded to Celery

    async def execute(self, query: str, context: Dict) -> Response:
        # Step 1: Query rewrite
        rewritten = await self.rewrite_query(query, context)

        # Step 2: Hybrid retrieval
        docs = await self.retriever.retrieve(rewritten)

        # Step 3: Rerank (Celery async)
        ranked_docs = await self.reranker.rerank(query, docs)

        # Step 4: Generate
        response = await self.generate(query, ranked_docs, context)
        return response
```

**Migration Steps**:
- [ ] Merge `writer.py` + `builder.py` → `src/agents/executor.py`
- [ ] Extract novel context building to `scenarios/novel/context_builder.py`
- [ ] Implement hybrid retriever (vector + graph)
- [ ] Create Celery task: `src/tasks/compute_tasks.py:rerank_documents`

**Consistency Auditor Agent** (`src/agents/consistency_auditor.py`)
```python
class ConsistencyAuditor:
    def __init__(self, scenario_config: ScenarioConfig):
        self.strategy = scenario_config.validation_strategy  # Rule-based or NLI

    async def audit(self, draft: str, ground_truth: Dict) -> AuditResult:
        # Extract claims from draft
        claims = await self.extract_claims(draft)

        # Validate with strategy
        if isinstance(self.strategy, RuleBasedStrategy):
            errors = self.strategy.validate(claims, ground_truth)
        elif isinstance(self.strategy, NLIStrategy):
            errors = await self.strategy.validate(claims, ground_truth)

        if errors:
            return AuditResult(passed=False, feedback=errors)
        return AuditResult(passed=True)
```

**Migration Steps**:
- [ ] Copy `src/workers/handlers/critic.py` → `src/agents/consistency_auditor.py`
- [ ] Implement claim extraction (LLM prompt)
- [ ] Create `RuleBasedStrategy` for novel validation
- [ ] Create `NLIStrategy` for general validation

**Knowledge Manager Agent** (`src/agents/knowledge_manager.py`)
```python
class KnowledgeManager:
    def __init__(self):
        self.graph_db = Neo4jClient()
        self.vector_db = ChromaDB()

    async def process_session(self, session_id: str):
        """Offloaded to Celery (Fire-and-Forget)"""
        # Extract entities/relations from conversation
        entities = await self.extract_entities(session_id)

        # Entity linking
        linked = await self.link_entities(entities)

        # Dual-write
        await asyncio.gather(
            self.graph_db.merge_entities(linked),
            self.vector_db.upsert_session_summary(session_id)
        )
```

**Migration Steps**:
- [ ] Copy `src/workers/handlers/knowledge.py` → `src/agents/knowledge_manager.py`
- [ ] Migrate to Celery task: `src/tasks/memory_tasks.py:consolidate_memory`
- [ ] Implement Neo4j Cypher queries for graph updates
- [ ] Add entity linking logic

#### 1.2 Refactor Workflow Graph

**Update**: `src/workflow/graph_builder.py`
```python
class GraphBuilder:
    def build_scenario_graph(self, scenario: ScenarioConfig) -> StateGraph:
        graph = StateGraph(AgentState)

        # Add nodes (dynamically based on scenario)
        graph.add_node("compliance_in", scenario.agents.compliance_guard.check_input)
        graph.add_node("planner", scenario.agents.task_planner.plan)
        graph.add_node("executor", scenario.agents.executor.execute)
        graph.add_node("auditor", scenario.agents.consistency_auditor.audit)
        graph.add_node("compliance_out", scenario.agents.compliance_guard.check_output)

        # Add edges
        graph.add_edge("compliance_in", "planner")
        graph.add_edge("planner", "executor")
        graph.add_edge("executor", "auditor")
        graph.add_conditional_edges(
            "auditor",
            self.should_revise,
            {
                "pass": "compliance_out",
                "fail": "executor"  # Loop back with feedback
            }
        )
        graph.add_edge("compliance_out", END)

        return graph.compile()
```

**Migration Steps**:
- [ ] Refactor `src/workflow/graph.py` → `graph_builder.py`
- [ ] Make node registration dynamic (registry pattern)
- [ ] Add conditional routing based on Auditor feedback
- [ ] Support scenario-specific node insertion

**Deliverables**:
- ✅ 5 generic agents implemented
- ✅ Novel scenario still works (backward compatibility)
- ✅ Integration tests pass

---

### Phase 2: Memory & RAG Upgrade (Week 6-7)

**Goal**: Implement hybrid retrieval (Vector + Graph) and Cross-Encoder reranking

#### 2.1 Neo4j Integration

**Graph Schema Design**:
```cypher
// Entities
CREATE (u:User {id: $user_id, level: "VIP"})
CREATE (n:Novel {id: $novel_id, title: $title})
CREATE (c:Character {name: $name, personality: $personality})
CREATE (ch:Chapter {id: $chapter_id, index: $index})

// Relationships
CREATE (u)-[:CREATED]->(n)
CREATE (n)-[:HAS_CHARACTER]->(c)
CREATE (n)-[:HAS_CHAPTER]->(ch)
CREATE (c)-[:APPEARS_IN]->(ch)

// Attributes as properties
CREATE (c)-[:HAS_TRAIT]->(t:Trait {name: "Brave"})
```

**Migration Steps**:
- [ ] Design Neo4j schema for novel domain
- [ ] Implement `src/memory/graph_memory.py` with Cypher queries
- [ ] Migrate existing character data from JSON → Neo4j
  ```python
  # Migration script
  for novel in novels:
      bios = get_novel_setting(novel.id, "bios")
      for bio in bios:
          graph_db.execute("""
              MERGE (c:Character {name: $name})
              SET c.personality = $personality,
                  c.appearance = $appearance
          """, bio)
  ```
- [ ] Implement 1-Hop subgraph extraction:
  ```cypher
  MATCH (c:Character {name: $name})-[r]-(related)
  RETURN c, r, related
  LIMIT 20
  ```

#### 2.2 Hybrid Retriever

**Implementation**: `src/memory/hybrid_retriever.py`
```python
class HybridRetriever:
    async def retrieve(self, query: str) -> List[Document]:
        # Parallel execution
        vector_task = self.vector_db.search(query, top_k=50)
        graph_task = self.graph_db.subgraph_search(query, hops=1)

        vector_docs, graph_docs = await asyncio.gather(vector_task, graph_task)

        # Merge results (deduplication)
        return self.merge_documents(vector_docs, graph_docs)
```

**Migration Steps**:
- [ ] Implement parallel retrieval
- [ ] Add deduplication logic
- [ ] Configure scenario-specific retrieval strategies in config

#### 2.3 Cross-Encoder Reranking (Celery)

**Celery Task**: `src/tasks/compute_tasks.py`
```python
from celery import Celery

app = Celery('prometheus', broker='redis://localhost:6379/0')

@app.task(queue='compute_queue')
def rerank_documents(query: str, documents: List[Dict]) -> List[Dict]:
    from sentence_transformers import CrossEncoder

    model = CrossEncoder('BAAI/bge-reranker-v2-m3')
    pairs = [(query, doc['content']) for doc in documents]
    scores = model.predict(pairs)

    # Sort by score
    ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, score in ranked[:10]]
```

**LangGraph Integration**:
```python
# In executor node
async def executor_node(state: AgentState):
    # ... retrieval ...

    # Call Celery (async wait)
    task = rerank_documents.apply_async(args=[query, docs], queue='compute_queue')

    # Non-blocking wait
    while not task.ready():
        await asyncio.sleep(0.1)

    ranked_docs = task.get()
    # ... continue generation ...
```

**Migration Steps**:
- [ ] Install Celery + Redis broker
- [ ] Create `src/tasks/__init__.py` with app config
- [ ] Implement rerank task with model loading
- [ ] Configure worker: `celery -A src.tasks worker -Q compute_queue -c 4`
- [ ] Update Executor agent to call Celery

**Deliverables**:
- ✅ Neo4j integrated with character/chapter data
- ✅ Hybrid retriever operational
- ✅ Cross-Encoder reranking via Celery
- ✅ Performance improvement: Rerank latency < 500ms

---

### Phase 3: Scenario System & Configuration (Week 8-9)

**Goal**: Transform system from single-purpose to multi-scenario orchestration engine

#### 3.1 Scenario Configuration Schema

**File**: `scenarios/novel/config.yaml`
```yaml
scenario:
  name: "novel_generation"
  version: "1.0.0"
  description: "AI-powered novel chapter generation"

# Agent configurations
agents:
  task_planner:
    intent_classifier_prompt: "scenarios/novel/prompts/intent_classifier.yaml"
    dag_templates:
      generate_chapter: "scenarios/novel/prompts/dag_generate_chapter.yaml"
      revise_chapter: "scenarios/novel/prompts/dag_revise_chapter.yaml"

  compliance_guard:
    l1_filters:
      sensitive_words: "scenarios/novel/blacklists/sensitive_words.txt"
      regex_patterns: ["\\d{17,18}"]  # ID numbers
    l2_policy: "scenarios/novel/prompts/compliance_policy.yaml"

  executor:
    retrieval_strategy:
      vector:
        enabled: true
        collection: "novel_chapters"
        top_k: 50
      graph:
        enabled: true
        max_hops: 1
        entity_types: ["Character", "Chapter", "PlotPoint"]
    rerank:
      enabled: true
      model: "BAAI/bge-reranker-v2-m3"
      threshold: 0.5
    generation_prompt: "scenarios/novel/prompts/writer_generation.yaml"

  consistency_auditor:
    strategy: "rule_based"  # or "nli"
    rules:
      - type: "character_consistency"
        check: "scenarios/novel/validators/character_validator.py"
      - type: "plot_continuity"
        check: "scenarios/novel/validators/plot_validator.py"

  knowledge_manager:
    entity_types: ["Character", "PlotPoint", "Setting"]
    extraction_prompt: "scenarios/novel/prompts/entity_extraction.yaml"

# Workflow topology
workflow:
  nodes:
    - compliance_in
    - planner
    - executor
    - auditor
    - compliance_out
  edges:
    - [compliance_in, planner]
    - [planner, executor]
    - [executor, auditor]
    - [auditor, compliance_out]  # if pass
    - [auditor, executor]  # if fail (loop)
  conditional_routing:
    auditor:
      pass: compliance_out
      fail: executor
      max_retries: 3

# Data models
models:
  - scenarios.novel.models.Novel
  - scenarios.novel.models.Chapter
  - scenarios.novel.models.Character
```

#### 3.2 Scenario Registration

**File**: `scenarios/novel/__init__.py`
```python
from src.core.scenario_registry import ScenarioRegistry
from .config import NovelScenarioConfig
from .novel_scenario import NovelScenario

def register():
    registry = ScenarioRegistry.get_instance()
    config = NovelScenarioConfig.from_yaml("scenarios/novel/config.yaml")
    scenario = NovelScenario(config)
    registry.register("novel_generation", scenario)

# Auto-register on import
register()
```

**File**: `src/core/scenario_registry.py`
```python
class ScenarioRegistry:
    _instance = None
    _scenarios = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, name: str, scenario: BaseScenario):
        self._scenarios[name] = scenario

    def get_scenario(self, name: str) -> BaseScenario:
        return self._scenarios.get(name)

    def list_scenarios(self) -> List[str]:
        return list(self._scenarios.keys())
```

#### 3.3 Migrate Novel-Specific Logic

**Extract Business Logic**:

```python
# scenarios/novel/novel_scenario.py
class NovelScenario(BaseScenario):
    def __init__(self, config: NovelScenarioConfig):
        self.config = config
        self.context_builder = NovelContextBuilder()

    def build_context(self, novel_id: str, chapter_num: int) -> Dict:
        """Novel-specific context assembly"""
        # Load characters from Neo4j
        characters = self.graph_db.query("""
            MATCH (n:Novel {id: $novel_id})-[:HAS_CHARACTER]->(c:Character)
            RETURN c
        """, {"novel_id": novel_id})

        # Load previous chapters
        prev_chapters = self.db.query(Chapter).filter(
            Chapter.novel_id == novel_id,
            Chapter.index < chapter_num
        ).order_by(Chapter.index.desc()).limit(3).all()

        return {
            "characters": characters,
            "previous_chapters": prev_chapters,
            "world_setting": self.get_world_setting(novel_id)
        }

    def validate_output(self, draft: str, context: Dict) -> ValidationResult:
        """Novel-specific validation rules"""
        # Check character consistency
        mentioned_characters = extract_character_names(draft)
        known_characters = {c['name'] for c in context['characters']}

        if unknown := mentioned_characters - known_characters:
            return ValidationResult(
                passed=False,
                errors=[f"Unknown character: {name}" for name in unknown]
            )

        return ValidationResult(passed=True)
```

**Migration Steps**:
- [ ] Create `scenarios/novel/` directory structure
- [ ] Move `src/api/models.py` (Novel/Chapter/ChapterDraft) → `scenarios/novel/models.py`
- [ ] Move `src/api/routers/novels.py` → `scenarios/novel/routers/novel_router.py`
- [ ] Move `src/api/services/novel_service.py` → `scenarios/novel/services/novel_service.py`
- [ ] Extract context building from `builder.py` → `scenarios/novel/context_builder.py`
- [ ] Move prompt files: `config/prompts/*.yaml` → `scenarios/novel/prompts/*.yaml`
- [ ] Update imports across codebase

#### 3.4 Update API Layer

**File**: `src/api/app.py`
```python
from fastapi import FastAPI
from src.core.scenario_registry import ScenarioRegistry
from src.api.routers import workflow_router, monitor_router

# Auto-load scenarios
import scenarios.novel  # Triggers registration

app = FastAPI()

# Generic routes
app.include_router(workflow_router.router, prefix="/workflow", tags=["workflow"])
app.include_router(monitor_router.router, prefix="/monitor", tags=["monitor"])

# Dynamically load scenario routes
registry = ScenarioRegistry.get_instance()
for scenario_name in registry.list_scenarios():
    scenario = registry.get_scenario(scenario_name)
    if scenario.routers:
        for router in scenario.routers:
            app.include_router(router, prefix=f"/scenarios/{scenario_name}")
```

**Workflow Endpoint** (`src/api/routers/workflow_router.py`):
```python
@router.post("/execute")
async def execute_workflow(request: WorkflowRequest):
    """Generic workflow execution endpoint"""
    registry = ScenarioRegistry.get_instance()
    scenario = registry.get_scenario(request.scenario_name)

    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Build graph for scenario
    graph = GraphBuilder().build_scenario_graph(scenario.config)

    # Execute
    result = await graph.ainvoke(request.initial_state)
    return result
```

**Deliverables**:
- ✅ Scenario system operational
- ✅ Novel generation works as Scenario #1
- ✅ API routes dynamically loaded
- ✅ Configuration externalized to YAML

---

### Phase 4: Offline Controller & Memory Consolidation (Week 10)

**Goal**: Implement APScheduler-based controller for batch processing

#### 4.1 Controller Setup

**File**: `src/controller/scheduler.py`
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.tasks.memory_tasks import consolidate_memory
from src.core.state_manager import StateManager

class OfflineController:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.state_manager = StateManager()

    def start(self):
        # Daily memory consolidation (2:00 AM)
        self.scheduler.add_job(
            self.run_memory_consolidation,
            trigger='cron',
            hour=2,
            minute=0
        )

        # Weekly index rebuilding (Sunday 3:00 AM)
        self.scheduler.add_job(
            self.run_index_rebuild,
            trigger='cron',
            day_of_week='sun',
            hour=3,
            minute=0
        )

        self.scheduler.start()

    async def run_memory_consolidation(self):
        """Fan-out to Celery workers"""
        active_users = await self.state_manager.get_active_users_last_24h()

        for user_id in active_users:
            consolidate_memory.apply_async(
                args=[user_id],
                queue='io_queue'
            )
```

**Celery Task**: `src/tasks/memory_tasks.py`
```python
@app.task(queue='io_queue')
def consolidate_memory(user_id: str):
    """Process user's conversation history and update knowledge graph"""
    # 1. Load conversations from Redis
    sessions = redis_client.lrange(f"sessions:{user_id}", 0, -1)

    # 2. Extract entities/relations
    entities = []
    for session in sessions:
        extracted = llm_client.extract_entities(session)
        entities.extend(extracted)

    # 3. Entity linking
    linked = entity_linker.link(entities)

    # 4. Update graph
    graph_db.merge_entities(linked)

    # 5. Generate summary and upsert to vector DB
    summary = llm_client.summarize(sessions)
    vector_db.upsert(user_id, summary)
```

#### 4.2 Index Rebuilding

**File**: `src/controller/index_rebuilder.py`
```python
async def rebuild_vector_index(collection_name: str, embedding_model: str):
    """Rebuild entire vector index with new embedding model"""
    # 1. Fetch all documents
    docs = await db.query(Document).all()

    # 2. Fan-out to Celery (batch processing)
    batch_size = 100
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i+batch_size]
        rebuild_batch.apply_async(
            args=[batch, embedding_model, collection_name],
            queue='compute_queue'
        )

@app.task(queue='compute_queue')
def rebuild_batch(documents: List[Dict], model_name: str, collection: str):
    """Re-embed and re-index batch of documents"""
    embedder = EmbeddingModel(model_name)

    for doc in documents:
        embedding = embedder.encode(doc['content'])
        vector_db.upsert(
            collection=collection,
            id=doc['id'],
            embedding=embedding,
            metadata=doc['metadata']
        )
```

**Deliverables**:
- ✅ APScheduler controller running
- ✅ Nightly memory consolidation job
- ✅ Weekly index rebuilding job
- ✅ Fan-out pattern tested (1000+ tasks)

---

### Phase 5: Testing, Optimization & Documentation (Week 11-12)

**Goal**: Production readiness

#### 5.1 Testing Suite

**Unit Tests** (`tests/unit/`):
```python
# tests/unit/test_agents.py
@pytest.mark.asyncio
async def test_task_planner_intent_classification():
    config = load_test_config("novel")
    planner = TaskPlannerAgent(config)

    result = await planner.classify_intent("生成第3章")
    assert result.intent == "GENERATE_CHAPTER"

@pytest.mark.asyncio
async def test_compliance_guard_l1_filter():
    guard = ComplianceGuard(load_test_config())
    result = await guard.check("这是测试敏感词", direction="input")
    assert result.blocked == True
```

**Integration Tests** (`tests/integration/`):
```python
# tests/integration/test_workflow.py
@pytest.mark.asyncio
async def test_full_chapter_generation_workflow():
    graph = GraphBuilder().build_scenario_graph(novel_config)

    initial_state = {
        "novel_id": "test-novel-123",
        "chapter_num": 1,
        "messages": [HumanMessage(content="生成第1章")]
    }

    result = await graph.ainvoke(initial_state)

    assert result['status'] == 'completed'
    assert result['draft_content'] is not None
    assert result['critique_score'] >= 75
```

**Load Tests** (`tests/load/`):
```bash
# Using locust
locust -f tests/load/test_workflow.py --host=http://localhost:8000
```

#### 5.2 Performance Optimization

**Checkpoints**:
- [ ] Rerank latency < 500ms (P95)
- [ ] End-to-end workflow < 30s for chapter generation
- [ ] Redis pipeline reduces RTT by 50%
- [ ] Memory consolidation processes 10K users/hour

**Optimizations**:
1. **Redis Pipeline**:
   ```python
   pipe = redis_client.pipeline()
   pipe.hset(f"checkpoint:{thread_id}", state)
   pipe.rpush(f"audit:{thread_id}", log_entry)
   pipe.execute()  # Single RTT
   ```

2. **ChromaDB HNSW Tuning**:
   ```python
   collection = client.create_collection(
       name="novel_chapters",
       metadata={
           "hnsw:M": 16,
           "hnsw:ef_construction": 200
       }
   )
   ```

3. **Celery Worker Tuning**:
   ```bash
   # Compute queue: Low concurrency for CPU-bound tasks
   celery -A src.tasks worker -Q compute_queue -c 4 --prefetch-multiplier=1

   # IO queue: High concurrency for I/O-bound tasks
   celery -A src.tasks worker -Q io_queue -c 20 --prefetch-multiplier=4
   ```

#### 5.3 Documentation

**Architecture Docs**:
- [ ] `docs/architecture.md` - System overview
- [ ] `docs/agents.md` - Agent design patterns
- [ ] `docs/scenarios.md` - How to create new scenarios
- [ ] `docs/deployment.md` - Production deployment guide

**API Docs**:
- [ ] OpenAPI schema auto-generated (FastAPI)
- [ ] Scenario-specific endpoint documentation
- [ ] WebSocket protocol documentation

**Runbooks**:
- [ ] `docs/runbooks/incident_response.md`
- [ ] `docs/runbooks/scaling.md`
- [ ] `docs/runbooks/disaster_recovery.md`

**Deliverables**:
- ✅ 80%+ test coverage
- ✅ All integration tests passing
- ✅ Performance benchmarks met
- ✅ Complete documentation

---

## 4. Risk Assessment & Mitigation

### 4.1 Critical Risks

| Risk | Severity | Probability | Impact | Mitigation |
|------|----------|------------|--------|------------|
| **Data Loss During Migration** | 🔴 Critical | Medium | Loss of existing novel data | 1. Full database backup before Phase 1<br>2. Run parallel systems during migration<br>3. Implement rollback scripts |
| **Performance Regression** | 🟠 High | Medium | Slower chapter generation | 1. Benchmark before/after each phase<br>2. Feature flags to disable new features<br>3. Keep legacy code path available |
| **Neo4j Learning Curve** | 🟠 High | High | Delayed graph integration | 1. Prototype Neo4j integration in Phase 0<br>2. Hire consultant if needed<br>3. Fallback to vector-only retrieval |
| **Celery Overhead** | 🟡 Medium | Low | Increased latency | 1. Use Fire-and-Forget for non-critical tasks<br>2. Tune prefetch settings<br>3. Monitor task queue length |
| **Backward Compatibility** | 🟡 Medium | Medium | Break existing novel API | 1. Version API endpoints (/v1/, /v2/)<br>2. Maintain legacy endpoints<br>3. Client migration guide |

### 4.2 Mitigation Strategies

**Phase-Gate Approach**:
- Each phase requires sign-off before proceeding
- Automated tests must pass (95%+ coverage)
- Performance benchmarks must meet thresholds
- Rollback plan documented and tested

**Feature Flags**:
```python
# settings.yaml
feature_flags:
  use_neo4j: false           # Enable after Phase 2
  use_celery_rerank: false   # Enable after Phase 2
  use_new_agents: false      # Enable after Phase 1
  enable_controller: false   # Enable after Phase 4
```

**Parallel Deployment**:
- Run old and new systems side-by-side during Phase 1-3
- Use load balancer to route 10% traffic to new system
- Gradually increase to 100% over 2 weeks

---

## 5. Success Criteria

### 5.1 Functional Requirements

- [ ] Novel generation workflow produces identical quality output (critic score ≥ 75)
- [ ] All existing API endpoints remain functional (backward compatibility)
- [ ] New scenario can be added in < 2 days (pluggability)
- [ ] Multi-user support (different scenarios per user)
- [ ] Offline controller processes 10K+ users per night

### 5.2 Non-Functional Requirements

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| **End-to-end Latency** | ~60s | < 30s | 🎯 Target |
| **Rerank Latency** | N/A | < 500ms (P95) | 🎯 Target |
| **Test Coverage** | 0% | > 80% | 🎯 Target |
| **Memory Consolidation** | N/A | 10K users/hour | 🎯 Target |
| **Concurrent Users** | ~10 | > 100 | 🎯 Target |
| **System Uptime** | ~95% | > 99.5% | 🎯 Target |

### 5.3 Business Metrics

- [ ] System can support 3+ scenarios (novel, e-commerce, customer service)
- [ ] Development velocity: New feature in < 1 week
- [ ] Incident recovery time: < 15 minutes
- [ ] Documentation completeness: 100% of public APIs

---

## 6. Rollout Timeline

```
Week 1-2:  [████████████████████████] Phase 0: Infrastructure Preparation
Week 3-5:  [████████████████████████] Phase 1: Core Agent Abstraction
Week 6-7:  [████████████████████████] Phase 2: Memory & RAG Upgrade
Week 8-9:  [████████████████████████] Phase 3: Scenario System
Week 10:   [████████████████████████] Phase 4: Offline Controller
Week 11-12:[████████████████████████] Phase 5: Testing & Optimization

Total: 12 weeks (3 months)
```

**Milestones**:
- **M1 (Week 2)**: Infrastructure deployed, parallel systems running
- **M2 (Week 5)**: Generic agents complete, novel scenario migrated
- **M3 (Week 7)**: Hybrid retrieval + reranking operational
- **M4 (Week 9)**: Scenario system live, API updated
- **M5 (Week 10)**: Controller running, memory consolidation tested
- **M6 (Week 12)**: Production release, full documentation

---

## 7. Post-Migration: Next Scenarios

### 7.1 Scenario #2: E-Commerce After-Sales (Example)

**Config**: `scenarios/after_sales/config.yaml`
```yaml
scenario:
  name: "after_sales"
  agents:
    task_planner:
      intent_classifier_prompt: "scenarios/after_sales/prompts/intent.yaml"
      dag_templates:
        refund_request: "scenarios/after_sales/prompts/dag_refund.yaml"

    compliance_guard:
      l1_filters:
        blacklist: ["password", "CVV"]
      l2_policy: "scenarios/after_sales/prompts/compliance.yaml"

    executor:
      retrieval_strategy:
        graph:
          entity_types: ["Order", "Policy", "User"]

    consistency_auditor:
      strategy: "rule_based"
      rules:
        - type: "refund_amount_check"
          check: "scenarios/after_sales/validators/refund_validator.py"
```

**Domain Models**: `scenarios/after_sales/models.py`
```python
class Order(Base):
    id: UUID
    user_id: UUID
    status: OrderStatus
    payment_amount: Decimal

class RefundPolicy(Base):
    sku_category: str
    max_days: int
    conditions: JSON
```

**Estimated Effort**: 1-2 weeks (with generic framework in place)

---

## 8. Appendix: Code Migration Checklist

### A. Files to Delete (Post-Migration)
- [ ] `src/agents/novelist.py` - Replaced by generic Executor + NovelScenario
- [ ] `src/agents/writer.py` - Merged into Executor
- [ ] `src/agents/editor.py` - Merged into Auditor
- [ ] `src/agents/planner.py` - Replaced by TaskPlanner
- [ ] `src/agents/builder.py` - Moved to scenarios/novel/context_builder.py
- [ ] `src/agents/orchestrator.py` - Replaced by LangGraph topology
- [ ] `src/agents/reviewers/*` - Replaced by Auditor strategies
- [ ] `src/workers/controller_tasks.py` - Replaced by Controller scheduler

### B. Files to Refactor
- [ ] `src/core/llm.py` → Remove hardcoded `.switch_model()` calls
- [ ] `src/core/prompt_loader.py` → Add versioning + caching
- [ ] `src/workflow/graph.py` → Add scenario-based construction
- [ ] `src/api/main.py` → Dynamic scenario route loading

### C. New Files to Create
- [ ] `src/agents/task_planner.py`
- [ ] `src/agents/compliance_guard.py`
- [ ] `src/agents/executor.py`
- [ ] `src/agents/consistency_auditor.py`
- [ ] `src/agents/knowledge_manager.py`
- [ ] `src/memory/hybrid_retriever.py`
- [ ] `src/memory/graph_memory.py`
- [ ] `src/memory/reranker.py`
- [ ] `src/controller/scheduler.py`
- [ ] `src/tasks/__init__.py`
- [ ] `src/tasks/compute_tasks.py`
- [ ] `src/tasks/io_tasks.py`
- [ ] `src/tasks/memory_tasks.py`
- [ ] `src/core/scenario_registry.py`
- [ ] `scenarios/novel/__init__.py`
- [ ] `scenarios/novel/config.yaml`

---

**Document End** | Generated: 2026-02-05 | Status: Comprehensive Migration Plan Complete
