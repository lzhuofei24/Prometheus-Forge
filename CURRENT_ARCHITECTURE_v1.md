# Current Architecture Analysis v1.0 - Novel-Agent "As-Is" State

**Document Date**: 2026-02-05
**Codebase Size**: ~7,883 lines of Python
**Architecture Status**: Transitional (Legacy → LangGraph Migration In-Progress)

---

## Executive Summary

**Novel-Agent** is a sophisticated AI-powered novel creation system implementing a multi-agent architecture for automated chapter generation. The system has recently undergone partial architectural evolution from a legacy controller-based pattern to a **LangGraph-based state machine**, with persistent storage transitioning from filesystem to **SQLite + Redis**.

### Current Status
- ✅ **Functional**: Core workflow (chapter generation) operational
- ⚠️ **Transitional**: Dual architecture (legacy agents + new LangGraph) coexist
- 🔴 **Technical Debt**: Significant coupling, fragmented configuration, no test coverage

---

## 1. Project Structure & File Organization

```
novel-agent/
├── src/
│   ├── agents/                      # ⚠️ LEGACY - Being phased out
│   │   ├── novelist.py             # DEPRECATED: Unified novelist
│   │   ├── writer.py               # WriterAgent for scene generation
│   │   ├── editor.py               # ChiefEditor & Critic
│   │   ├── planner.py              # PlannerAgent for outlining
│   │   ├── builder.py              # WorldBuilder for context assembly
│   │   ├── orchestrator.py         # OrchestratorAgent for workflow decisions
│   │   └── reviewers/              # Specialized review agents
│   │       ├── character_checker.py
│   │       ├── plot_checker.py
│   │       ├── style_checker.py
│   │       └── team.py
│   │
│   ├── api/                         # ✅ FastAPI REST layer
│   │   ├── main.py                 # FastAPI app & routes setup
│   │   ├── models.py               # SQLAlchemy ORM models
│   │   ├── routers/                # API endpoint handlers
│   │   │   ├── novels.py           # Novel CRUD operations
│   │   │   ├── workflow.py         # Workflow execution endpoints
│   │   │   ├── prompts.py          # Prompt management
│   │   │   └── monitor.py          # Monitoring/health checks
│   │   ├── services/               # Business logic services
│   │   │   ├── novel_service.py    # Novel domain service
│   │   │   └── import_service.py   # Import/export operations
│   │   └── websocket.py            # WebSocket broadcast support
│   │
│   ├── core/                        # 🔧 Core infrastructure
│   │   ├── state.py                # AgentState & NovelState definitions
│   │   ├── state_manager.py        # Redis state persistence
│   │   ├── llm.py                  # LLM client (OpenAI compatible)
│   │   ├── prompt_loader.py        # Database-driven prompt loading
│   │   ├── prompt_manager.py       # Chroma-based prompt retrieval
│   │   ├── container.py            # Dependency injection (singleton)
│   │   ├── database.py             # SQLAlchemy setup
│   │   ├── db_service.py           # Sync DB service layer
│   │   ├── config.py               # Settings/configuration models
│   │   └── events.py               # Event types & audit logs
│   │
│   ├── rag/                         # 🔍 Retrieval-Augmented Generation
│   │   ├── indexer.py              # ChromaDB vector indexing
│   │   ├── retriever.py            # Semantic search retrieval
│   │   └── graph_store.py          # Knowledge graph storage
│   │
│   ├── workflow/                    # ✅ NEW: LangGraph architecture
│   │   ├── graph.py                # Workflow graph construction
│   │   ├── nodes.py                # Async node handlers
│   │   ├── state.py                # WorkflowState TypedDict
│   │   └── import_graph.py         # Import-specific graph
│   │
│   ├── workers/                     # 🔀 Handler-based execution (Bridge pattern)
│   │   ├── base.py                 # BaseAgentHandler template pattern
│   │   ├── handlers/               # Concrete handler implementations
│   │   │   ├── architect.py        # Outline generation handler
│   │   │   ├── writer.py           # Content writing handler
│   │   │   ├── critic.py           # Quality review handler
│   │   │   ├── censor.py           # Sensitivity checking handler
│   │   │   ├── media.py            # Image generation handler
│   │   │   └── knowledge.py        # Knowledge base updates handler
│   │   └── controller_tasks.py     # Task distribution logic
│   │
│   └── utils/                       # 🛠️ Utilities
│       ├── file_manager.py         # Filesystem operations
│       ├── json_utils.py           # JSON parsing helpers
│       └── novel_query.py          # Query helpers
│
├── config/
│   ├── settings.yaml               # Main configuration
│   └── prompts/                    # YAML-based prompt templates
│       ├── architect.yaml
│       ├── writer_builder.yaml
│       ├── critic.yaml
│       ├── censor.yaml
│       └── ... (12+ prompt files)
│
└── web/                            # Frontend (React/TypeScript)
```

