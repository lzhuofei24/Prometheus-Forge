from celery import Celery
from kombu import Queue

celery_app = Celery(
    'novel_agent',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1',
    timezone='Asia/Shanghai',
    enable_utc=True,
)

AGENTS = ['architect', 'writer', 'critic', 'media', 'knowledge', 'censor']

celery_app.conf.task_queues = tuple(
    Queue(f'{agent}_pending', routing_key=f'{agent}.pending')
    for agent in AGENTS
) + (
    Queue('controller_pending', routing_key='controller.pending'),
)

celery_app.conf.task_routes = {
    'architect.*': {'queue': 'architect_pending'},
    'writer.*': {'queue': 'writer_pending'},
    'critic.*': {'queue': 'critic_pending'},
    'media.*': {'queue': 'media_pending'},
    'knowledge.*': {'queue': 'knowledge_pending'},
    'censor.*': {'queue': 'censor_pending'},
    'controller.*': {'queue': 'controller_pending'},
}

celery_app.conf.task_default_queue = 'architect_pending'
celery_app.conf.task_default_exchange = 'tasks'
celery_app.conf.task_default_exchange_type = 'direct'
celery_app.conf.task_default_routing_key = 'architect.pending'

celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_acks_late = True
celery_app.conf.worker_send_task_events = True
celery_app.conf.task_send_sent_event = True
celery_app.conf.worker_disable_rate_limits = False
celery_app.conf.worker_max_tasks_per_child = 1000
celery_app.conf.worker_hijack_root_logger = False
celery_app.conf.worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
celery_app.conf.worker_task_log_format = '[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s'
celery_app.conf.task_always_eager = False
celery_app.conf.task_eager_propagates = False
celery_app.conf.worker_pool = 'solo'
# 允许任务重试（用于 agent 禁用时的阻塞机制）
celery_app.conf.task_autoretry_for = (Exception,)
celery_app.conf.task_default_max_retries = 1000
