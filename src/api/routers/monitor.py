import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter
import redis

from src.api.schemas.workflow import TokenStatsResponse
from src.core.state_manager import StateManager
from src.core.celery_config import celery_app
from src.core.app_settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor", tags=["monitor"])

def _get_redis_client() -> redis.Redis:
    """与 Controller / StateManager 使用相同 Redis 配置，确保能读到 system:controller:heartbeat。"""
    s = get_settings()
    return redis.Redis(
        host=s.redis_host,
        port=s.redis_port,
        db=s.redis_db,
        decode_responses=True,
    )

_settings = get_settings()
state_manager = StateManager(
    redis_host=_settings.redis_host,
    redis_port=_settings.redis_port,
    redis_db=_settings.redis_db,
)
redis_client = _get_redis_client()

# 与 celery_config 中队列命名一致：Redis List key 即队列名
AGENTS = ["architect", "writer", "critic", "media", "knowledge", "censor"]
CONTROLLER_HEARTBEAT_KEY = "system:controller:heartbeat"


def get_monitor_data_from_redis() -> Dict[str, Any]:
    """仅用 Redis Pipeline 一次性拉取队列长度、Controller 心跳、禁用状态与全局统计，不做 Celery inspect。"""
    pipe = redis_client.pipeline()

    # 1) 各 Agent 的 pending / completed / suspended 队列长度
    for agent in AGENTS:
        pipe.llen(f"{agent}_pending")
        pipe.llen(f"{agent}_completed")
        pipe.llen(f"{agent}_suspended")
    pipe.llen("controller_pending")

    # 2) Controller 心跳
    pipe.exists(CONTROLLER_HEARTBEAT_KEY)

    # 3) 各 Agent 禁用状态
    for agent in AGENTS:
        pipe.get(f"agent:{agent}:disabled")

    # 3.5) 各 Agent 是否正在执行（agent:{name}:processing 是否存在）
    for agent in AGENTS:
        pipe.exists(f"agent:{agent}:processing")

    # 4) 全局统计（若有）
    pipe.get("stats:api_calls")
    pipe.get("stats:prompt_tokens")
    pipe.get("stats:completion_tokens")

    try:
        results = pipe.execute()
    except Exception as e:
        logger.warning("Redis pipeline execute failed: %s", e)
        return _empty_monitor_data()

    idx = 0
    queue_lengths = {}
    for agent in AGENTS:
        pending = results[idx] if results[idx] is not None else 0
        completed = results[idx + 1] if results[idx + 1] is not None else 0
        suspended = results[idx + 2] if results[idx + 2] is not None else 0
        idx += 3
        queue_lengths[f"{agent}_pending"] = int(pending)
        queue_lengths[f"{agent}_completed"] = int(completed)
        queue_lengths[f"{agent}_suspended"] = int(suspended)
    queue_lengths["controller_pending"] = int(results[idx] or 0)
    idx += 1

    controller_online = bool(results[idx])
    idx += 1

    agent_disabled = {}
    for agent in AGENTS:
        val = results[idx]
        agent_disabled[agent] = (val or "1") == "1"
        idx += 1

    agent_processing = {}
    for agent in AGENTS:
        agent_processing[agent] = bool(results[idx])
        idx += 1

    global_stats = {}
    api_calls = results[idx]
    prompt_tokens = results[idx + 1]
    completion_tokens = results[idx + 2]
    if api_calls or prompt_tokens or completion_tokens:
        global_stats["global"] = {
            "api_calls": int(api_calls) if api_calls else 0,
            "prompt_tokens": int(float(prompt_tokens)) if prompt_tokens else 0,
            "completion_tokens": int(float(completion_tokens)) if completion_tokens else 0,
        }

    # 占位 workers：不再查 inspect，仅保留结构兼容；Controller 状态以心跳为准
    workers_list = _minimal_workers_list(controller_online)
    active_count = sum(1 for w in workers_list if w.get("status") == "online")

    return {
        "queues": queue_lengths,
        "controller": {"online": controller_online},
        "workers": {"active": active_count, "list": workers_list},
        "agent_tasks": {a: None for a in AGENTS},
        "agent_disabled": agent_disabled,
        "agent_processing": agent_processing,
        "global_stats": global_stats,
    }


