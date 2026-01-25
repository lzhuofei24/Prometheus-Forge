import json
import logging
from pathlib import Path
import os
from src.core.celery_config import celery_app
from src.core.state_manager import StateManager
from src.core.dispatcher import Dispatcher
from src.core.llm import LLMClient
from src.core.config import Settings
from src.utils.file_manager import ProjectManager
from src.workers.handlers.architect import ArchitectHandler
from src.workers.handlers.writer import WriterHandler
from src.workers.handlers.critic import CriticHandler
from src.workers.handlers.media import MediaHandler
from src.workers.handlers.knowledge import KnowledgeHandler
from src.workers.handlers.censor import CensorHandler
from src.core.events import EventType, EventSource, EventPayload
from src.core.workflow_lock import WorkflowLock
from src.core.db_service import DatabaseService
from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

logger = logging.getLogger(__name__)

state_manager = None
dispatcher = None
llm_client = None
file_manager = None
workflow_lock = None


def _init_components():
    global state_manager, dispatcher, llm_client, file_manager, workflow_lock
    
    if state_manager is None:
        state_manager = StateManager()
    
    if workflow_lock is None:
        workflow_lock = WorkflowLock(state_manager.redis_client)
    
    if dispatcher is None:
        dispatcher = Dispatcher(state_manager)
    
    if file_manager is None:
        project_root = Path(__file__).parent.parent.parent
        from dotenv import load_dotenv
        load_dotenv(project_root / ".env")
        
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        file_manager = ProjectManager(Path(config.paths.workspace))
    
    if llm_client is None:
        project_root = Path(__file__).parent.parent.parent
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        
        api_key = None
        if hasattr(config.model, 'api_key_env') and config.model.api_key_env:
            api_key = os.getenv(config.model.api_key_env)
        elif config.model.provider == "siliconflow":
            api_key = os.getenv("SILICONFLOW_API_KEY")
        elif config.model.provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
        else:
            api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            api_key_env_name = getattr(config.model, 'api_key_env', None) or "SILICONFLOW_API_KEY"
            raise ValueError(f"API Key 未设置！请在 .env 文件中设置：{api_key_env_name}=your_key")
        
        base_url = getattr(config.model, 'base_url', None)
        site_url = None
        app_name = None
        if hasattr(config, 'llm') and config.llm:
            site_url = config.llm.get('site_url')
            app_name = config.llm.get('app_name')
        
        llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            api_key=api_key,
            base_url=base_url,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            api_key_env=getattr(config.model, 'api_key_env', None),
            site_url=site_url,
            app_name=app_name
        )
    
    return state_manager, dispatcher, llm_client, file_manager, workflow_lock


def _check_agent_disabled(agent_name: str) -> bool:
    """检查 agent 是否被禁用。与 API monitor 使用同一 Redis 配置，初始：无 key 或 \"1\" 为禁用，\"0\" 为启用。"""
    try:
        from src.core.app_settings import get_settings
        import redis
        s = get_settings()
        r = redis.Redis(host=s.redis_host, port=s.redis_port, db=s.redis_db, decode_responses=True)
        val = r.get(f"agent:{agent_name}:disabled")
        return (val or "1") == "1"
    except Exception as e:
        logger.debug(f"Failed to check agent disabled status: {e}")
        return False


def _get_redis_for_worker():
    """Worker 内获取 Redis，与 monitor/disable 使用同一配置。"""
    from src.core.app_settings import get_settings
    import redis as redis_mod
    s = get_settings()
    return redis_mod.Redis(host=s.redis_host, port=s.redis_port, db=s.redis_db, decode_responses=True)