---

## 2. Domain Model & Business Logic

### 2.1 Data Models

#### Novel Entity
```python
# src/api/models.py:Novel
class Novel:
    id: UUID [PK]
    title: String(255) [indexed]
    genre: String(100) [nullable]
    summary: Text [nullable]
    created_at: DateTime
    updated_at: DateTime

    # Relationships
    chapters: List[Chapter] (1-to-N)
    settings: List[NovelSetting] (1-to-N)
```

#### Chapter Entity
```python
# src/api/models.py:Chapter
class Chapter:
    id: UUID [PK]
    novel_id: UUID [FK → Novel, indexed]
    index: Integer [compound index with novel_id]
    title: String [nullable]
    status: Enum (PENDING|WRITING|REVISING|FINISHED|FAILED)
    active_draft_id: UUID [FK → ChapterDraft]
    latest_version: Integer
    created_at: DateTime
    updated_at: DateTime

    # Relationships
    drafts: List[ChapterDraft] (1-to-N, cascade delete)
```

#### ChapterDraft Entity (Multi-version Support)
```python
# src/api/models.py:ChapterDraft
class ChapterDraft:
    id: UUID [PK]
    chapter_id: UUID [FK → Chapter, indexed]
    version: Integer [indexed]
    content: Text [nullable]
    summary: Text [nullable]
    critique_data: JSON [nullable]  # { score, comments, actionable_feedback }
    is_active: Boolean [indexed]
    created_at: DateTime
```

#### NovelSetting Entity (Key-Value Store)
```python
# src/api/models.py:NovelSetting
class NovelSetting:
    id: UUID [PK]
    novel_id: UUID [FK → Novel]
    key: String(100)  # "bios", "world", "story_summary", etc.
    value: Text       # JSON serialized data
    created_at: DateTime
    updated_at: DateTime

    # Compound unique index: (novel_id, key)
```

### 2.2 Character Management (Embedded JSON Pattern)

**Current State**: Characters stored as JSON in `NovelSetting` with key="bios"

```python
# Character bio structure (inferred from handlers)
{
    "name": str,
    "personality": str,
    "appearance": str,
    "background": str
}
```

**Storage Pattern**:
- No dedicated Character table/entity
- Loaded via `DatabaseService.get_novel_global_settings(novel_id)`
- Formatted via duplicated `_format_bios()` helper methods across multiple files

**Access Pattern**:
```python
# Example from src/workers/handlers/architect.py:53
bios = db_service.get_novel_global_settings(novel_id, "bios")
for bio in bios:
    name = bio.get("name", "未知")          # Hardcoded field names
    personality = bio.get("personality", "")
    appearance = bio.get("appearance", "")
    background = bio.get("background", "")
```

---

## 3. Workflow Architecture & Data Flow

### 3.1 Chapter Generation Workflow (LangGraph-based)

```
┌─────────────────────────────────────────────────────────────┐
│                    START (User Request)                     │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ architect_node │  ← Generate scene-level outline
                    └────────┬───────┘    (JSON with scenes[])
                             │
                             ▼
                    ┌────────────────┐
                    │  writer_node   │  ← Generate content per scene
                    └────────┬───────┘    (scene_id loop)
                             │
                             ▼
                    ┌────────────────┐
                    │  censor_node   │  ← Check sensitivity
                    └────────┬───────┘
                             │
                ┌────────────┴────────────┐
                │                         │
            [BLOCKED]                 [PASS]
                │                         │
                ▼                         ▼
              END                  ┌────────────────┐
        (status=blocked)           │  critic_node   │  ← Review & score (0-100)
                                   └────────┬───────┘
                                            │
                        ┌───────────────────┼───────────────────┐
                        │                   │                   │
                  [score ≥ 75]      [score < 75 &       [revision_count ≥ 3]
                                   revision_count < 3]
                        │                   │                   │
                        ▼                   ▼                   ▼
                 ┌────────────┐      ┌──────────┐            END
                 │ media_node │      │ REVISION │      (status=failed)
                 └──────┬─────┘      └────┬─────┘
                        │                 │
                        ▼                 │
                       END     ───────────┘
                (status=completed)  (Loop back to writer_node
                                     with feedback, revision_count++)
```