def _empty_monitor_data() -> Dict[str, Any]:
    queues = {f"{a}_pending": 0 for a in AGENTS}
    queues.update({f"{a}_completed": 0 for a in AGENTS})
    queues.update({f"{a}_suspended": 0 for a in AGENTS})
    queues["controller_pending"] = 0
    return {
        "queues": queues,
        "controller": {"online": False},
        "workers": {"active": 0, "list": _minimal_workers_list(False)},
        "agent_tasks": {a: None for a in AGENTS},
        "agent_disabled": {a: False for a in AGENTS},
        "agent_processing": {a: False for a in AGENTS},
        "global_stats": {},
    }


def _minimal_workers_list(controller_online: bool) -> List[Dict[str, Any]]:
    """返回结构兼容的 workers 占位列表，不做 inspect。"""
    display_map = {
        "architect": "Architect",
        "writer": "Writer",
        "critic": "Critic",
        "media": "Media",
        "knowledge": "Knowledge",
        "censor": "Censor",
    }
    out = []
    for agent in AGENTS:
        out.append({
            "name": display_map.get(agent, agent),
            "original_name": f"{agent}@redis",
            "instance_id": 0,
            "status": "online",  # 占位，无 inspect 时暂视为在线
            "active_tasks": 0,
            "reserved_tasks": 0,
            "registered_tasks": 0,
            "queues": [f"{agent}_pending"],
            "current_tasks": [],
            "pool": "solo",
            "concurrency": 1,
        })
    out.append({
        "name": "Controller",
        "original_name": "controller@heartbeat",
        "instance_id": 0,
        "status": "online" if controller_online else "offline",
        "active_tasks": 0,
        "reserved_tasks": 0,
        "registered_tasks": 0,
        "queues": ["controller_pending"],
        "current_tasks": [],
        "pool": "solo",
        "concurrency": 1,
    })
    return out


def get_queue_length(queue_name: str) -> int:
    """获取 Celery 队列长度（仅统计 Redis 中该队列 list 的长度，即尚未被 worker 取走的消息数）"""
    try:
        # Redis 作为 broker 时，队列名为 list 的 key，直接 llen 最可靠
        try:
            n = redis_client.llen(queue_name)
            if n is not None:
                return int(n)
        except Exception:
            pass
        # 兼容：若配置了 tasks. 前缀等
        for key in (queue_name, f"tasks.{queue_name}"):
            try:
                n = redis_client.llen(key)
                if n is not None and n > 0:
                    return int(n)
            except Exception:
                continue
        return 0
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Failed to get queue length for {queue_name}: {e}")
        return 0


def get_active_workers_count(active_data=None) -> int:
    """获取活跃的 Celery worker 数量"""
    try:
        if active_data is not None:
            return len(active_data) if active_data else 0
        inspect = celery_app.control.inspect(timeout=1.0)
        active = inspect.active()
        if active:
            return len(active)
        return 0
    except Exception:
        return 0