def _handle_disabled_agent(self, agent_name: str, workflow_id: str) -> bool:
    """
    若 agent 被禁用：将当前任务 payload RPUSH 到 {agent}_suspended，然后返回 True，由调用方直接 return。
    不再 retry，任务从 pending 消失、进入挂起队列；启用时由 API 将 suspended 弹回 pending。
    """
    if not _check_agent_disabled(agent_name):
        return False
    try:
        r = _get_redis_for_worker()
        payload = {
            "task": self.request.task,
            "args": list(self.request.args),
            "kwargs": dict(self.request.kwargs),
        }
        r.rpush(f"{agent_name}_suspended", json.dumps(payload, ensure_ascii=False))
        logger.info(
            "Agent disabled, moved task to suspended queue. agent=%s, workflow_id=%s",
            agent_name, workflow_id
        )
        return True
    except Exception as e:
        logger.warning("Failed to move task to suspended queue: %s", e)
        return False


@celery_app.task(
    name="architect.generate_outline",
    time_limit=600,
    soft_time_limit=540,
    bind=True
)
def task_generate_outline(self, workflow_id: str, novel_name: str, chapter_num: int):
    logger.info("Agent architect received message for workflow %s", workflow_id)
    if _handle_disabled_agent(self, "architect", workflow_id):
        return {"status": "suspended", "agent": "architect", "workflow_id": workflow_id}
    state_manager, dispatcher, llm_client, file_manager, workflow_lock = _init_components()
    
    if not workflow_lock.acquire(workflow_id):
        logger.warning(f"Workflow {workflow_id} already running, skipping")
        return {"status": "skipped", "reason": "already_running"}
    
    try:
        handler = ArchitectHandler(state_manager, dispatcher, llm_client, file_manager)
        input_data = {
            "novel_name": novel_name,
            "chapter_num": chapter_num
        }
        result = handler.execute(workflow_id, input_data)
        logger.info("消费完成: agent=architect, workflow_id=%s", workflow_id)
        return result
    except (SoftTimeLimitExceeded, TimeLimitExceeded):
        state_manager.update_state(workflow_id, {"status": "timeout"})
        logger.error(f"Task timeout for workflow {workflow_id}")
        raise
    finally:
        workflow_lock.release(workflow_id)


@celery_app.task(
    name="writer.write_content",
    time_limit=1200,
    soft_time_limit=1140,
    bind=True
)
def task_write_content(self, workflow_id: str, feedback: str = None):
    logger.info("Agent writer received message for workflow %s", workflow_id)
    if _handle_disabled_agent(self, "writer", workflow_id):
        return {"status": "suspended", "agent": "writer", "workflow_id": workflow_id}
    state_manager, dispatcher, llm_client, file_manager, workflow_lock = _init_components()
    
    try:
        handler = WriterHandler(state_manager, dispatcher, llm_client, file_manager)
        input_data = {}
        if feedback:
            input_data["feedback"] = feedback
        result = handler.execute(workflow_id, input_data)
        logger.info("消费完成: agent=writer, workflow_id=%s", workflow_id)
        return result
    except (SoftTimeLimitExceeded, TimeLimitExceeded):
        state_manager.update_state(workflow_id, {"status": "timeout"})
        logger.error(f"Task timeout for workflow {workflow_id}")
        raise


@celery_app.task(
    name="writer.revise_content",
    time_limit=1200,
    soft_time_limit=1140,
    bind=True
)
def task_revise_content(self, workflow_id: str, feedback: str):
    logger.info("Agent writer received message for workflow %s (revise)", workflow_id)
    if _handle_disabled_agent(self, "writer", workflow_id):
        return {"status": "suspended", "agent": "writer", "workflow_id": workflow_id}
    state_manager, dispatcher, llm_client, file_manager, workflow_lock = _init_components()
    
    try:
        handler = WriterHandler(state_manager, dispatcher, llm_client, file_manager)
        input_data = {"feedback": feedback}
        result = handler.execute(workflow_id, input_data)
        logger.info("消费完成: agent=writer(revise), workflow_id=%s", workflow_id)
        return result
    except (SoftTimeLimitExceeded, TimeLimitExceeded):
        state_manager.update_state(workflow_id, {"status": "timeout"})
        logger.error(f"Task timeout for workflow {workflow_id}")
        raise