### 3.2 State Management (Hybrid: Redis + SQLite)

#### Temporary State (Redis)
```python
# StateManager uses Redis hash: workflow:{workflow_id}:state
{
    "novel_name": str,
    "chapter_num": int,
    "outline": JSON string of scenes,     # Intermediate data
    "draft_content": str,                 # Draft in progress
    "critique_score": int,                # Latest score
    "critique_comments": str,             # Review feedback
    "revision_count": int,                # Retry counter
    "is_sensitive": bool,                 # Censor flag
    "censor_reason": str,                 # Block reason
    "status": "processing|completed|failed|blocked"
}
```

**Data Type Issue**: All values stored as strings in Redis, requiring type conversion

#### Persistent State (SQLite Database)
- **ChapterDraft**: Final approved content + critique metadata
- **PendingWrite**: Awaiting user approval (write_type: outline|content)
- **NovelSetting**: Global settings (bios, world, story_summary)

### 3.3 Request Flow

```
POST /workflow/generate
  │
  ├─→ [1] API Layer (routers/workflow.py)
  │    └─→ Request validation & mapping
  │
  ├─→ [2] Dispatcher.dispatch(workflow_type)
  │    └─→ Submits async task
  │
  ├─→ [3] main_graph.py: run_workflow()
  │    ├─→ Initialize WorkflowState
  │    ├─→ Create LangGraph instance
  │    └─→ Iterate nodes: astream(initial_state)
  │         │
  │         ├─→ [NODE] architect_node
  │         │    └─→ ArchitectHandler._process()
  │         │         ├─→ Load novel + character settings via DatabaseService
  │         │         ├─→ resolve_prompt("architect", workflow_type)
  │         │         ├─→ LLMClient.chat() → outline JSON
  │         │         └─→ StateManager.update_state()
  │         │
  │         ├─→ [NODE] writer_node
  │         │    └─→ WriterHandler._process()
  │         │         ├─→ Parse scenes from outline
  │         │         ├─→ Loop: generate each scene with context
  │         │         └─→ StateManager.update_state()
  │         │
  │         ├─→ [NODE] censor_node
  │         │    └─→ CensorHandler._process()
  │         │         ├─→ Check content sensitivity
  │         │         └─→ Set is_sensitive flag
  │         │
  │         ├─→ [NODE] critic_node
  │         │    └─→ CriticHandler._process()
  │         │         ├─→ Score content (0-100)
  │         │         ├─→ Decision routing logic
  │         │         └─→ Set revision_count
  │         │
  │         └─→ [NODE] media_node (conditional)
  │              └─→ MediaHandler._process()
  │                   └─→ Generate chapter images
  │
  └─→ [4] Finalization
       ├─→ Persist ChapterDraft to DB
       ├─→ Update Chapter.active_draft_id
       └─→ Send WebSocket notification
```

---

## 4. Technical Debt & Anti-Patterns

### 4.1 🔴 CRITICAL: Hardcoded Prompts

**Location**: `src/agents/novelist.py:33-41`

```python
# Inline string prompts (DEPRECATED but still active)
outline_prompt = (
    f"请为小说《{novel_name}》的第{chapter_num}章生成详细大纲。\n\n"
    f"{reference_context}\n\n"
    "请生成一个详细的大纲，包括：\n"
    "1. 章节标题...\n"
    "2. 主要情节点...\n"
    # ... hardcoded instruction text
)
```

**Impact**:
- Prompt changes require code deployment
- No A/B testing capability
- Difficult to version control prompt evolution
- Inconsistent with database-driven prompt system

### 4.2 🔴 CRITICAL: Tight Coupling - Model & Provider

**Location**: `src/agents/editor.py:167`, `src/core/llm.py`

