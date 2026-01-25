# 项目优化方案路线图

## 一、性能优化

### 1.1 数据库查询优化

**问题:**
- `get_chapter_outline` 和 `get_chapter_content` 存在多次数据库往返
- `get_chapter_by_novel_and_index` 每次都加载所有 drafts（selectinload）

**方案:**
```python
# 优化1: 合并查询，使用 JOIN 一次性获取
@staticmethod
def get_chapter_with_active_draft(novel_id: str, chapter_index: int):
    with SessionLocal() as db:
        return db.execute(
            select(Chapter, ChapterDraft)
            .join(ChapterDraft, and_(
                ChapterDraft.chapter_id == Chapter.id,
                ChapterDraft.is_active == True
            ))
            .where(and_(
                Chapter.novel_id == novel_id,
                Chapter.index == chapter_index
            ))
        ).first()

# 优化2: 批量查询多个章节
@staticmethod
def get_chapters_with_drafts(novel_id: str, chapter_indices: List[int]):
    with SessionLocal() as db:
        return db.execute(
            select(Chapter, ChapterDraft)
            .join(ChapterDraft, and_(
                ChapterDraft.chapter_id == Chapter.id,
                ChapterDraft.is_active == True
            ))
            .where(and_(
                Chapter.novel_id == novel_id,
                Chapter.index.in_(chapter_indices)
            ))
        ).all()
```

**预期提升:** 查询时间减少 50-70%

### 1.2 Redis 缓存策略

**问题:**
- 频繁查询的章节内容没有缓存
- 全局设置（bios.json, world.md）每次都从文件读取

**方案:**
```python
# 缓存章节内容（TTL: 1小时）
def get_chapter_content_cached(novel_id: str, chapter_index: int):
    cache_key = f"chapter:{novel_id}:{chapter_index}:content"
    cached = redis_client.get(cache_key)
    if cached:
        return cached
    
    content = DatabaseService.get_chapter_content(novel_id, chapter_index)
    if content:
        redis_client.setex(cache_key, 3600, content)
    return content

# 缓存全局设置（TTL: 5分钟）
def get_novel_settings_cached(novel_name: str):
    cache_key = f"novel:{novel_name}:settings"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    settings = load_settings_from_file(novel_name)
    redis_client.setex(cache_key, 300, json.dumps(settings))
    return settings
```

**预期提升:** 重复查询响应时间减少 80-90%

### 1.3 LLM 响应缓存

**问题:**
- 相同 prompt 重复调用 LLM，浪费 token 和成本

**方案:**
```python
# 使用 prompt hash 作为缓存键
def chat_with_cache(messages, temperature=0.7):
    prompt_hash = hashlib.md5(
        json.dumps(messages, sort_keys=True).encode()
    ).hexdigest()
    cache_key = f"llm:response:{prompt_hash}:{temperature}"
    
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    response = llm_client.chat(messages, temperature)
    redis_client.setex(cache_key, 86400, json.dumps(response))  # 24小时
    return response
```

**预期提升:** 重复请求成本减少 100%，响应时间减少 95%

### 1.4 批量操作优化

**问题:**
- `list_chapters` 逐个查询章节内容
- KnowledgeHandler 逐个生成章节摘要

**方案:**
```python
# 批量获取章节内容
def get_chapters_content_batch(novel_id: str, chapter_indices: List[int]):
    chapters = DatabaseService.list_chapters(novel_id)
    target_chapters = [c for c in chapters if c.index in chapter_indices]
    
    # 一次性 JOIN 查询所有 active drafts
    with SessionLocal() as db:
        drafts = db.execute(
            select(ChapterDraft)
            .where(and_(
                ChapterDraft.chapter_id.in_([c.id for c in target_chapters]),
                ChapterDraft.is_active == True
            ))
        ).all()
    
    # 构建映射
    draft_map = {d.chapter_id: d for d in drafts}
    return {c.index: draft_map.get(c.id).content for c in target_chapters if c.id in draft_map}
```

**预期提升:** 批量操作时间减少 60-80%

## 二、架构优化

### 2.1 Dispatcher 任务调度实现

**问题:**
- Dispatcher 目前只记录日志，不实际调度任务
- 需要实现中央控制器逻辑

**方案:**
```python
class Dispatcher:
    def _handle_outline_generated(self, workflow_id: str, data: Dict[str, Any]):
        outline = data.get("outline")
        self.state_manager.update_state(workflow_id, {"outline": outline})
        
        # 自动调度下一个任务
        from src.workers.tasks_new import task_write_content
        task_write_content.delay(workflow_id)
        
    def _handle_critique_completed(self, workflow_id: str, data: Dict[str, Any]):
        score = data.get("score", 0)
        passed = data.get("passed", False)
        state = self.state_manager.get_state(workflow_id)
        revision_count = state.get("revision_count", 0)
        
        if passed or revision_count >= 3:
            # 通过或达到最大重试次数 → 完成
            from src.workers.tasks_new import task_update_knowledge
            task_update_knowledge.delay(workflow_id)
        else:
            # 未通过 → 重写
            from src.workers.tasks_new import task_revise_content
            task_revise_content.delay(workflow_id, data.get("advice", ""))
```