@celery_app.task(
    name="critic.critique_content",
    time_limit=600,
    soft_time_limit=540,
    bind=True
)
def task_critique_content(self, workflow_id: str):
    logger.info("Agent critic received message for workflow %s", workflow_id)
    if _handle_disabled_agent(self, "critic", workflow_id):
        return {"status": "suspended", "agent": "critic", "workflow_id": workflow_id}
    state_manager, dispatcher, llm_client, file_manager, workflow_lock = _init_components()
    
    try:
        handler = CriticHandler(state_manager, dispatcher, llm_client, file_manager)
        result = handler.execute(workflow_id, {})
        logger.info("消费完成: agent=critic, workflow_id=%s", workflow_id)
        return result
    except (SoftTimeLimitExceeded, TimeLimitExceeded):
        state_manager.update_state(workflow_id, {"status": "timeout"})
        logger.error(f"Task timeout for workflow {workflow_id}")
        raise


@celery_app.task(
    name="media.generate_media",
    time_limit=300,
    soft_time_limit=270,
    bind=True
)
def task_generate_media(self, workflow_id: str, chapter_content: str = None, scene_description: str = None):
    logger.info("Agent media received message for workflow %s", workflow_id)
    if _handle_disabled_agent(self, "media", workflow_id):
        return {"status": "suspended", "agent": "media", "workflow_id": workflow_id}
    state_manager, dispatcher, llm_client, file_manager, workflow_lock = _init_components()
    
    try:
        handler = MediaHandler(state_manager, dispatcher, llm_client, file_manager)
        input_data = {}
        if chapter_content:
            input_data["chapter_content"] = chapter_content
        if scene_description:
            input_data["scene_description"] = scene_description
        result = handler.execute(workflow_id, input_data)
        logger.info("消费完成: agent=media, workflow_id=%s", workflow_id)
        return result
    except (SoftTimeLimitExceeded, TimeLimitExceeded):
        state_manager.update_state(workflow_id, {"status": "timeout"})
        logger.error(f"Task timeout for workflow {workflow_id}")
        raise


@celery_app.task(
    name="knowledge.update_knowledge",
    time_limit=600,
    soft_time_limit=540,
    bind=True
)
def task_update_knowledge(self, workflow_id: str):
    logger.info("Agent knowledge received message for workflow %s", workflow_id)
    if _handle_disabled_agent(self, "knowledge", workflow_id):
        return {"status": "suspended", "agent": "knowledge", "workflow_id": workflow_id}
    state_manager, dispatcher, llm_client, file_manager, workflow_lock = _init_components()
    
    try:
        handler = KnowledgeHandler(state_manager, dispatcher, llm_client, file_manager)
        result = handler.execute(workflow_id, {})
        logger.info("消费完成: agent=knowledge, workflow_id=%s", workflow_id)
        return result
    except (SoftTimeLimitExceeded, TimeLimitExceeded):
        state_manager.update_state(workflow_id, {"status": "timeout"})
        logger.error(f"Task timeout for workflow {workflow_id}")
        raise


@celery_app.task(
    name="censor.check_content",
    time_limit=300,
    soft_time_limit=270,
    bind=True
)
def task_censor_content(self, workflow_id: str):
    logger.info("Agent censor received message for workflow %s", workflow_id)
    if _handle_disabled_agent(self, "censor", workflow_id):
        return {"status": "suspended", "agent": "censor", "workflow_id": workflow_id}
    state_manager, dispatcher, llm_client, file_manager, workflow_lock = _init_components()
    
    try:
        handler = CensorHandler(state_manager, dispatcher, llm_client)
        state = state_manager.get_state(workflow_id)
        input_data = {"content": state.get("draft_content", "")}
        result = handler.execute(workflow_id, input_data)
        logger.info("消费完成: agent=censor, workflow_id=%s", workflow_id)
        return result
    except (SoftTimeLimitExceeded, TimeLimitExceeded):
        state_manager.update_state(workflow_id, {"status": "timeout"})
        logger.error(f"Task timeout for workflow {workflow_id}")
        raise