```python
# Hardcoded model switches scattered across codebase
self.llm_client.switch_model(
    "deepseek/deepseek-chat",          # Model name
    "openrouter",                       # Provider
    "https://openrouter.ai/api/v1"     # Base URL
)
```

**Locations**:
- `src/agents/editor.py:167`
- `src/agents/novelist.py` (multiple places)
- `src/workers/handlers/critic.py`

**Impact**:
- Provider switching requires code changes
- Configuration scattered across multiple files
- No single source of truth for LLM configuration
- Difficult to implement fallback strategies

### 4.3 🔴 CRITICAL: Character Data Coupling

**Problem 1: Hardcoded Schema in Multiple Locations**

```python
# DUPLICATED across 4 files:
# - src/agents/builder.py:43
# - src/workers/handlers/architect.py:53
# - src/workers/handlers/critic.py:58
# - src/workers/handlers/writer.py

for bio in bios:
    name = bio.get("name", "未知")          # Hardcoded field
    personality = bio.get("personality", "")
    appearance = bio.get("appearance", "")
    background = bio.get("background", "")
```

**Problem 2: Direct Embedding in Prompts**

```python
# src/agents/builder.py:43-44
character_bios_text = self._format_bios(bios)
base_context = f"...## 人物设定：\n{character_bios_text}\n\n..."
```

**Impact**:
- Adding new character fields requires changes in 4+ files
- No character service layer or repository pattern
- Business logic mixed with data access
- Difficult to extend character attributes

### 4.4 🟠 MEDIUM: Dual Architecture Complexity

**Current State**: Two parallel systems coexist

| Aspect | Legacy (agents/) | New (workflow/) | Status |
|--------|------------------|-----------------|--------|
| Pattern | Class-based agents | LangGraph nodes | ⚠️ Mixed |
| State | In-memory / Filesystem | Redis Checkpointer | ⚠️ Mixed |
| Async | Mixed sync/async | Full async | ⚠️ Transitional |
| Entry Point | Direct API calls | Graph execution | ✅ Migrated |

**Evidence**:
- `src/agents/novelist.py:16` - Deprecated warning but still referenced
- `src/workers/handlers/` - Bridge pattern connecting old to new
- State management split between `state_manager.py` and legacy patterns

**Impact**:
- Increased cognitive load for developers
- Duplicate logic in legacy and new systems
- Maintenance burden of two codebases
- Risk of inconsistent behavior

### 4.5 🟠 MEDIUM: Prompt Resolution Fragmentation

**Three Different Implementations**:

```python
# Version 1: src/agents/novelist.py:9
def resolve_prompt(key: str, workflow_type: str = "") -> str:
    # Implementation A

# Version 2: src/agents/planner.py:34
def resolve_prompt(key: str, workflow_type: str = "") -> str:
    # Implementation B (slightly different)

# Version 3: src/workers/handlers/architect.py
# Uses core/prompt_loader.py (correct approach)
```

**Impact**:
- Inconsistent prompt loading behavior
- Bug fixes need to be applied to multiple places
- No single source of truth

### 4.6 🟠 MEDIUM: Context Assembly Without Token Limits

**Location**: `src/agents/builder.py:41-100`

```python
# WorldBuilder._build_context() loads:
# - All character bios (unbounded)
# - Entire world setting text (unbounded)
# - Full story summary (unbounded)
# - Last 3 chapters (complete content, ~5000 tokens each)
# - 15+ previous chapter outlines (~200 tokens each)
# Total: NO token limit checking before assembly
```

**Risk**:
- Context window overflow causes runtime failures
- No graceful degradation strategy
- No token counting before LLM call
- Can exceed model's maximum context length (e.g., 8K, 16K, 32K)

### 4.7 🟠 MEDIUM: State Synchronization Issues

**Type Inconsistencies**:

```python
# Redis state (StateManager) - All strings
{
    "critique_score": "75",        # String
    "revision_count": "1"          # String
}

# Database state (ChapterDraft.critique_data) - Typed JSON
{
    "score": 75,                   # Integer
    "comments": "..."              # String
}
```

**Synchronization Gap**:
- Redis state = source of truth during workflow
- Database = source of truth after completion
- If workflow crashes mid-execution, no clear recovery path
- revision_count exists in 3 places (WorkflowState, Redis, ChapterDraft JSON)

### 4.8 🟡 LOW: Configuration Fragmentation

**Settings Scattered Across**:

