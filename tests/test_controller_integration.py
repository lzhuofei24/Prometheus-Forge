import pytest
import json
import redis
import time
from unittest.mock import patch, MagicMock
from src.core.controller import CentralController
from src.core.state_manager import StateManager
from src.core.app_settings import get_settings


@pytest.fixture
def test_redis():
    settings = get_settings()
    client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=True
    )
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def test_state_manager(test_redis):
    return StateManager(
        redis_host=test_redis.connection_pool.connection_kwargs['host'],
        redis_port=test_redis.connection_pool.connection_kwargs['port'],
        redis_db=test_redis.connection_pool.connection_kwargs['db']
    )


@pytest.fixture
def controller(test_state_manager, test_redis):
    with patch('src.core.controller.celery_app') as mock_celery:
        controller = CentralController(test_state_manager, test_redis)
        controller.celery = mock_celery
        controller.running = False
        return controller


class TestControllerWorkflow:
    def test_full_workflow_architect_to_writer(self, controller, test_redis):
        workflow_id = "test-workflow-1"
        
        test_state_manager = controller.state_manager
        test_state_manager.init_workflow(workflow_id, {
            "novel_name": "测试小说",
            "chapter_num": 1,
            "status": "started",
            "revision_count": 0
        })
        
        payload = {
            "version": "1.0",
            "workflow_id": workflow_id,
            "source": "architect",
            "status": "SUCCESS",
            "event_type": "outline_generated",
            "data": {"outline": "测试大纲"},
            "timestamp": "2026-01-25T10:00:00"
        }
        
        test_redis.rpush("architect_completed", json.dumps(payload, ensure_ascii=False))
        
        controller.handle_completion("architect_completed", json.dumps(payload))
        
        assert controller.celery.send_task.called
        call_args = controller.celery.send_task.call_args
        assert call_args[0][0] == "writer.write_content"
        assert call_args[1]["queue"] == "writer_pending"

    def test_workflow_critic_high_score(self, controller, test_redis):
        workflow_id = "test-workflow-2"
        
        test_state_manager = controller.state_manager
        test_state_manager.init_workflow(workflow_id, {
            "novel_name": "测试小说",
            "chapter_num": 1,
            "status": "started",
            "revision_count": 0
        })
        
        payload = {
            "version": "1.0",
            "workflow_id": workflow_id,
            "source": "critic",
            "status": "SUCCESS",
            "event_type": "critique_completed",
            "data": {"score": 85, "advice": "很好"},
            "timestamp": "2026-01-25T10:00:00"
        }
        
        controller.handle_completion("critic_completed", json.dumps(payload))
        
        calls = controller.celery.send_task.call_args_list
        target_agents = [call[1]["queue"].replace("_pending", "") for call in calls]
        assert "media" in target_agents
        assert "knowledge" in target_agents

    def test_workflow_critic_low_score_rewrite(self, controller, test_redis):
        workflow_id = "test-workflow-3"
        
        test_state_manager = controller.state_manager
        test_state_manager.init_workflow(workflow_id, {
            "novel_name": "测试小说",
            "chapter_num": 1,
            "status": "started",
            "revision_count": 0,
            "critique_comments": "需要改进"
        })
        
        payload = {
            "version": "1.0",
            "workflow_id": workflow_id,
            "source": "critic",
            "status": "SUCCESS",
            "event_type": "critique_completed",
            "data": {"score": 60, "advice": "需要改进"},
            "timestamp": "2026-01-25T10:00:00"
        }
        
        controller.handle_completion("critic_completed", json.dumps(payload))
        
        assert controller.celery.send_task.called
        call_args = controller.celery.send_task.call_args
        assert call_args[0][0] == "writer.revise_content"
        assert call_args[1]["queue"] == "writer_pending"

    def test_workflow_censor_failed_stops(self, controller, test_redis):
        workflow_id = "test-workflow-4"
        
        test_state_manager = controller.state_manager
        test_state_manager.init_workflow(workflow_id, {
            "novel_name": "测试小说",
            "chapter_num": 1,
            "status": "started"
        })
        
        payload = {
            "version": "1.0",
            "workflow_id": workflow_id,
            "source": "censor",
            "status": "SUCCESS",
            "event_type": "content_censored",
            "data": {"is_sensitive": True, "reason": "敏感内容"},
            "timestamp": "2026-01-25T10:00:00"
        }
        
        controller.handle_completion("censor_completed", json.dumps(payload))
        
        assert not controller.celery.send_task.called
        
        state = test_state_manager.get_state(workflow_id)
        assert state.get("status") != "completed"
