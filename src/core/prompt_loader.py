"""
从数据库 prompt_templates 表读取提示词模板，供各 Agent/Worker 使用。
约定：仅使用数据库，不读 YAML、不做缓存，每次调用均请求数据库。
"""
from typing import Optional
import os
import logging
from pathlib import Path

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


def get_prompt_content(key: str, workflow_type: Optional[str] = None) -> Optional[str]:
    """
    从 prompt_templates 表按 key（及可选 workflow_type）取 content。每次调用都会查询数据库，不做缓存。
    - workflow_type 为 None 或空：只查 (key, '') 的默认模板。
    - workflow_type 非空：先查 (key, workflow_type)，若无则回退到 (key, '')。
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
            wt = (workflow_type or "").strip()
            if wt:
                row = conn.execute(
                    text(
                        "SELECT content, is_active FROM prompt_templates WHERE key = :key AND workflow_type = :wt"
                    ),
                    {"key": key, "wt": wt},
                ).fetchone()
                if row:
                    content, is_active = row
                    if is_active is not False and content:
                        return content
                # 回退到默认
                row = conn.execute(
                    text(
                        "SELECT content, is_active FROM prompt_templates WHERE key = :key AND (workflow_type = '' OR workflow_type IS NULL)"
                    ),
                    {"key": key},
                ).fetchone()
            else:
                row = conn.execute(
                    text(
                        "SELECT content, is_active FROM prompt_templates WHERE key = :key AND (workflow_type = '' OR workflow_type IS NULL)"
                    ),
                    {"key": key},
                ).fetchone()
            if not row:
                return None
            content, is_active = row
            if is_active is False:
                return None
            return content if content else None
    except Exception as e:
        logger.debug("get_prompt_content(%s, workflow_type=%s) db error: %s", key, workflow_type, e)
        return None


def resolve_prompt(key: str, workflow_type: Optional[str] = None) -> str:
    """
    按 key（及可选 workflow_type）从数据库读取提示词，不读 YAML、无回退。
    若指定 workflow_type，则优先使用该工作流对应模板，否则使用默认模板。
    若 key 不存在或内容为空，抛出 ValueError。
    """
    content = get_prompt_content(key, workflow_type=workflow_type)
    if content is not None and content.strip():
        return content.strip()
    raise ValueError(
        f"提示词 key={key!r}（workflow_type={workflow_type or ''!r}）在数据库中不存在或内容为空，请先在「提示词助手」或数据库中配置。"
    )


def format_prompt_template(template: str, **kwargs: object) -> str:
    """
    仅替换 {key} 占位符，不解析其它花括号，避免模板中 JSON 示例等被 str.format 误解析导致 KeyError。
    用于所有从数据库读取的提示词模板的变量替换。
    """
    out = template
    for k, v in kwargs.items():
        out = out.replace("{" + k + "}", str(v) if v is not None else "")
    return out


def get_fiction_system_prompt() -> str:
    """
    仅从数据库 key=fiction_system 读取「小说/创作合规」系统提示词。
    若库中未配置或内容为空，抛出 ValueError。
    """
    return resolve_prompt("fiction_system")
