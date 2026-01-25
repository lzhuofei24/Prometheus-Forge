import json
import hashlib
import redis
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CacheService:
    _instance = None
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    @classmethod
    def set_cache_service(cls, cache_service):
        cls._instance = cache_service
    
    @classmethod
    def get_instance(cls):
        return cls._instance

    def get_chapter_content(self, novel_id: str, chapter_index: int) -> Optional[str]:
        cache_key = f"chapter:{novel_id}:{chapter_index}:content"
        cached = self.redis.get(cache_key)
        if cached:
            return cached
        return None

    def set_chapter_content(self, novel_id: str, chapter_index: int, content: str, ttl: int = 3600):
        cache_key = f"chapter:{novel_id}:{chapter_index}:content"
        self.redis.setex(cache_key, ttl, content)

    def get_chapter_outline(self, novel_id: str, chapter_index: int) -> Optional[str]:
        cache_key = f"chapter:{novel_id}:{chapter_index}:outline"
        cached = self.redis.get(cache_key)
        if cached:
            return cached
        return None

    def set_chapter_outline(self, novel_id: str, chapter_index: int, outline: str, ttl: int = 3600):
        cache_key = f"chapter:{novel_id}:{chapter_index}:outline"
        self.redis.setex(cache_key, ttl, outline)

    def get_novel_settings(self, novel_name: str) -> Optional[Dict[str, Any]]:
        cache_key = f"novel:{novel_name}:settings"
        cached = self.redis.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except:
                return None
        return None

    def set_novel_settings(self, novel_name: str, settings: Dict[str, Any], ttl: int = 300):
        cache_key = f"novel:{novel_name}:settings"
        self.redis.setex(cache_key, ttl, json.dumps(settings, ensure_ascii=False))

    def get_llm_response(self, messages: list, temperature: float = 0.7) -> Optional[str]:
        prompt_hash = hashlib.md5(
            json.dumps(messages, sort_keys=True).encode()
        ).hexdigest()
        cache_key = f"llm:response:{prompt_hash}:{temperature}"
        cached = self.redis.get(cache_key)
        if cached:
            return cached
        return None

    def set_llm_response(self, messages: list, response: str, temperature: float = 0.7, ttl: int = 86400):
        prompt_hash = hashlib.md5(
            json.dumps(messages, sort_keys=True).encode()
        ).hexdigest()
        cache_key = f"llm:response:{prompt_hash}:{temperature}"
        self.redis.setex(cache_key, ttl, response)

    def invalidate_chapter(self, novel_id: str, chapter_index: int):
        self.redis.delete(f"chapter:{novel_id}:{chapter_index}:content")
        self.redis.delete(f"chapter:{novel_id}:{chapter_index}:outline")

    def invalidate_novel_settings(self, novel_name: str):
        self.redis.delete(f"novel:{novel_name}:settings")
