import logging
from typing import Dict, Any
from src.core.events import EventType, EventSource, EventPayload, AuditLogEntry
from src.core.state_manager import StateManager

logger = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, state_manager: StateManager):
        self.state_manager = state_manager

    def handle_event(self, payload: EventPayload):
        workflow_id = payload.workflow_id
        event_type = payload.event_type
        data = payload.data

        self.state_manager.add_audit_log(
            workflow_id,
            AuditLogEntry(
                workflow_id=workflow_id,
                source=EventSource.DISPATCHER,
                event_type=EventType.TASK_DISPATCHED,
                details={
                    "triggered_by": event_type,
                    "data": data
                }
            )
        )

        if event_type == EventType.WORKFLOW_STARTED:
            self._handle_workflow_started(workflow_id, data)
        elif event_type == EventType.OUTLINE_GENERATED:
            self._handle_outline_generated(workflow_id, data)
        elif event_type == EventType.CONTENT_WRITTEN:
            self._handle_content_written(workflow_id, data)
        elif event_type == EventType.CRITIQUE_COMPLETED:
            self._handle_critique_completed(workflow_id, data)
        elif event_type == EventType.CRITIQUE_FAILED:
            self._handle_critique_failed(workflow_id, data)
        elif event_type == EventType.MEDIA_GENERATED:
            self._handle_media_generated(workflow_id, data)
        elif event_type == EventType.KNOWLEDGE_UPDATED:
            self._handle_knowledge_updated(workflow_id, data)
        elif event_type == EventType.TASK_FAILED:
            self._handle_task_failed(workflow_id, data)
        else:
            logger.warning(f"Unknown event type: {event_type}")

    def _handle_workflow_started(self, workflow_id: str, data: Dict[str, Any]):
        novel_name = data.get("novel_name")
        chapter_num = data.get("chapter_num")
        
        state = self.state_manager.get_state(workflow_id)
        if not state:
            self.state_manager.init_workflow(workflow_id, {
                "novel_name": novel_name,
                "chapter_num": chapter_num,
                "status": "started",
                "revision_count": 0
            })
        
        logger.info(f"Workflow {workflow_id} started. Task dispatch will be handled by central controller.")

    def _handle_outline_generated(self, workflow_id: str, data: Dict[str, Any]):
        outline = data.get("outline")
        self.state_manager.update_state(workflow_id, {"outline": outline})
        
        logger.info(f"Outline generated for workflow {workflow_id}. Task dispatch will be handled by central controller.")

    def _handle_content_written(self, workflow_id: str, data: Dict[str, Any]):
        content = data.get("content")
        self.state_manager.update_state(workflow_id, {"draft_content": content})
        
        logger.info(f"Content written for workflow {workflow_id}. Task dispatch will be handled by central controller.")

    def _handle_critique_completed(self, workflow_id: str, data: Dict[str, Any]):
        score = data.get("score", 0)
        advice = data.get("advice", "")
        
        self.state_manager.update_state(workflow_id, {
            "critique_score": score,
            "critique_comments": advice
        })

        state = self.state_manager.get_state(workflow_id)
        revision_count = state.get("revision_count", 0)
        passed = data.get("passed", score >= 75)
        
        logger.info(f"Critique completed for workflow {workflow_id}: score={score}, passed={passed}. Task dispatch will be handled by central controller.")

    def _handle_critique_failed(self, workflow_id: str, data: Dict[str, Any]):
        """处理审稿失败事件"""
        self.state_manager.update_state(workflow_id, {
            "status": "failed",
            "error": "Critique failed"
        })

    def _handle_media_generated(self, workflow_id: str, data: Dict[str, Any]):
        """处理媒体生成完成事件"""
        image_url = data.get("image_url")
        self.state_manager.update_state(workflow_id, {"media_url": image_url})

    def _handle_knowledge_updated(self, workflow_id: str, data: Dict[str, Any]):
        """处理知识库更新完成事件"""
        entities_count = data.get("entities_extracted", 0)
        logger.info(f"Knowledge updated for workflow {workflow_id}: {entities_count} entities extracted")

    def _handle_content_censored(self, workflow_id: str, data: Dict[str, Any]):
        is_sensitive = data.get("is_sensitive", False)
        reason = data.get("reason", "")
        self.state_manager.update_state(workflow_id, {
            "censor_result": {
                "is_sensitive": is_sensitive,
                "reason": reason,
                "checked_by": data.get("checked_by", "unknown")
            }
        })
        logger.info(f"Content censored for workflow {workflow_id}: is_sensitive={is_sensitive}")

    def _handle_task_failed(self, workflow_id: str, data: Dict[str, Any]):
        error = data.get("error", "Unknown error")
        self.state_manager.update_state(workflow_id, {
            "status": "failed",
            "error": error
        })
