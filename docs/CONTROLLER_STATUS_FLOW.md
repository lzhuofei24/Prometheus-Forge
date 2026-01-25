# Controller 在线状态：前端为何显示 Offline，相关代码在哪

## 1. 前端：如何决定显示「在线 / 离线」

**文件**: `web/src/pages/ControllerDashboard.tsx`

```tsx
// 第 21-28 行
const queueLengths = stats?.stats?.queues || {};
const workersList = stats?.stats?.workers?.list || [];
const agentTasks = stats?.stats?.agent_tasks || {};

// 优先用 Redis 心跳字段；无该字段时再看 workers 里的 Controller
const controllerWorker = workersList.find((w: any) => w.name === 'Controller');
const controllerActive =
  (stats?.stats?.controller as { online?: boolean } | undefined)?.online === true ||
  controllerWorker?.status === 'online';
```

- **`controllerActive === true`** → 显示「🚀 Central Cortex Online」
- **`controllerActive === false`** → 显示「⚠️ Controller Offline - Routing Halted」，并展示你看到的那段说明文案

也就是说：  
**只要 `stats.stats.controller.online !== true` 且 `controllerWorker?.status !== 'online'`，就会显示 Offline。**

说明文案本身在下面这段（第 128-138 行）：

```tsx
{!controllerActive && (
  <p className="text-sm text-zinc-400 mt-1 max-w-2xl">
    Controller Worker 负责消费<strong>所有节点的已处理队列</strong>
    （architect_completed、writer_completed、...），...
    请先启动该进程：... start_all_workers.bat ...
    celery -A src.workers.controller_tasks worker -n controller@%h -Q controller_pending ...
  </p>
)}
```

---

## 2. 后端：`controller.online` 从哪来（Redis 心跳）

**文件**: `src/api/routers/monitor.py`

在 `get_resources()` 里（约第 318-324 行）：

```python
# Controller 状态优先用 Redis 心跳（不依赖 inspect）
_controller_heartbeat_key = "system:controller:heartbeat"
try:
    controller_online = bool(redis_client.exists(_controller_heartbeat_key))
except Exception:
    controller_online = False
stats["controller"] = {"online": controller_online}
```

- 用的 Redis key：**`system:controller:heartbeat`**
- `redis_client`：`redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)`（第 10 行）
- 只要这个 key 存在，API 就会返回 `stats.controller.online == true`，前端在上面就会用这个值，从而显示在线。

所以：**前端显示 Offline，要么是没请求到 /monitor/resources，要么是请求到了但 `stats.controller.online` 不是 true，即 Redis 里没有 `system:controller:heartbeat`。**

---

## 3. 谁在写「心跳」：Controller 的 run_loop

**文件**: `src/core/controller.py`

常量（第 8-9 行）：

```python
HEARTBEAT_KEY = "system:controller:heartbeat"
HEARTBEAT_TTL = 30
```

在 `run_loop()` 里，每次循环开头写一次心跳（第 99-128 行）：

```python
def run_loop(self):
    self.running = True
    logger.info("🚀 Central Controller started, listening to completed queues...")

    while self.running:
        try:
            # 写入心跳，便于 API 通过 Redis 判定 Controller 在线
            try:
                self.redis.setex(HEARTBEAT_KEY, HEARTBEAT_TTL, str(time.time()))
            except Exception as e:
                logger.debug(f"Heartbeat write failed: {e}")

            result = self.redis.blpop(self.listen_queues, timeout=1)
            # ... 处理 result ...
```

- 心跳 key：同上，`system:controller:heartbeat`
- 用的 Redis 客户端：`self.redis`，在 Worker 里由 `_init_controller()` 创建（见下一节）
- 只有 **Controller 的 Celery Worker 正在跑这段 `run_loop()`** 时，这个 key 才会一直被刷新；一旦进程退出或卡在别处没进循环，约 30 秒后 key 过期，接口就会认为离线。

---

## 4. Controller 进程如何启动、用的哪个 Redis

**文件**: `src/workers/controller_tasks.py`

- Worker 准备就绪时自动发一次「跑 run_loop」的任务（第 14-23 行）：

