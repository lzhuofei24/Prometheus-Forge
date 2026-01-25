import redis
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class WorkflowLock:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def acquire(self, workflow_id: str, timeout: int = 3600) -> bool:
        lock_key = f"workflow:lock:{workflow_id}"
        if self.redis.set(lock_key, "1", nx=True, ex=timeout):
            logger.info(f"Workflow lock acquired: {workflow_id}")
            return True
        logger.warning(f"Workflow lock already exists: {workflow_id}")
        return False

    def release(self, workflow_id: str):
        lock_key = f"workflow:lock:{workflow_id}"
        self.redis.delete(lock_key)
        logger.info(f"Workflow lock released: {workflow_id}")

    def is_locked(self, workflow_id: str) -> bool:
        lock_key = f"workflow:lock:{workflow_id}"
        return self.redis.exists(lock_key) > 0
