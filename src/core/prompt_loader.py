"""
从数据库 prompt_templates 表读取提示词模板，供各 Agent/Worker 使用。
优先使用数据库；若 key 不存在则从本地 YAML 回退（若提供了 fallback 路径）。
"""
from pathlib import Path
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

# 与 db_service 一致的同步 DB 路径
def _get_sync_db_url() -> str:
    raw = os.getenv("DATABASE_URL", "").strip()
    if raw.startswith("sqlite+aiosqlite:///"):
        return "sqlite:///" + raw.replace("sqlite+aiosqlite:///", "", 1)
    if raw.startswith("sqlite:///"):
        return raw
    if not raw:
        root = Path(__file__).resolve().parent.parent.parent
        return f"sqlite:///{root / 'data' / 'novel_content_db' / 'prometheus_forge.db'}"
    return raw


def get_prompt_content(key: str) -> Optional[str]:
    """
    从 prompt_templates 表按 key 取 content。
    若不存在或 is_active=False，返回 None。
    """
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import StaticPool
        url = _get_sync_db_url()
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False} if "sqlite" in url else {},
            poolclass=StaticPool if "sqlite" in url else None,
        )
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT content, is_active FROM prompt_templates WHERE key = :key"),
                {"key": key}
            ).fetchone()
            if not row:
                return None
            content, is_active = row
            if is_active is False:
                return None
            return content if content else None
    except Exception as e:
        logger.debug("get_prompt_content(%s) db error: %s", key, e)
        return None


def resolve_prompt(key: str, fallback_yaml_path: Optional[Path] = None) -> str:
    """
    解析提示词内容：优先数据库 prompt_templates.key，否则从 fallback_yaml_path 读文件。
    若两者都无可用内容，则抛出 FileNotFoundError 或 ValueError。
    """
    content = get_prompt_content(key)
    if content is not None and content.strip():
        return content.strip()
    if fallback_yaml_path is not None and fallback_yaml_path.exists():
        with open(fallback_yaml_path, "r", encoding="utf-8") as f:
            return f.read()
    if content is not None:
        return content.strip() if content else ""
    raise FileNotFoundError(
        f"提示词 key={key!r} 在数据库中不存在且未提供有效回退路径: {fallback_yaml_path}"
    )


def get_fiction_system_prompt() -> str:
    """
    返回「小说/创作合规」系统提示词。
    优先使用 DB key fiction_system；若无则返回内置默认。
    """
    default = """你是一位专业的文学编辑和小说创作助手。

【合规要求，必须遵守】
1. 所有产出必须符合中华人民共和国法律法规及内容安全与出版规范，禁止任何非法、政治敏感、色情、暴力恐怖、违法犯罪或违背公序良俗的内容。
2. 内容健康向上，适合全年龄或合规分级受众；不涉及真实政党、敏感历史事件或违法犯罪细节。
3. 在合规前提下进行客观分析与文学润色，严格遵循用户指令（如 JSON 格式），并**使用简体中文**回复。
"""
    content = get_prompt_content("fiction_system")
    return (content and content.strip()) or default
