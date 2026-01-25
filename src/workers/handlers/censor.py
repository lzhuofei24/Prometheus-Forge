import logging
import yaml
from typing import Dict, Any, Optional
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource
from src.core.llm import LLMClient
from src.core.prompt_loader import resolve_prompt, format_prompt_template

logger = logging.getLogger(__name__)


class CensorHandler(BaseAgentHandler):
    def __init__(self, state_manager, dispatcher, llm_client: LLMClient):
        super().__init__(state_manager, dispatcher)
        self.llm_client = llm_client

    def _llm_censor_check(self, content: str, workflow_type: Optional[str] = None) -> Dict[str, Any]:
        """从数据库 key=censor 读取提示词模板（YAML: system + user），user 中占位符 {content}。"""
        prompt_raw = resolve_prompt("censor", workflow_type=workflow_type)
        prompt_data = yaml.safe_load(prompt_raw)
        system_prompt = prompt_data.get("system", "")
        user_template = prompt_data.get("user", "")
        user_prompt = format_prompt_template(user_template, content=content[:2000])

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self.llm_client.chat(messages, temperature=0.1, max_tokens=512)
            from src.utils.json_utils import parse_json_from_response
            result = parse_json_from_response(response)
            return result
        except Exception as e:
            logger.warning(f"LLM 审查失败: {e}")
            return {"is_sensitive": False, "reason": "审查失败", "severity": "unknown"}

    def _process(self, workflow_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        state = self.state_manager.get_state(workflow_id)
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        
        content = input_data.get("content") or state.get("draft_content", "")
        
        if not content:
            raise ValueError("必须提供 content")

        llm_check = self._llm_censor_check(content, workflow_type=state.get("workflow_type"))
        return {
            "is_sensitive": llm_check.get("is_sensitive", False),
            "reason": llm_check.get("reason", ""),
            "severity": llm_check.get("severity", "unknown"),
            "checked_by": "llm"
        }

    def _get_source(self) -> EventSource:
        return EventSource.AGENT_CENSOR

    def _get_completion_event_type(self) -> EventType:
        return EventType.CONTENT_CENSORED