### 2.2 任务优先级队列

**问题:**
- 所有任务使用相同优先级
- 用户触发的任务应该优先于后台任务

**方案:**
```python
# 在 celery_config.py 中定义优先级队列
celery_app.conf.task_routes = {
    'architect.*': {'queue': 'architect_pending', 'priority': 5},
    'writer.*': {'queue': 'writer_pending', 'priority': 5},
    'critic.*': {'queue': 'critic_pending', 'priority': 4},
    'media.*': {'queue': 'media_pending', 'priority': 3},
    'knowledge.*': {'queue': 'knowledge_pending', 'priority': 2},
}

# Worker 启动时指定优先级
celery -A src.workers.tasks_new worker -Q architect_pending -n architect@%h --max-priority=10
```

### 2.3 任务去重机制

**问题:**
- 相同工作流可能被重复提交
- 没有幂等性保证

**方案:**
```python
# 使用 Redis SET 实现分布式锁
def ensure_workflow_not_running(workflow_id: str) -> bool:
    lock_key = f"workflow:lock:{workflow_id}"
    if redis_client.set(lock_key, "1", nx=True, ex=3600):
        return True
    return False

# 在任务开始时检查
@celery_app.task
def task_generate_outline(workflow_id: str, ...):
    if not ensure_workflow_not_running(workflow_id):
        logger.warning(f"Workflow {workflow_id} already running")
        return {"status": "skipped", "reason": "already_running"}
    # ... 执行任务
```

## 三、错误处理和可靠性

### 3.1 重试策略优化

**问题:**
- 当前重试使用固定延迟
- 没有区分可重试和不可重试的错误

**方案:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((APIConnectionError, APIError, httpx.HTTPError)),
    reraise=True
)
def chat_with_retry(messages, ...):
    # 自动重试逻辑
    pass
```

### 3.2 断路器模式

**问题:**
- API 持续失败时仍会不断重试
- 没有降级策略

**方案:**
```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
def call_llm_api(messages):
    # 连续失败5次后，60秒内直接返回错误，不调用API
    return llm_client.chat(messages)

def chat_with_fallback(messages):
    try:
        return call_llm_api(messages)
    except CircuitBreakerError:
        # 降级：返回缓存或默认响应
        return get_cached_response(messages) or "服务暂时不可用，请稍后重试"
```

### 3.3 任务超时和取消

**问题:**
- 长时间运行的任务无法取消
- 没有超时保护

**方案:**
```python
# Celery 任务超时配置
@celery_app.task(
    time_limit=600,  # 硬超时：10分钟
    soft_time_limit=540  # 软超时：9分钟（可以捕获异常）
)
def task_write_content(workflow_id: str, ...):
    try:
        # 执行任务
        pass
    except SoftTimeLimitExceeded:
        # 保存进度，标记为可恢复
        state_manager.update_state(workflow_id, {"status": "timeout", "checkpoint": ...})
        raise
```

## 四、监控和可观测性

### 4.1 结构化日志

**问题:**
- 日志格式不统一
- 缺少 trace_id 关联

**方案:**
```python
import structlog

logger = structlog.get_logger()
logger = logger.bind(workflow_id=workflow_id, agent="writer")

# 所有日志自动包含 workflow_id
logger.info("task_started", chapter_num=chapter_num)
logger.error("task_failed", error=str(e), exc_info=True)
```

### 4.2 指标收集

**问题:**
- 缺少性能指标（P50, P95, P99 延迟）
- 没有错误率统计

**方案:**
```python
from prometheus_client import Counter, Histogram, Gauge

task_duration = Histogram('task_duration_seconds', 'Task duration', ['agent', 'status'])
task_count = Counter('tasks_total', 'Total tasks', ['agent', 'status'])
active_workflows = Gauge('active_workflows', 'Active workflows count')

# 在任务中记录
@task_duration.labels(agent='writer', status='success').time()
def task_write_content(...):
    task_count.labels(agent='writer', status='success').inc()
    # ...
```

### 4.3 分布式追踪

**问题:**
- 无法追踪跨 agent 的完整请求链路

**方案:**
```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger import JaegerExporter

tracer = trace.get_tracer(__name__)