```yaml
# config/settings.yaml: Global LLM config
llm:
  provider: "openrouter"
  model_name: "deepseek/deepseek-chat"
  api_base: "https://openrouter.ai/api/v1"

# config/settings.yaml: Agent-specific overrides
agents:
  architect:
    temperature: 0.7
  writer:
    temperature: 0.9

# Database: prompt_templates table
# Stores prompts with workflow_type variants

# Code: Hardcoded overrides
# src/agents/editor.py - .switch_model() calls
```

**Impact**:
- No single source of truth
- Difficult to understand actual runtime configuration
- Risk of conflicts between config sources

### 4.9 🟡 LOW: Code Duplication

**Duplicated Logic**:

| Function | Occurrences | Files |
|----------|-------------|-------|
| `resolve_prompt()` | 3 | novelist.py, planner.py, handlers/* |
| `_build_context()` | 4 | builder.py, architect.py, critic.py, orchestrator.py |
| `_format_bios()` | 3 | builder.py, architect.py, critic.py |
| JSON parsing helpers | 5+ | Multiple agents and handlers |

**Maintenance Cost**: Bug fixes require changes in multiple locations

---

## 5. Component Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                      Container (Singleton)                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ redis_client, llm_client, state_manager, db_session │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
  ┌──────────┐ ┌──────────┐ ┌──────────────┐
  │ LLMClient│ │StateManager│ │DatabaseService│
  │(Singleton)│ │  (Redis)  │ │  (SQLite)    │
  └─────┬────┘ └─────┬────┘ └──────┬───────┘
        │            │              │
        │            │              │
        └────────────┴──────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
  ┌──────────┐            ┌──────────────┐
  │ Handlers │            │Legacy Agents │
  │(workers/)│            │  (agents/)   │
  └────┬─────┘            └──────┬───────┘
       │                         │
       └─────────┬───────────────┘
                 │
                 ▼
          ┌────────────┐
          │ LangGraph  │
          │   Nodes    │
          └────────────┘
```

### Key Dependencies

**LLMClient** (Singleton)
- Used by: All handlers, all legacy agents
- Configuration: `settings.yaml` + code overrides
- Cache: Redis-based response cache
- Provider: OpenAI-compatible API (OpenRouter, SiliconFlow)

**StateManager** (Redis)
- Used by: Handlers, Dispatcher, Workflow nodes
- Keys: `workflow:{workflow_id}:state`
- Pattern: Hash structure for state, List for audit logs

**DatabaseService** (Sync wrapper)
- Used by: Handlers, API services, Legacy agents
- Session: SQLAlchemy SessionLocal (blocking)
- Models: Novel, Chapter, ChapterDraft, NovelSetting, PendingWrite

**FileManager** (ProjectManager)
- Used by: Legacy agents, some handlers
- Path: From `settings.yaml` (workspace)
- Purpose: Filesystem-based chapter storage (legacy)

---

## 6. Prompt Management System

### 6.1 Current Architecture

**Database Schema**:
```sql
CREATE TABLE prompt_templates (
    id INTEGER PRIMARY KEY,
    key VARCHAR(50) NOT NULL,        -- "architect", "writer_builder", etc.
    workflow_type VARCHAR(50),       -- "" (default) or specific type
    content TEXT NOT NULL,           -- Full YAML prompt content
    description VARCHAR(200),
    is_active BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(key, workflow_type)
);
```

**Resolution Flow**:
```python
# src/core/prompt_loader.py:resolve_prompt()
resolve_prompt("architect", workflow_type="generate_chapter")
  ├─→ Query: SELECT content FROM prompt_templates
  │    WHERE key="architect" AND workflow_type="generate_chapter"
  ├─→ If not found: fallback to workflow_type=""
  └─→ Return YAML content (parse at runtime)
```

### 6.2 Issues

| Issue | Severity | Description |
|-------|----------|-------------|
| No versioning | 🟠 Medium | Can't rollback prompt changes |
| No A/B testing | 🟠 Medium | Can't run multiple variants |
| Runtime YAML parsing | 🟡 Low | Performance overhead |
| No analytics | 🟡 Low | Can't track which prompts were used |
| No validation | 🟠 Medium | Invalid prompts only fail at runtime |

### 6.3 Variable Substitution (Brittle)

```python
# src/core/prompt_loader.py:93-101
def format_prompt_template(template: str, **kwargs: object) -> str:
    out = template
    for k, v in kwargs.items():
        out = out.replace("{" + k + "}", str(v) if v is not None else "")
    return out
```

**Problems**:
- Missing variables silently become empty strings
- No error on typos in placeholder names (`{novle_name}`)
- No typing for expected placeholders
- No validation that all required variables provided

---

## 7. Integration Points & External Dependencies

### 7.1 LLM Integration

**Providers**:
- Primary: OpenRouter (`https://openrouter.ai/api/v1`)
- Secondary: SiliconFlow, OpenAI (compatible)

**Models**:
- Default: `deepseek/deepseek-chat`
- Alternative: Claude, GPT-4 (configurable)

**Caching**:
- Redis-based LLM response cache via `CacheService`
- Key pattern: `llm_cache:{hash(prompt)}`

### 7.2 Vector Search (RAG)

**Engine**: ChromaDB (Chroma)
- Collection: Novel-specific collections
- Embedding Model: `BAAI/bge-small-zh-v1.5` (Chinese-optimized)
- Purpose: Retrieval for context assembly, semantic search

**Usage**:
- `src/rag/indexer.py` - Index creation
- `src/rag/retriever.py` - Semantic search
- `src/core/prompt_manager.py` - Prompt retrieval from vector store

### 7.3 Task Queue

**System**: Redis lists (manual polling)
- Pattern: Push tasks to `queue:{task_type}`, handlers poll
- Limitation: No distributed task queue (no Celery equivalent)
- Concurrency: Single-threaded polling

### 7.4 Message Bus

**Mechanism**: Redis pub/sub + WebSocket
- Events: `WORKFLOW_STARTED`, `TASK_STARTED`, `TASK_COMPLETED`, `TASK_FAILED`
- Publisher: Workflow nodes, handlers
- Consumers: Frontend (WebSocket), monitoring dashboards

---

## 8. Strengths of Current System

✅ **LangGraph Migration Started**: Modern async-first workflow orchestration
✅ **Multi-version Chapters**: ChapterDraft versioning allows rollback
✅ **Approval Workflow**: PendingWrite table enables human-in-the-loop
✅ **Audit Logging**: AuditLogEntry + event stream for traceability
✅ **Configuration Management**: YAML + Pydantic settings (partially)
✅ **RAG Foundation**: ChromaDB + semantic retriever in place
✅ **Modular Handlers**: BaseAgentHandler template pattern
✅ **API-Driven**: FastAPI with async/await throughout API layer

---

## 9. Summary: AS-IS State Assessment

| Dimension | Current State | Key Issues |
|-----------|---------------|-----------|
| **Architecture** | Dual (LangGraph + legacy agents) | Incomplete migration, complexity |
| **Domain Model** | Novel → Chapter → Draft (SQLAlchemy) | Characters embedded in JSON, no service layer |
| **Prompts** | Database + YAML + inline strings | Fragmented, no versioning, hardcoded |
| **State Management** | Redis (temp) + SQLite (persistent) | Type inconsistencies, sync gaps |
| **Configuration** | Partially externalized (settings.yaml) | Hardcoded endpoints, scattered overrides |
| **LLM Integration** | OpenAI-compatible client | Provider switching requires code changes |
| **Context Assembly** | Retrieval from DB + ChromaDB | No token limit enforcement, overflow risk |
| **Testing** | None | Zero test coverage, unknown reliability |
| **Documentation** | Minimal (Chinese comments) | Hard to maintain, no architecture docs |
| **Scalability** | Single-threaded polling | Limited concurrency, no Celery |

---

## 10. Critical Path for Modernization

**Priority 1 (P1) - System Stability**:
1. Complete LangGraph migration (retire legacy agents)
2. Consolidate prompt management (single source of truth)
3. Fix state synchronization (choose Redis XOR Database as primary)

**Priority 2 (P2) - Extensibility**:
4. Extract Character entity & service layer
5. Implement token counting & context window management
6. Add comprehensive test suite

**Priority 3 (P3) - Operational Excellence**:
7. Unified configuration system (eliminate hardcoded values)
8. Implement distributed task queue (Celery)
9. Add observability (structured logging, metrics, tracing)

---

**Document End** | Generated: 2026-02-05 | Status: Comprehensive Analysis Complete