def get_all_workers_info(active_data=None, inspect_timeout: float = 3.0) -> list:
    """获取所有 Celery Worker 的详细信息。inspect_timeout 稍大以便阻塞型 worker（如 Controller run_loop）有机会响应。"""
    try:
        inspect = celery_app.control.inspect(timeout=inspect_timeout)
        
        stats = inspect.stats() or {}
        active = active_data if active_data is not None else (inspect.active() or {})
        registered = inspect.registered() or {}
        reserved = inspect.reserved() or {}
        
        all_worker_names = set()
        all_worker_names.update(stats.keys())
        all_worker_names.update(active.keys())
        all_worker_names.update(registered.keys())
        
        workers = []
        worker_instances = {}
        
        for worker_name in all_worker_names:
            # 出现在 stats 或 active 中均视为在线。Controller 等长时间阻塞在 run_loop 的 worker
            # 可能无法在 inspect 超时内响应 stats，但会出现在 active（正在执行 controller.run_loop）
            is_online = (worker_name in stats) or (worker_name in active)
            
            worker_stats = stats.get(worker_name, {})
            pool_info = worker_stats.get('pool', {})
            concurrency = pool_info.get('max-concurrency', 0)
            
            active_tasks_list = active.get(worker_name, [])
            reserved_tasks_list = reserved.get(worker_name, [])
            
            queues_handled = set()
            for task in active_tasks_list + reserved_tasks_list:
                routing_key = task.get('delivery_info', {}).get('routing_key', '') or task.get('request', {}).get('routing_key', '')
                if routing_key.startswith('architect.'):
                    queues_handled.add('architect_pending')
                elif routing_key.startswith('writer.'):
                    queues_handled.add('writer_pending')
                elif routing_key.startswith('critic.'):
                    queues_handled.add('critic_pending')
                elif routing_key.startswith('media.'):
                    queues_handled.add('media_pending')
                elif routing_key.startswith('knowledge.'):
                    queues_handled.add('knowledge_pending')
                elif routing_key.startswith('censor.'):
                    queues_handled.add('censor_pending')
            
            if not queues_handled:
                worker_name_lower = worker_name.lower()
                if 'architect' in worker_name_lower:
                    queues_handled.add('architect_pending')
                elif 'writer' in worker_name_lower:
                    queues_handled.add('writer_pending')
                elif 'critic' in worker_name_lower:
                    queues_handled.add('critic_pending')
                elif 'media' in worker_name_lower:
                    queues_handled.add('media_pending')
                elif 'knowledge' in worker_name_lower:
                    queues_handled.add('knowledge_pending')
                elif 'censor' in worker_name_lower:
                    queues_handled.add('censor_pending')
                elif 'controller' in worker_name_lower:
                    queues_handled.add('controller_pending')
            
            if worker_name not in worker_instances:
                worker_instances[worker_name] = []
            
            instance_id = len(worker_instances[worker_name])
            
            worker_name_lower = worker_name.lower()
            if 'architect' in worker_name_lower:
                display_name = 'Architect'
            elif 'writer' in worker_name_lower:
                display_name = 'Writer'
            elif 'critic' in worker_name_lower:
                display_name = 'Critic'
            elif 'media' in worker_name_lower:
                display_name = 'Media'
            elif 'knowledge' in worker_name_lower:
                display_name = 'Knowledge'
            elif 'censor' in worker_name_lower:
                display_name = 'Censor'
            elif 'controller' in worker_name_lower:
                display_name = 'Controller'
            else:
                display_name = worker_name
            
            worker_info = {
                'name': display_name,
                'original_name': worker_name,
                'instance_id': instance_id,
                'status': 'online' if is_online else 'offline',
                'active_tasks': len(active_tasks_list),
                'registered_tasks': len(registered.get(worker_name, [])),
                'reserved_tasks': len(reserved_tasks_list),
                'queues': sorted(list(queues_handled)) if queues_handled else ['unknown'],
            }
            
            worker_info['pool'] = pool_info.get('implementation', 'unknown')
            worker_info['concurrency'] = concurrency
            
            if active_tasks_list:
                current_tasks = []
                for task in active_tasks_list:
                    current_tasks.append({
                        'id': task.get('id', ''),
                        'name': task.get('name', ''),
                        'time_start': task.get('time_start', 0),
                    })
                worker_info['current_tasks'] = current_tasks
            else:
                worker_info['current_tasks'] = []
            
            worker_instances[worker_name].append(worker_info)
        
        for worker_name, instances in worker_instances.items():
            if len(instances) == 1:
                workers.append(instances[0])
            else:
                for idx, instance in enumerate(instances):
                    instance['name'] = worker_name
                    workers.append(instance)
        
        
        return sorted(workers, key=lambda x: (x['original_name'], x['instance_id']))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to get workers info: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return []


def _agent_from_worker_or_task(worker_name: str, task_name: str) -> str:
    """根据 worker 名或任务名推断 agent（architect/writer/critic/media/knowledge/censor）。"""
    w = (worker_name or "").lower()
    t = (task_name or "").lower()
    if "architect" in w or "outline" in t or "architect." in t:
        return "architect"
    if "writer" in w or "write_content" in t or "revise_content" in t or "writer." in t:
        return "writer"
    if "critic" in w or "critique" in t or "critic." in t:
        return "critic"
    if "media" in w or "generate_media" in t or "media." in t:
        return "media"
    if "knowledge" in w or "update_knowledge" in t or "knowledge." in t:
        return "knowledge"
    if "censor" in w or "check_content" in t or "censor." in t:
        return "censor"
    return ""