def task_write_content(workflow_id: str, ...):
    with tracer.start_as_current_span("writer.task") as span:
        span.set_attribute("workflow_id", workflow_id)
        span.set_attribute("chapter_num", chapter_num)
        # 执行任务
        with tracer.start_as_current_span("llm.call"):
            response = llm_client.chat(...)
```

## 五、代码质量

### 5.1 类型注解完善

**问题:**
- 部分函数缺少类型注解
- 返回类型不明确

**方案:**
```python
from typing import TypedDict, Literal

class WorkflowState(TypedDict):
    novel_name: str
    chapter_num: int
    status: Literal["started", "writing", "reviewing", "finished"]
    outline: Optional[str]
    draft_content: Optional[str]

def get_state(workflow_id: str) -> WorkflowState:
    # ...
```

### 5.2 配置管理优化

**问题:**
- 配置分散在多个地方（.env, settings.yaml, 代码）
- 缺少配置验证

**方案:**
```python
from pydantic_settings import BaseSettings

class AppSettings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379
    database_url: str
    openrouter_api_key: str
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = AppSettings()  # 自动验证和加载
```

### 5.3 依赖注入

**问题:**
- 全局变量和单例模式
- 难以测试和替换

**方案:**
```python
from dependency_injector import containers, providers

class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration()
    
    redis = providers.Singleton(
        redis.Redis,
        host=config.redis.host,
        port=config.redis.port
    )
    
    state_manager = providers.Factory(
        StateManager,
        redis_client=redis
    )
    
    llm_client = providers.Singleton(
        LLMClient,
        api_key=config.openrouter.api_key
    )

container = ApplicationContainer()
```

## 六、安全性

### 6.1 API 认证

**问题:**
- FastAPI 接口没有认证
- 任何人都可以触发工作流

**方案:**
```python
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

@router.post("/workflow/start")
async def start_workflow(..., api_key: str = Depends(verify_api_key)):
    # ...
```

### 6.2 输入验证增强

**问题:**
- 缺少对 novel_name 和 chapter_num 的严格验证
- 可能被注入恶意内容

**方案:**
```python
from pydantic import Field, validator

class WorkflowStartRequest(BaseModel):
    novel_name: str = Field(..., min_length=1, max_length=100, regex="^[a-zA-Z0-9\u4e00-\u9fa5_\\-]+$")
    chapter_num: int = Field(..., ge=1, le=9999)
    
    @validator('novel_name')
    def validate_novel_name(cls, v):
        # 防止路径遍历
        if '..' in v or '/' in v or '\\' in v:
            raise ValueError("Invalid novel name")
        return v
```

### 6.3 敏感信息脱敏

**问题:**
- 日志中可能包含 API Key
- 错误信息可能泄露内部结构

**方案:**
```python
def sanitize_log_message(message: str) -> str:
    # 脱敏 API Key
    message = re.sub(r'sk-[a-zA-Z0-9]{20,}', 'sk-***', message)
    # 脱敏其他敏感信息
    return message

logger.info(sanitize_log_message(f"API Key: {api_key}"))
```

## 七、数据库优化（补充）

### 7.1 连接池优化

**问题:**
- 每次查询都创建新连接
- 没有连接池管理

**方案:**
```python
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # 自动重连
    pool_recycle=3600  # 1小时回收连接
)
```

### 7.2 读写分离（未来）

**问题:**
- 所有操作都在主库
- 读操作可能阻塞写操作

**方案:**
```python
# 主库（写）
write_engine = create_engine(WRITE_DATABASE_URL)
# 从库（读）
read_engine = create_engine(READ_DATABASE_URL)

class DatabaseService:
    @staticmethod
    def get_chapter_content(novel_id: str, chapter_index: int):
        # 使用读库
        with SessionLocal(bind=read_engine) as db:
            # ...
    
    @staticmethod
    def save_content(novel_id: str, chapter_index: int, content: str):
        # 使用写库
        with SessionLocal(bind=write_engine) as db:
            # ...
```

### 7.3 数据库索引优化（补充）

**方案:**
```sql
-- 添加全文搜索索引（SQLite FTS5）
CREATE VIRTUAL TABLE chapter_content_fts USING fts5(
    chapter_id, content, content='chapter_drafts', content_rowid='id'
);

-- 添加复合索引优化常见查询
CREATE INDEX idx_draft_chapter_active_created ON chapter_drafts(chapter_id, is_active, created_at);
CREATE INDEX idx_chapter_novel_status_updated ON chapters(novel_id, status, updated_at);
```

## 八、前端优化

### 8.1 请求去重

**问题:**
- 用户快速点击可能触发重复请求
- 没有请求取消机制

**方案:**
```typescript
// 使用 AbortController
const abortController = new AbortController();

