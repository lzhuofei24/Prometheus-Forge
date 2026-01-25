import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from typing import AsyncGenerator
import fakeredis
from unittest.mock import AsyncMock, patch, MagicMock
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.api.main import app
from src.core.database import Base, get_db
from src.core.state_manager import StateManager


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    future=True,
    connect_args={
        "check_same_thread": False,
    },
    poolclass=StaticPool,
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def override_get_db(db_session):
    async def _get_db():
        yield db_session
    return _get_db


@pytest_asyncio.fixture
async def async_client(override_get_db):
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def redis_client():
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    fake_redis.flushall()
    yield fake_redis
    fake_redis.flushall()


@pytest.fixture
def state_manager(redis_client):
    manager = StateManager()
    manager.redis_client = redis_client
    return manager


@pytest.fixture
def mock_llm_client():
    def _mock_chat(messages, temperature=None, max_tokens=None, **kwargs):
        return "Mocked AI Response"
    
    with patch("src.core.llm.LLMClient.chat", side_effect=_mock_chat):
        yield


@pytest.fixture
def mock_llm_client_instance():
    mock_instance = MagicMock()
    mock_instance.chat = MagicMock(return_value="Mocked AI Response")
    mock_instance.provider = "test"
    mock_instance.model = "test-model"
    mock_instance.api_key = "test-key"
    mock_instance.base_url = "http://test"
    return mock_instance


@pytest.fixture
def mock_celery_task():
    with patch("src.workers.tasks_new.task_generate_outline.delay") as mock_outline, \
         patch("src.workers.tasks_new.task_write_content.delay") as mock_write, \
         patch("src.workers.tasks_new.task_critique_content.delay") as mock_critique, \
         patch("src.workers.tasks_new.task_revise_content.delay") as mock_revise, \
         patch("src.workers.tasks_new.task_generate_media.delay") as mock_media:
        yield {
            "outline": mock_outline,
            "write": mock_write,
            "critique": mock_critique,
            "revise": mock_revise,
            "media": mock_media
        }