def get_reserved_and_scheduled_by_agent(inspect_timeout: float = 1.0) -> tuple:
    """返回 (reserved_by_agent, scheduled_by_agent)，每个为 dict agent -> count。"""
    reserved_counts = {a: 0 for a in ("architect", "writer", "critic", "media", "knowledge", "censor")}
    scheduled_counts = {a: 0 for a in reserved_counts}
    try:
        insp = celery_app.control.inspect(timeout=inspect_timeout)
        reserved = insp.reserved() or {}
        scheduled = insp.scheduled() or {}
    except Exception:
        return reserved_counts, scheduled_counts
    for worker_name, tasks in reserved.items():
        for t in (tasks or []):
            name = t.get("name") or ""
            agent = _agent_from_worker_or_task(worker_name, name)
            if agent and agent in reserved_counts:
                reserved_counts[agent] += 1
    for worker_name, tasks in scheduled.items():
        for t in (tasks or []):
            name = t.get("name") or ""
            agent = _agent_from_worker_or_task(worker_name, name)
            if agent and agent in scheduled_counts:
                scheduled_counts[agent] += 1
    return reserved_counts, scheduled_counts


def get_active_tasks_by_agent(active_data=None) -> dict:
    """获取每个Agent正在执行的任务信息"""
    try:
        active = active_data if active_data is not None else {}
        if active_data is None:
            inspect = celery_app.control.inspect(timeout=1.0)
            active = inspect.active() or {}
        
        agent_tasks = {
            'architect': None,
            'writer': None,
            'critic': None,
            'media': None,
            'knowledge': None,
            'censor': None,
        }
        
        for worker_name, task_list in active.items():
            for task in task_list:
                task_name = task.get('name', '').lower()
                if 'generate_outline' in task_name or 'outline' in task_name:
                    agent_tasks['architect'] = {
                        'task_name': task.get('name', ''),
                        'time_start': task.get('time_start', 0),
                    }
                elif 'write_content' in task_name or ('write' in task_name and 'content' in task_name):
                    agent_tasks['writer'] = {
                        'task_name': task.get('name', ''),
                        'time_start': task.get('time_start', 0),
                    }
                elif 'revise_content' in task_name or 'revise' in task_name:
                    agent_tasks['writer'] = {
                        'task_name': task.get('name', ''),
                        'time_start': task.get('time_start', 0),
                    }
                elif 'critique_content' in task_name or 'critique' in task_name:
                    agent_tasks['critic'] = {
                        'task_name': task.get('name', ''),
                        'time_start': task.get('time_start', 0),
                    }
                elif 'generate_media' in task_name or ('media' in task_name and 'generate' in task_name):
                    agent_tasks['media'] = {
                        'task_name': task.get('name', ''),
                        'time_start': task.get('time_start', 0),
                    }
                elif 'update_knowledge' in task_name or ('knowledge' in task_name and 'update' in task_name):
                    agent_tasks['knowledge'] = {
                        'task_name': task.get('name', ''),
                        'time_start': task.get('time_start', 0),
                    }
                elif 'check_content' in task_name or ('censor' in task_name and 'check' in task_name):
                    agent_tasks['censor'] = {
                        'task_name': task.get('name', ''),
                        'time_start': task.get('time_start', 0),
                    }
        
        return agent_tasks
    except Exception:
        return {
            'architect': None,
            'writer': None,
            'critic': None,
            'media': None,
            'knowledge': None,
            'censor': None,
        }


