import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from abc import ABC, abstractmethod
from src.core.events import EventType, EventSource, AuditLogEntry, EventPayload
from src.core.state_manager import StateManager
from src.core.dispatcher import Dispatcher
from src.core.structured_logger import get_structured_logger

logger = logging.getLogger(__name__)


class BaseAgentHandler(ABC):
    """
    抽象基类：所有 Agent Handler 的模板
    
    实现模板方法模式，定义标准执行流程：
    1. _pre_process: 记录 TASK_STARTED 审计日志
    2. _process: 子类实现具体业务逻辑
    3. _post_process: 更新状态、记录 TASK_COMPLETED、发送完成事件
    4. _handle_error: 捕获异常、记录 TASK_FAILED、发送失败事件
    """
    
    def __init__(self, state_manager: StateManager, dispatcher: Dispatcher):
        self.state_manager = state_manager
        self.dispatcher = dispatcher

    def execute(self, workflow_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        模板方法：标准执行流程
        在开始执行前设置 agent:{name}:processing = workflow_id，结束时在 finally 中删除，供监控 API 查询。
        """
        agent_name = self._get_agent_name()
        structured_logger = get_structured_logger(__name__, workflow_id=workflow_id, agent=agent_name)
        processing_key = f"agent:{agent_name}:processing" if agent_name else None

        try:
            if processing_key:
                try:
                    self.state_manager.redis_client.setex(processing_key, 3600, workflow_id)
                except Exception as e:
                    logger.warning("Failed to set processing key %s: %s", processing_key, e)

            self._pre_process(workflow_id, input_data)
            structured_logger.info("task_started", extra_data=input_data)

            output_data = self._process(workflow_id, input_data)

            self._post_process(workflow_id, output_data)
            structured_logger.info("task_completed", extra_data={"result": output_data})

            return output_data

        except Exception as e:
            self._handle_error(workflow_id, e)
            structured_logger.error("task_failed", extra_data={"error": str(e)}, exc_info=True)
            raise
        finally:
            if processing_key:
                try:
                    self.state_manager.redis_client.delete(processing_key)
                except Exception as e:
                    logger.warning("Failed to delete processing key %s: %s", processing_key, e)

    def _pre_process(self, workflow_id: str, input_data: Dict[str, Any]) -> None:
        """
        Step 1: 预处理 - 记录 TASK_STARTED 审计日志
        """
        self.state_manager.add_audit_log(
            workflow_id,
            AuditLogEntry(
                workflow_id=workflow_id,
                source=self._get_source(),
                event_type=EventType.TASK_STARTED,
                details={"input": input_data}
            )
        )

    @abstractmethod
    def _process(self, workflow_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step 2: 核心处理逻辑（子类必须实现）
        
        Args:
            workflow_id: 工作流 ID
            input_data: 输入数据
            
        Returns:
            处理结果字典
        """
        pass

    def _post_process(self, workflow_id: str, output_data: Dict[str, Any]) -> None:
        """
        Step 3: 后处理
        - 更新 Redis 状态
        - 记录 TASK_COMPLETED 审计日志
        - 将任务移到已消费队列
        - 发送完成事件
        """
        self.state_manager.update_state(workflow_id, output_data)
        
        self.state_manager.add_audit_log(
            workflow_id,
            AuditLogEntry(
                workflow_id=workflow_id,
                source=self._get_source(),
                event_type=EventType.TASK_COMPLETED,
                details={"result": output_data}
            )
        )

        event_payload = EventPayload(
            workflow_id=workflow_id,
            event_type=self._get_completion_event_type(),
            data=output_data,
            source=self._get_source()
        )
        self.dispatcher.handle_event(event_payload)
        
        agent_name = self._get_agent_name()
        if agent_name:
            completed_queue = f"{agent_name}_completed"
            payload = {
                "version": "1.0",
                "workflow_id": workflow_id,
                "source": agent_name,
                "status": "SUCCESS",
                "event_type": self._get_completion_event_type().value,
                "data": output_data,
                "timestamp": datetime.now().isoformat()
            }
            try:
                self.state_manager.redis_client.rpush(
                    completed_queue,
                    json.dumps(payload, ensure_ascii=False)
                )
                logger.debug(f"Pushed completion to {completed_queue} for workflow {workflow_id}")
            except Exception as e:
                logger.error(f"Failed to push to completed queue: {e}", exc_info=True)
    
    def _get_agent_name(self) -> Optional[str]:
        """从事件源获取 agent 名称"""
        source = self._get_source()
        if source == EventSource.AGENT_ARCHITECT:
            return "architect"
        elif source == EventSource.AGENT_WRITER:
            return "writer"
        elif source == EventSource.AGENT_CRITIC:
            return "critic"
        elif source == EventSource.AGENT_MEDIA:
            return "media"
        elif source == EventSource.AGENT_KNOWLEDGE:
            return "knowledge"
        elif source == EventSource.AGENT_CENSOR:
            return "censor"
        return None

    def _handle_error(self, workflow_id: str, error: Exception) -> None:
        """
        Step 4: 错误处理
        - 记录 TASK_FAILED 审计日志
        - 发送失败事件
        """
        error_msg = str(error)
        logger.error(f"Task failed for workflow {workflow_id}: {error_msg}", exc_info=True)
        
        self.state_manager.add_audit_log(
            workflow_id,
            AuditLogEntry(
                workflow_id=workflow_id,
                source=self._get_source(),
                event_type=EventType.TASK_FAILED,
                details={"error": error_msg},
                error=error_msg
            )
        )

        event_payload = EventPayload(
            workflow_id=workflow_id,
            event_type=EventType.TASK_FAILED,
            data={"error": error_msg},
            source=self._get_source()
        )
        self.dispatcher.handle_event(event_payload)

    @abstractmethod
    def _get_source(self) -> EventSource:
        """返回 Agent 的事件源"""
        pass

    @abstractmethod
    def _get_completion_event_type(self) -> EventType:
        """返回完成事件类型"""
        pass
