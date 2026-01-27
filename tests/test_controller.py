import pytest
import json
import redis
from unittest.mock import Mock, patch, MagicMock
from src.core.controller import CentralController, RoutingRule
from src.core.state_manager import StateManager


class TestRoutingRule:
    def test_rule_with_condition_true(self):
        rule = RoutingRule(
            source_agent="test",
            next_agents=["agent1"],
            condition=lambda data: data.get("score", 0) >= 75
        )
        result = rule.decide({"score": 80})
        assert result == ["agent1"]

    def test_rule_with_condition_false(self):
        rule = RoutingRule(
            source_agent="test",
            next_agents=["agent1"],
            condition=lambda data: data.get("score", 0) >= 75,
            else_agents=["agent2"]
        )
        result = rule.decide({"score": 60})
        assert result == ["agent2"]

    def test_rule_without_condition(self):
        rule = RoutingRule(
            source_agent="test",
            next_agents=["agent1"]
        )
        result = rule.decide({})
        assert result == ["agent1"]


class TestCentralController:
    @pytest.fixture
    def mock_state_manager(self):
        manager = Mock(spec=StateManager)
        manager.get_state.return_value = {
            "novel_name": "测试小说",
            "chapter_num": 1,
            "outline": "测试大纲",
            "revision_count": 0,
            "workflow_type": "generate_chapter",
        }
        manager.update_state = Mock()
        manager.redis_client = Mock(spec=redis.Redis)
        return manager

    @pytest.fixture
    def mock_redis(self):
        return Mock(spec=redis.Redis)

    @pytest.fixture
    def controller(self, mock_state_manager, mock_redis):
        with patch('src.core.controller.celery_app') as mock_celery:
            controller = CentralController(mock_state_manager, mock_redis)
            controller.celery = mock_celery
            return controller

    def test_routing_architect_to_writer(self, controller):
        next_agents = controller.decide_next_step("test-wf-1", "architect", {})
        assert "writer" in next_agents

    def test_routing_writer_to_censor(self, controller):
        next_agents = controller.decide_next_step("test-wf-1", "writer", {})
        assert "censor" in next_agents

    def test_routing_censor_passed_to_critic(self, controller):
        next_agents = controller.decide_next_step("test-wf-1", "censor", {"is_sensitive": False})
        assert "critic" in next_agents

    def test_routing_censor_failed_stops(self, controller):
        next_agents = controller.decide_next_step("test-wf-1", "censor", {"is_sensitive": True})
        assert next_agents == []

    def test_routing_critic_high_score_to_media(self, controller):
        """critic 高分 -> media；knowledge 已脱离工作流，仅支持手动索引管理。"""
        next_agents = controller.decide_next_step("test-wf-1", "critic", {"score": 80})
        assert "media" in next_agents

    def test_routing_critic_low_score_to_writer(self, controller):
        next_agents = controller.decide_next_step("test-wf-1", "critic", {"score": 60})
        assert "writer" in next_agents

    def test_handle_completion_success(self, controller, mock_redis):
        payload = {
            "version": "1.0",
            "workflow_id": "test-workflow-1",
            "source": "architect",
            "status": "SUCCESS",
            "data": {"outline": "测试大纲"},
            "timestamp": "2026-01-25T10:00:00"
        }
        
        controller.handle_completion("architect_completed", json.dumps(payload))
        
        controller.state_manager.update_state.assert_called()
        controller.celery.send_task.assert_called_once()

    def test_handle_completion_failure(self, controller, mock_redis):
        payload = {
            "version": "1.0",
            "workflow_id": "test-workflow-1",
            "source": "architect",
            "status": "FAILED",
            "error": "Test error",
            "timestamp": "2026-01-25T10:00:00"
        }
        
        controller.handle_completion("architect_completed", json.dumps(payload))
        
        controller.state_manager.update_state.assert_called_once()
        call_args = controller.state_manager.update_state.call_args[0]
        assert call_args[0] == "test-workflow-1"
        assert call_args[1]["status"] == "failed"

    def test_dispatch_task_architect(self, controller):
        controller.dispatch_task("test-workflow-1", "architect")
        controller.celery.send_task.assert_called_once()
        call_args = controller.celery.send_task.call_args
        assert call_args[0][0] == "architect.generate_outline"
        assert call_args[1]["queue"] == "architect_pending"

    def test_dispatch_task_writer_first_time(self, controller):
        controller.state_manager.get_state.return_value = {
            "novel_name": "测试小说",
            "chapter_num": 1,
            "revision_count": 0
        }
        controller.dispatch_task("test-workflow-1", "writer")
        controller.celery.send_task.assert_called_once()
        call_args = controller.celery.send_task.call_args
        assert call_args[0][0] == "writer.write_content"

    def test_dispatch_task_writer_revision(self, controller):
        controller.state_manager.get_state.return_value = {
            "novel_name": "测试小说",
            "chapter_num": 1,
            "revision_count": 1,
            "advice": "需要改进"
        }
        controller.dispatch_task("test-workflow-1", "writer")
        controller.celery.send_task.assert_called_once()
        call_args = controller.celery.send_task.call_args
        assert call_args[0][0] == "writer.revise_content"


class TestControllerIntegration:
    @pytest.fixture
    def real_redis(self):
        from src.core.app_settings import get_settings
        settings = get_settings()
        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True
        )
        yield client
        client.flushdb()

    def test_completed_queue_write_and_read(self, real_redis):
        """验证 Redis 队列可写可读，使用独立 key 避免与业务队列或并发测试冲突。"""
        queue_name = "test:controller:queue:write_read"
        payload = {
            "version": "1.0",
            "workflow_id": "test-workflow-1",
            "source": "architect",
            "status": "SUCCESS",
            "data": {"outline": "测试大纲"},
            "timestamp": "2026-01-25T10:00:00"
        }
        n = real_redis.rpush(queue_name, json.dumps(payload, ensure_ascii=False))
        assert n == 1, "rpush 应返回 1"
        result = real_redis.blpop([queue_name], timeout=2)
        assert result is not None, "blpop 应得到刚写入的元素"
        queue, data = result
        parsed = json.loads(data)
        assert parsed["workflow_id"] == "test-workflow-1"
        assert parsed["status"] == "SUCCESS"