const startWorkflow = async (novelName: string, chapterNum: number) => {
  // 取消之前的请求
  abortController.abort();
  
  const newController = new AbortController();
  abortController = newController;
  
  try {
    await workflowApi.start({ novel_name: novelName, chapter_num: chapterNum }, {
      signal: newController.signal
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      console.log('Request cancelled');
      return;
    }
    throw error;
  }
};
```

### 8.2 虚拟滚动

**问题:**
- 工作流追踪列表可能很长
- 渲染所有项目导致性能问题

**方案:**
```typescript
import { useVirtualizer } from '@tanstack/react-virtual';

const VirtualizedTraceList = ({ logs }) => {
  const parentRef = useRef<HTMLDivElement>(null);
  
  const virtualizer = useVirtualizer({
    count: logs.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 80,
    overscan: 5,
  });
  
  return (
    <div ref={parentRef} style={{ height: '600px', overflow: 'auto' }}>
      {virtualizer.getVirtualItems().map(virtualItem => (
        <div key={virtualItem.key} style={{ height: virtualItem.size }}>
          {logs[virtualItem.index]}
        </div>
      ))}
    </div>
  );
};
```

### 8.3 乐观更新

**问题:**
- 用户操作需要等待服务器响应
- 体验不够流畅

**方案:**
```typescript
const { mutate } = useMutation({
  mutationFn: startWorkflow,
  onMutate: async (newWorkflow) => {
    // 取消正在进行的查询
    await queryClient.cancelQueries(['workflows']);
    
    // 快照当前值
    const previous = queryClient.getQueryData(['workflows']);
    
    // 乐观更新
    queryClient.setQueryData(['workflows'], (old) => [
      ...old,
      { ...newWorkflow, status: 'pending', id: Date.now() }
    ]);
    
    return { previous };
  },
  onError: (err, newWorkflow, context) => {
    // 回滚
    queryClient.setQueryData(['workflows'], context.previous);
  },
});
```

## 九、部署和运维

### 9.1 健康检查增强

**问题:**
- 当前健康检查过于简单
- 没有检查依赖服务状态

**方案:**
```python
@router.get("/health")
async def health_check():
    checks = {
        "api": "ok",
        "redis": check_redis(),
        "database": check_database(),
        "celery": check_celery_workers(),
    }
    
    status_code = 200 if all(v == "ok" for v in checks.values()) else 503
    return JSONResponse(content=checks, status_code=status_code)
```

### 9.2 优雅关闭

**问题:**
- 服务关闭时可能丢失正在处理的任务

**方案:**
```python
import signal
import atexit

def graceful_shutdown():
    # 停止接收新任务
    celery_app.control.pool_shutdown()
    # 等待当前任务完成（最多30秒）
    time.sleep(30)
    # 关闭连接
    redis_client.close()

signal.signal(signal.SIGTERM, graceful_shutdown)
atexit.register(graceful_shutdown)
```

### 9.3 配置热重载

**问题:**
- 修改配置需要重启服务

**方案:**
```python
@router.post("/admin/reload-config")
async def reload_config():
    # 重新加载配置
    config = Settings.load_from_yaml("config/settings.yaml")
    # 更新全局配置
    app.state.config = config
    return {"status": "reloaded"}
```

## 十、成本优化

### 10.1 Token 使用优化

**问题:**
- 每次查询都发送完整上下文
- 没有压缩或摘要机制

**方案:**
```python
def compress_context(context: str, max_tokens: int = 2000) -> str:
    """压缩上下文，保留关键信息"""
    if estimate_tokens(context) <= max_tokens:
        return context
    
    # 使用 LLM 生成摘要
    summary = llm_client.chat([
        {"role": "system", "content": "请将以下内容压缩为关键信息，保留人物、地点、重要事件"},
        {"role": "user", "content": context}
    ], max_tokens=max_tokens)
    return summary
```

### 10.2 批量处理优化

**问题:**
- 多个章节逐个处理，无法利用批量 API

**方案:**
```python
# 如果 API 支持批量，合并请求
def batch_generate_outlines(novel_name: str, chapter_nums: List[int]):
    prompts = [build_outline_prompt(novel_name, ch) for ch in chapter_nums]
    # 使用批量 API（如果支持）
    responses = llm_client.batch_chat(prompts)
    return responses
```

## 优先级建议

### 高优先级（立即实施）
1. ✅ 数据库查询优化（1.1）
2. ✅ Redis 缓存策略（1.2）
3. ✅ Dispatcher 任务调度实现（2.1）
4. ✅ 错误处理和重试优化（3.1）

### 中优先级（1-2周内）
5. LLM 响应缓存（1.3）
6. 任务优先级队列（2.2）
7. 结构化日志（4.1）
8. API 认证（6.1）

### 低优先级（长期优化）
9. 分布式追踪（4.3）
10. 读写分离（7.2）
11. 配置热重载（9.3）
