"""
E2E 测试沙盒：内存数据库、Celery 同步执行、Mock LLM，不调用真实 API。
"""
from __future__ import annotations

import os
import sys
import json
import types
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 在导入任何使用 DATABASE_URL 的模块之前设置环境。
# db_service 使用同步 create_engine，必须用 sqlite:/// 而非 sqlite+aiosqlite:///
# E2E 强制覆盖，避免 .env / 外层传入的 aiosqlite URL 导致 create_engine 报错
project_root = Path(__file__).resolve().parent.parent.parent
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import fakeredis


# ----- 内存数据库 -----
def _make_test_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(scope="session")
def e2e_engine():
    """会话级内存引擎，建表一次。避免加载 app 的 async database，先 mock 再取 Base。"""
    engine = _make_test_engine()
    with patch("sqlalchemy.ext.asyncio.create_async_engine", MagicMock(return_value=MagicMock())):
        from src.core.database import Base
        import src.api.models  # noqa: F401
        import src.core.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def e2e_db(e2e_engine):
    """每个测试独立的 DB：回滚或重建表以隔离。"""
    from src.core.database import Base
    import src.api.models  # noqa: F401
    import src.core.models  # noqa: F401
    Base.metadata.drop_all(bind=e2e_engine)
    Base.metadata.create_all(bind=e2e_engine)
    yield e2e_engine


@pytest.fixture(scope="function")
def patch_db_service(e2e_db):
    """让 DatabaseService 使用 E2E 内存库。导入前强制 os.getenv('DATABASE_URL') 返回同步 SQLite，避免 db_service 模块级 create_engine 用 aiosqlite 报错。"""
    _real_getenv = os.getenv
    def _e2e_getenv(key, default=None):
        if key == "DATABASE_URL":
            return "sqlite:///:memory:"
        return _real_getenv(key, default)
    with patch("os.getenv", side_effect=_e2e_getenv):
        from src.core import db_service
    SessionLocal = sessionmaker(bind=e2e_db, autocommit=False, autoflush=False)
    original_engine = getattr(db_service, "engine", None)
    original_session = getattr(db_service, "SessionLocal", None)
    db_service.engine = e2e_db
    db_service.SessionLocal = SessionLocal
    try:
        yield db_service
    finally:
        if original_engine is not None:
            db_service.engine = original_engine
        if original_session is not None:
            db_service.SessionLocal = original_session


# ----- Celery 同步模式 -----
@pytest.fixture(scope="module", autouse=True)
def celery_eager():
    """E2E 下任务同步执行，不依赖 Redis/Worker。缺少 celery 时跳过全模块。"""
    pytest.importorskip("celery", reason="需要安装 celery 才能运行 E2E（请在项目环境中执行）")
    from src.core.celery_config import celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = False


# ----- Mock LLM：按 Prompt 关键词返回不同内容 -----
def _smart_mock_chat(messages, temperature=None, max_tokens=None, **kwargs):
    """根据最后一条 user 内容或 system 内容决定返回格式。"""
    text = ""
    for m in reversed(messages or []):
        c = (m.get("content") or "")
        text = (c + " " + text).strip()
        if c:
            break
    text_lower = text.lower()
    # 大纲：需含 scenes 的合法 JSON
    if "architect" in text_lower or ("json" in text_lower and "scene" in text_lower):
        out = {
            "scenes": [
                {"id": "s1", "summary": "萧炎来到斗气大陆，踏入云岚宗。", "key_characters": ["萧炎"], "expected_words": 1500},
                {"id": "s2", "summary": "与纳兰嫣然对峙，定下三年之约。", "key_characters": ["萧炎", "纳兰嫣然"], "expected_words": 1200},
            ]
        }
        return json.dumps(out, ensure_ascii=False)
    # 正文：纯文本
    if "writer" in text_lower or "scene" in text_lower and "summary" in text_lower and "chapter" in text_lower:
        return "萧炎深吸一口气，迈步走入大殿。殿内斗气涌动，众人目光齐聚。\n\n三年之约，今日便在此了结。"
    # 审查：通过
    if "censor" in text_lower or "敏感" in text_lower or "合规" in text_lower:
        return json.dumps({"is_sensitive": False, "reason": "PASS", "severity": "low"}, ensure_ascii=False)
    # 审稿：高分通过
    if "critic" in text_lower or "审稿" in text_lower or "critique" in text_lower:
        return json.dumps({
            "score": 85,
            "suggestions": "节奏可再紧凑一些。",
            "critique": "Good.",
            "passed": True,
            "details": {},
        }, ensure_ascii=False)
    # 默认：简单 JSON 兜底（避免 parse_json 报错）
    return json.dumps({"scenes": [{"id": "s1", "summary": "默认场景", "key_characters": [], "expected_words": 1000}]}, ensure_ascii=False)


@pytest.fixture
def mock_llm():
    """拦截 LLMClient.chat，使用智能 Mock 返回值。"""
    with patch("src.core.llm.LLMClient.chat", side_effect=_smart_mock_chat):
        yield


