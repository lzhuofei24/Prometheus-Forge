from pydantic_settings import BaseSettings
from typing import Optional
import os
from pathlib import Path


class AppSettings(BaseSettings):
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    database_url: Optional[str] = None
    
    openrouter_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    siliconflow_api_key: Optional[str] = None
    
    api_key: Optional[str] = None
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }


_settings_instance: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = AppSettings()
    return _settings_instance


def reload_settings():
    global _settings_instance
    _settings_instance = AppSettings()
    return _settings_instance
