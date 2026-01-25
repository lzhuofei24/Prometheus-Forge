import logging
from src.core.celery_config import celery_app
from src.core.state_manager import StateManager
from src.core.controller import CentralController
from src.core.app_settings import get_settings
from celery.signals import worker_ready
import redis

logger = logging.getLogger(__name__)

_controller = None


@worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    try:
        import os
        worker_name = os.environ.get('CELERY_WORKER_NAME', '')
        if 'controller' in worker_name.lower() or (sender and 'controller' in str(sender).lower()):
            logger.info("Controller worker ready, auto-starting loop...")
            task_run_controller_loop.delay()
    except Exception as e:
        logger.error(f"Failed to auto-start controller: {e}", exc_info=True)


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


@celery_app.task(
    name="controller.run_loop",
    bind=True,
    time_limit=None
)
def task_run_controller_loop(self):
    controller = _init_controller()
    logger.info("🚀 Starting Central Controller loop...")
    try:
        controller.run_loop()
    except KeyboardInterrupt:
        logger.info("Controller loop interrupted")
        controller.stop()
    except Exception as e:
        logger.error(f"Controller loop error: {e}", exc_info=True)
        raise
    return {"status": "stopped"}


@celery_app.task(
    name="controller.start",
    bind=True
)
def task_start_controller(self):
    task_run_controller_loop.delay()
    return {"status": "started"}