@pytest.fixture
def mock_prompts():
    """避免 E2E 读库中 prompt 模板；返回最小可用 YAML。"""
    minimal_yaml = "system: ''\nuser: '占位'"
    with patch("src.core.prompt_loader.resolve_prompt", return_value=minimal_yaml), \
         patch("src.core.prompt_loader.get_fiction_system_prompt", return_value=""):
        yield


# ----- Fake Redis + 覆盖 tasks_new 的 _init_components -----
@pytest.fixture
def fake_redis():
    r = fakeredis.FakeStrictRedis(decode_responses=True)
    yield r
    r.flushall()


def _make_fake_dispatcher_module():
    """造一个假的 src.core.dispatcher 模块，供 tasks_new 导入，避免 workflows->controller->workflows 循环。"""
    if "src.core.dispatcher" in sys.modules:
        return
    m = types.ModuleType("src.core.dispatcher")
    class _FakeDispatcher:
        def __init__(self, *args, **kwargs): pass
        def handle_event(self, payload): pass
    m.Dispatcher = _FakeDispatcher
    sys.modules["src.core.dispatcher"] = m


@pytest.fixture
def e2e_components(fake_redis, mock_llm, mock_prompts, patch_db_service):
    """
    组装 E2E 环境：Fake Redis、Mock LLM、Mock Prompts、内存 DB，
    并令 tasks_new 使用的 state_manager / llm / file_manager 来自本沙盒。
    """
    _make_fake_dispatcher_module()
    from src.core.state_manager import StateManager
    from src.core.workflow_lock import WorkflowLock

    state_manager = StateManager()
    state_manager.redis_client = fake_redis
    workflow_lock = WorkflowLock(fake_redis)
    dispatcher = sys.modules["src.core.dispatcher"].Dispatcher(state_manager)

    # Mock LLM：不实例化真实 LLMClient，避免 API Key / 网络
    llm_client = MagicMock()
    llm_client.chat = MagicMock(side_effect=_smart_mock_chat)

    # 使用 Mock 的 file_manager，handlers 在 E2E 中不写真实文件
    file_manager = MagicMock()
    file_manager.get_chapter_path = MagicMock(return_value=Path(project_root) / "workspace" / "test_novel" / "chapters" / "chapter_001")
    file_manager.load_content = MagicMock(return_value="")
    file_manager.save_content = MagicMock()
    file_manager.init_chapter = MagicMock(return_value=Path(project_root) / "workspace" / "test_novel" / "chapters" / "chapter_001")

    def _init_components():
        return state_manager, dispatcher, llm_client, file_manager, workflow_lock

    def _resolve_prompt(key, workflow_type=None):
        # 按 key 返回包含关键词的模板，供 _smart_mock_chat 识别；占位符需与 format_prompt_template 一致
        tpl = "system: ''\nuser: '{ctx}'"
        if key == "architect":
            return tpl.format(ctx="architect generate outline in json with scenes")
        if key == "writer_builder":
            return tpl.format(ctx="writer write scene summary chapter")
        if key == "critique_handler":
            return tpl.format(ctx="critic critique content score")
        if key == "censor":
            return "system: ''\nuser: 'censor check {content}'"
        return tpl.format(ctx="占位")

    # 在 handler 内使用的名字上打补丁（handler 已 from prompt_loader import resolve_prompt）
    with patch("src.workers.tasks_new._init_components", side_effect=_init_components), \
         patch("src.workers.tasks_new._check_agent_disabled", return_value=False), \
         patch("src.workers.handlers.architect.resolve_prompt", side_effect=_resolve_prompt), \
         patch("src.workers.handlers.architect.get_fiction_system_prompt", return_value=""), \
         patch("src.workers.handlers.writer.resolve_prompt", side_effect=_resolve_prompt), \
         patch("src.workers.handlers.writer.get_fiction_system_prompt", return_value=""), \
         patch("src.workers.handlers.critic.resolve_prompt", side_effect=_resolve_prompt), \
         patch("src.workers.handlers.critic.get_fiction_system_prompt", return_value=""), \
         patch("src.workers.handlers.censor.resolve_prompt", side_effect=_resolve_prompt), \
         patch("src.core.prompt_loader.resolve_prompt", side_effect=_resolve_prompt), \
         patch("src.core.prompt_loader.get_fiction_system_prompt", return_value=""):
        # 重置 tasks_new 的全局变量，迫使下次调用用我们的 _init_components
        import src.workers.tasks_new as tasks_new
        tasks_new.state_manager = None
        tasks_new.dispatcher = None
        tasks_new.llm_client = None
        tasks_new.file_manager = None
        tasks_new.workflow_lock = None
        yield {
            "state_manager": state_manager,
            "dispatcher": dispatcher,
            "llm_client": llm_client,
            "file_manager": file_manager,
            "workflow_lock": workflow_lock,
        }