```python
@worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    try:
        worker_name = os.environ.get('CELERY_WORKER_NAME', '')
        if 'controller' in worker_name.lower() or (sender and 'controller' in str(sender).lower()):
            logger.info("Controller worker ready, auto-starting loop...")
            task_run_controller_loop.delay()
    except Exception as e:
        logger.error(f"Failed to auto-start controller: {e}", exc_info=True)
```

- 跑循环的任务和 Controller 实例的 Redis（第 26-41、45-53 行）：

```python
def _init_controller():
    global _controller
    if _controller is None:
        settings = get_settings()
        state_manager = StateManager(
            redis_host=settings.redis_host,
            redis_port=settings.redis_port,
            redis_db=settings.redis_db
        )
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True
        )
        _controller = CentralController(state_manager, redis_client)
    return _controller

@celery_app.task(name="controller.run_loop", bind=True, time_limit=None)
def task_run_controller_loop(self):
    controller = _init_controller()
    logger.info("🚀 Starting Central Controller loop...")
    try:
        controller.run_loop()
    ...
```

也就是说：**写心跳的 Redis** 是 `get_settings()` 里的 `redis_host/redis_port/redis_db`，一般是 `localhost:6379/0`。  
**读心跳的 Redis** 是 monitor 里写死的 `localhost:6379/0`。  
两边必须是同一个 Redis，否则即使 Controller 在写心跳，API 也读不到，前端就会一直 Offline。

---

## 5. 整条链路总结（为何会显示 Offline）

1. **前端**  
   - 用 `stats?.stats?.controller?.online === true` 或 `controllerWorker?.status === 'online'` 得到 `controllerActive`。
   - 为 false 时显示「⚠️ Controller Offline - Routing Halted」和那段说明。

2. **后端 /monitor/resources**  
   - 用 `redis_client.exists("system:controller:heartbeat")` 得到 `controller_online`，并放到 `stats["controller"] = {"online": controller_online}`。
   - 只有 Redis 里存在这个 key，前端才会拿到 `controller.online === true`。

3. **谁写这个 key**  
   - 只有 `src/core/controller.py` 的 `run_loop()` 在跑时，才会在循环里不断 `setex(system:controller:heartbeat, 30, ...)`。
   - 而 `run_loop()` 是由 Controller Celery Worker 执行的 `controller.run_loop` 任务调用的，该任务由 `controller_tasks.py` 里的 `worker_ready` 自动 `task_run_controller_loop.delay()` 触发。

因此，出现 Offline 时，通常只有这几类原因：

- Controller Worker 没起，或起了但没执行到 `run_loop()`（例如卡在别的任务或没收到 `controller.run_loop`）。
- Controller 和 Backend 用的不是同一个 Redis（host/port/db 不一致），心跳写在一个库、读在另一个库。
- 请求 `/monitor/resources` 失败或超时，前端从来没拿到过 `stats.controller.online === true`（你之前遇到的 30s 超时就属于这类）。

---

## 6. 相关文件与行号速查

| 用途 | 文件 | 位置 |
|------|------|------|
| 前端：用 stats.controller.online 决定在线/离线 | `web/src/pages/ControllerDashboard.tsx` | 约 21-28 行 |
| 前端：Offline 时显示的说明文案 | `web/src/pages/ControllerDashboard.tsx` | 约 128-138 行 |
| 后端：读 Redis 心跳、写 stats.controller | `src/api/routers/monitor.py` | 约 318-324 行 |
| 后端：monitor 用的 redis  client | `src/api/routers/monitor.py` | 约 10 行 |
| Controller：心跳 key、TTL、写心跳 | `src/core/controller.py` | 8-9 行, 99-108 行 |
| Controller：run_loop 与监听队列 | `src/core/controller.py` | 95-128 行 |
| Worker：自动发 run_loop 任务、初始化 Controller 用的 Redis | `src/workers/controller_tasks.py` | 14-23, 26-41, 45-53 行 |

你看到的「Controller Worker 负责消费所有节点的已处理队列…」那段话，就是 `ControllerDashboard.tsx` 里 `!controllerActive` 时渲染的同一段说明；把它和上面这些 controller 代码对照，就能完全看清楚「为何会显示 Offline」以及该查哪几处。
