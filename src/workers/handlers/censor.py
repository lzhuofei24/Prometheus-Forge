import logging
from typing import Dict, Any, List
from pathlib import Path
from src.workers.base import BaseAgentHandler
from src.core.events import EventType, EventSource
from src.core.llm import LLMClient
from src.core.db_service import DatabaseService

logger = logging.getLogger(__name__)


class CensorHandler(BaseAgentHandler):
    def __init__(self, state_manager, dispatcher, llm_client: LLMClient, sensitive_words: List[str] = None):
        super().__init__(state_manager, dispatcher)
        self.llm_client = llm_client
        self.sensitive_words = sensitive_words or self._load_sensitive_words()

    def _load_sensitive_words(self) -> List[str]:
        project_root = Path(__file__).parent.parent.parent.parent
        words_file = project_root / "config" / "sensitive_words.txt"
        
        if words_file.exists():
            with open(words_file, "r", encoding="utf-8") as f:
                words = [line.strip() for line in f if line.strip()]
                logger.info(f"加载了 {len(words)} 个敏感词")
                return words
        return []

    def _check_sensitive_words(self, content: str) -> Dict[str, Any]:
        found_words = []
        for word in self.sensitive_words:
            if word in content:
                found_words.append(word)
        
        if found_words:
            return {
                "is_sensitive": True,
                "found_words": found_words,
                "reason": "包含敏感词列表中的词汇"
            }
        return {"is_sensitive": False, "found_words": []}

    def _llm_censor_check(self, content: str) -> Dict[str, Any]:
        prompt = f"""
请审查以下文本内容，判断是否包含敏感、不当或违规内容。

**待审查文本**：
{content[:2000]}

**审查要求**：
1. 检查是否包含色情、暴力、政治敏感等不当内容
2. 检查是否包含违法违规内容
3. 检查是否包含可能引起不适的内容

**输出格式**（严格 JSON）：
{{
  "is_sensitive": true/false,
  "reason": "判断理由（如果敏感）",
  "severity": "low/medium/high"
}}

如果不敏感，is_sensitive 为 false，reason 可以为空。
"""

        messages = [
            {"role": "system", "content": "你是一位专业的内容审查员，负责识别文本中的敏感内容。必须返回严格的 JSON 格式。"},
            {"role": "user", "content": prompt}
        ]

        try:
            response = self.llm_client.chat(messages, temperature=0.1, max_tokens=512)
            import json
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
        
        word_check = self._check_sensitive_words(content)
        
        if word_check["is_sensitive"]:
            return {
                "is_sensitive": True,
                "found_words": word_check["found_words"],
                "reason": word_check["reason"],
                "checked_by": "word_list"
            }
        
        llm_check = self._llm_censor_check(content)
        
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