@router.get("/resources", response_model=TokenStatsResponse)
async def get_resources():
    """监控数据：仅用 Redis Pipeline 拉取队列/心跳/禁用/全局统计，不再调用 Celery Inspect。"""
    stats = state_manager.get_token_stats()
    mon = get_monitor_data_from_redis()

    stats["queues"] = mon["queues"]
    stats["controller"] = mon["controller"]
    stats["workers"] = mon["workers"]
    stats["agent_tasks"] = mon["agent_tasks"]
    stats["agent_disabled"] = mon["agent_disabled"]
    stats["agent_processing"] = mon.get("agent_processing") or {a: False for a in AGENTS}
    if mon.get("global_stats"):
        stats.update(mon["global_stats"])

    logger.debug("Queue lengths: %s, controller_online=%s", mon["queues"], mon["controller"].get("online"))
    return TokenStatsResponse(stats=stats)


@router.post("/queues/{queue_name}/purge")
async def purge_queue(queue_name: str):
    """清空指定队列中的所有消息"""
    try:
        if queue_name.endswith("_pending"):
            with celery_app.connection_or_acquire() as conn:
                channel = conn.default_channel
                queue_info = channel.queue_declare(queue=queue_name, passive=True)
                purged = channel.queue_purge(queue=queue_name)
                return {"success": True, "purged": purged, "queue": queue_name}
        elif queue_name.endswith("_completed"):
            count = redis_client.llen(queue_name)
            redis_client.delete(queue_name)
            return {"success": True, "purged": count, "queue": queue_name}
        else:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Invalid queue name")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to purge queue {queue_name}: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to purge queue: {str(e)}")


@router.post("/controller/start")
async def start_controller():
    """启动中控系统"""
    try:
        from src.workers.controller_tasks import task_run_controller_loop
        task_run_controller_loop.delay()
        return {"status": "started"}
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to start controller: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to start controller: {str(e)}")


@router.post("/agents/{agent_name}/disable")
async def disable_agent(agent_name: str):
    """禁用指定的 agent"""
    AGENTS = ['architect', 'writer', 'critic', 'media', 'knowledge', 'censor']
    if agent_name not in AGENTS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid agent name. Must be one of: {', '.join(AGENTS)}")
    
    try:
        # 使用 Redis 存储禁用状态，key: agent:{agent_name}:disabled
        redis_client.set(f"agent:{agent_name}:disabled", "1")
        return {"success": True, "agent": agent_name, "status": "disabled"}
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to disable agent {agent_name}: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to disable agent: {str(e)}")


def _redrive_suspended_to_pending(agent_name: str) -> int:
    """将 {agent}_suspended 中所有任务弹回 {agent}_pending，返回移动的数量。"""
    key = f"{agent_name}_suspended"
    queue_pending = f"{agent_name}_pending"
    count = 0
    while True:
        raw = redis_client.lpop(key)
        if not raw:
            break
        try:
            data = json.loads(raw)
            task_name = data.get("task")
            args = data.get("args") or []
            kwargs = data.get("kwargs") or {}
            if task_name:
                celery_app.send_task(task_name, args=args, kwargs=kwargs, queue=queue_pending)
                count += 1
        except Exception as e:
            logger.warning("Re-drive from suspended failed for agent=%s: %s", agent_name, e)
    return count


@router.post("/agents/{agent_name}/enable")
async def enable_agent(agent_name: str):
    """启用指定的 agent，并将挂起队列中的任务全部弹回 pending。"""
    AGENTS = ['architect', 'writer', 'critic', 'media', 'knowledge', 'censor']
    if agent_name not in AGENTS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid agent name. Must be one of: {', '.join(AGENTS)}")
    
    try:
        redis_client.set(f"agent:{agent_name}:disabled", "0")
        redriven = _redrive_suspended_to_pending(agent_name)
        if redriven:
            logger.info("Agent %s enabled, redriven %d task(s) from suspended to pending", agent_name, redriven)
        return {"success": True, "agent": agent_name, "status": "enabled", "redriven": redriven}
    except Exception as e:
        logger.error(f"Failed to enable agent {agent_name}: {e}")
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(e))


def is_agent_disabled(agent_name: str) -> bool:
    """检查 agent 是否被禁用。初始状态为禁用：无 key 或值为 \"1\" 视为禁用，仅显式 \"0\" 为启用。"""
    try:
        val = redis_client.get(f"agent:{agent_name}:disabled")
        return (val or "1") == "1"
    except Exception:
        return False
