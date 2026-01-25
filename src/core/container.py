from typing import Optional
import redis
from pathlib import Path
import os
from src.core.state_manager import StateManager
from src.core.dispatcher import Dispatcher
from src.core.llm import LLMClient
from src.core.cache import CacheService
from src.core.workflow_lock import WorkflowLock
from src.core.db_service import DatabaseService
from src.core.config import Settings
from src.utils.file_manager import ProjectManager
from src.core.app_settings import get_settings


_redis_client: Optional[redis.Redis] = None
_cache_service: Optional[CacheService] = None
_state_manager: Optional[StateManager] = None
_workflow_lock: Optional[WorkflowLock] = None
_dispatcher: Optional[Dispatcher] = None
_settings: Optional[Settings] = None
_file_manager: Optional[ProjectManager] = None
_llm_client: Optional[LLMClient] = None


def _get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True
        )
    return _redis_client


def _get_cache_service() -> CacheService:
    global _cache_service
    if _cache_service is None:
        _cache_service = CacheService(_get_redis_client())
    return _cache_service


def _get_state_manager() -> StateManager:
    global _state_manager
    if _state_manager is None:
        settings = get_settings()
        _state_manager = StateManager(
            redis_host=settings.redis_host,
            redis_port=settings.redis_port,
            redis_db=settings.redis_db
        )
    return _state_manager


def _get_workflow_lock() -> WorkflowLock:
    global _workflow_lock
    if _workflow_lock is None:
        _workflow_lock = WorkflowLock(_get_redis_client())
    return _workflow_lock


def _get_dispatcher() -> Dispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = Dispatcher(_get_state_manager())
    return _dispatcher


def _get_settings() -> Settings:
    global _settings
    if _settings is None:
        project_root = Path(__file__).parent.parent.parent
        _settings = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    return _settings

def reload_settings():
    global _settings, _llm_client
    project_root = Path(__file__).parent.parent.parent
    _settings = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    _llm_client = None


def _get_file_manager() -> ProjectManager:
    global _file_manager
    if _file_manager is None:
        settings = _get_settings()
        _file_manager = ProjectManager(Path(settings.paths.workspace))
    return _file_manager


def _get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        settings = _get_settings()
        api_key = os.getenv(settings.model.api_key_env or "OPENROUTER_API_KEY")
        _llm_client = LLMClient(
            provider=settings.model.provider,
            model=settings.model.name,
            api_key=api_key,
            base_url=settings.model.base_url,
            temperature=settings.model.temperature,
            max_tokens=settings.model.max_tokens,
            api_key_env=settings.model.api_key_env,
            site_url=settings.llm.get("site_url") if settings.llm else None,
            app_name=settings.llm.get("app_name") if settings.llm else None
        )
    return _llm_client


class Container:
    @staticmethod
    def redis_client() -> redis.Redis:
        return _get_redis_client()
    
    @staticmethod
    def cache_service() -> CacheService:
        return _get_cache_service()
    
    @staticmethod
    def state_manager() -> StateManager:
        return _get_state_manager()
    
    @staticmethod
    def workflow_lock() -> WorkflowLock:
        return _get_workflow_lock()
    
    @staticmethod
    def dispatcher() -> Dispatcher:
        return _get_dispatcher()
    
    @staticmethod
    def settings() -> Settings:
        return _get_settings()
    
    @staticmethod
    def file_manager() -> ProjectManager:
        return _get_file_manager()
    
    @staticmethod
    def llm_client() -> LLMClient:
        return _get_llm_client()


container = Container()


def init_container():
    DatabaseService.set_cache_service(container.cache_service())
    LLMClient.set_cache_service(container.cache_service())
