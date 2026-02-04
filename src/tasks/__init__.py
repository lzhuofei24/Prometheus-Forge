"""
Task System - Distributed Task Execution (Celery Interface)

This module defines task interfaces for distributed execution.
In Phase 1, these are stubs. In Phase 2, they will be connected to Celery workers.

Task Categories:
- compute_tasks.py: CPU-intensive tasks (reranking, entity extraction)
- io_tasks.py: I/O-intensive tasks (database writes, graph updates)
- memory_tasks.py: Memory consolidation tasks (background processing)
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TaskRegistry:
    """
    Registry for task definitions.

    In Phase 2, this will be replaced with Celery app configuration.
    """

    _tasks: Dict[str, callable] = {}

    @classmethod
    def register(cls, name: str, task_func: callable):
        """
        Register a task.

        Args:
            name: Task name
            task_func: Task function
        """
        cls._tasks[name] = task_func
        logger.info(f"Registered task: {name}")

    @classmethod
    def get_task(cls, name: str) -> Optional[callable]:
        """
        Get task by name.

        Args:
            name: Task name

        Returns:
            Task function or None
        """
        return cls._tasks.get(name)

    @classmethod
    def list_tasks(cls) -> list:
        """
        List all registered tasks.

        Returns:
            List of task names
        """
        return list(cls._tasks.keys())


def task(name: Optional[str] = None, queue: str = "default"):
    """
    Task decorator (stub for Celery @task).

    In Phase 2, this will be replaced with actual Celery decorator.

    Args:
        name: Optional task name
        queue: Queue name (compute_queue, io_queue)

    Returns:
        Decorator function
    """
    def decorator(func):
        task_name = name or func.__name__
        TaskRegistry.register(task_name, func)

        # Add metadata to function
        func._task_name = task_name
        func._task_queue = queue

        # Stub for apply_async (Celery interface)
        def apply_async(*args, **kwargs):
            """
            Stub for Celery apply_async.

            In Phase 1, this just calls the function directly.
            In Phase 2, this will submit to Celery.
            """
            logger.info(f"[STUB] Task {task_name} called (would be async in Phase 2)")
            # Direct synchronous call for now
            return func(*args, **kwargs)

        func.apply_async = apply_async

        return func

    return decorator


# Phase 2 TODO:
# Replace this module with actual Celery app configuration:
#
# from celery import Celery
#
# app = Celery('prometheus_forge', broker='redis://localhost:6379/0')
#
# app.conf.update(
#     task_routes={
#         'src.tasks.compute_tasks.*': {'queue': 'compute_queue'},
#         'src.tasks.io_tasks.*': {'queue': 'io_queue'},
#     },
#     worker_prefetch_multiplier=1,
#     worker_max_tasks_per_child=1000,
# )
