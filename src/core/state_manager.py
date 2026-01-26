import json
import redis
from typing import Dict, Any, Optional, List
from datetime import datetime
from src.core.events import AuditLogEntry
import logging

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0):
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )

    def get_state(self, workflow_id: str) -> Dict[str, Any]:
        key = f"workflow:{workflow_id}:state"
        data = self.redis_client.hgetall(key)
        if not data:
            return {}
        
        result = {}
        for k, v in data.items():
            try:
                result[k] = json.loads(v)
            except:
                result[k] = v
        return result

    def update_state(self, workflow_id: str, updates: Dict[str, Any]):
        key = f"workflow:{workflow_id}:state"
        pipe = self.redis_client.pipeline()
        for k, v in updates.items():
            if isinstance(v, (dict, list)):
                pipe.hset(key, k, json.dumps(v, ensure_ascii=False))
            else:
                pipe.hset(key, k, str(v))
        pipe.execute()

    def add_audit_log(self, workflow_id: str, entry: AuditLogEntry):
        key = f"workflow:{workflow_id}:audit"
        entry_dict = entry.model_dump()
        entry_dict["timestamp"] = entry.timestamp.isoformat()
        self.redis_client.lpush(key, json.dumps(entry_dict, ensure_ascii=False))
        self.redis_client.ltrim(key, 0, 9999)

    def get_workflow_trace(self, workflow_id: str) -> List[Dict[str, Any]]:
        key = f"workflow:{workflow_id}:audit"
        logs = self.redis_client.lrange(key, 0, -1)
        result = []
        for log_str in reversed(logs):
            try:
                log_dict = json.loads(log_str)
                log_dict["timestamp"] = datetime.fromisoformat(log_dict["timestamp"])
                result.append(log_dict)
            except Exception as e:
                logger.warning(f"Failed to parse audit log: {e}")
        return result

    def init_workflow(self, workflow_id: str, initial_state: Dict[str, Any]):
        self.update_state(workflow_id, initial_state)
        self.redis_client.set(f"workflow:{workflow_id}:created_at", datetime.now().isoformat())
        workflow_type = (initial_state.get("workflow_type") or "").strip() or "generate_chapter"
        self.redis_client.sadd(f"workflow_type_index:{workflow_type}", workflow_id)

    def delete_workflow(self, workflow_id: str):
        state = self.get_state(workflow_id)
        workflow_type = (state.get("workflow_type") or "").strip() or "generate_chapter"
        self.redis_client.delete(f"workflow:{workflow_id}:state")
        self.redis_client.delete(f"workflow:{workflow_id}:audit")
        self.redis_client.delete(f"workflow:{workflow_id}:created_at")
        self.redis_client.srem(f"workflow_type_index:{workflow_type}", workflow_id)

    def list_workflow_ids_by_type(self, workflow_type: str) -> List[str]:
        """返回该 workflow_type 下所有 workflow_id（含仅存在于索引但 state 已删的，调用方需按 state 存在性过滤）。"""
        key = f"workflow_type_index:{(workflow_type or '').strip() or 'generate_chapter'}"
        return list(self.redis_client.smembers(key) or [])

    def get_token_stats(self) -> Dict[str, Any]:
        stats = {}
        for key in self.redis_client.scan_iter(match="token_stats:*"):
            workflow_id = key.split(":")[-1]
            data = self.redis_client.hgetall(key)
            stats[workflow_id] = {
                k: int(v) if v.isdigit() else v
                for k, v in data.items()
            }
        return stats
