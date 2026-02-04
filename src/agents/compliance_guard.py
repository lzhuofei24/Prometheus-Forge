"""
Compliance Guard Agent - Bi-directional Safety Firewall

Implements a two-level (L1 + L2) compliance filtering system:
- L1: Deterministic filtering (regex patterns, blacklists) - millisecond latency
- L2: Semantic filtering (LLM-based) - second latency

This agent can check both input (user queries) and output (AI responses).
"""

import re
import logging
import yaml
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass
from src.agents.base_agent import BaseAgent, AgentConfig, AgentError
from src.core.llm import LLMClient
from src.core.prompt_loader import resolve_prompt, format_prompt_template

logger = logging.getLogger(__name__)


@dataclass
class ComplianceResult:
    """Result of compliance check"""
    blocked: bool
    level: str  # "L1" or "L2"
    reason: str
    severity: str  # "low", "medium", "high", "critical"
    matched_pattern: Optional[str] = None


class L1Filter:
    """
    Level 1: Deterministic filtering using regex and blacklists.

    Fast (millisecond-level) pattern matching for known violations.
    No LLM token cost.
    """

    def __init__(self, patterns: List[str], blacklist: Set[str]):
        """
        Initialize L1 filter.

        Args:
            patterns: List of regex patterns (e.g., r'\\d{17,18}' for ID numbers)
            blacklist: Set of exact-match sensitive words
        """
        self.patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self.blacklist = blacklist

    def check(self, text: str) -> Optional[ComplianceResult]:
        """
        Check text against L1 filters.

        Returns:
            ComplianceResult if violation found, None if clean
        """
        # Exact-match blacklist check
        text_lower = text.lower()
        for word in self.blacklist:
            if word.lower() in text_lower:
                return ComplianceResult(
                    blocked=True,
                    level="L1",
                    reason=f"Blacklisted word detected",
                    severity="high",
                    matched_pattern=word
                )

        # Regex pattern check
        for pattern in self.patterns:
            match = pattern.search(text)
            if match:
                return ComplianceResult(
                    blocked=True,
                    level="L1",
                    reason=f"Pattern violation detected",
                    severity="medium",
                    matched_pattern=pattern.pattern
                )

        return None  # Clean


class L2Filter:
    """
    Level 2: Semantic filtering using LLM.

    Slower but more intelligent - can detect:
    - Contextual violations (e.g., profanity disguised as typos)
    - Prompt injection attempts
    - Scenario-specific policy violations
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize L2 filter.

        Args:
            llm_client: LLM client for semantic checking
        """
        self.llm_client = llm_client

    async def check(
        self,
        text: str,
        safety_policy: str,
        workflow_type: Optional[str] = None
    ) -> ComplianceResult:
        """
        Check text using LLM semantic analysis.

        Args:
            text: Text to check
            safety_policy: Scenario-specific safety policy
            workflow_type: Optional workflow type for prompt selection

        Returns:
            ComplianceResult
        """
        try:
            # Load prompt template from database
            prompt_raw = resolve_prompt("censor", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw)

            # Inject safety policy into system prompt
            system_prompt = prompt_data.get("system", "")
            system_prompt = system_prompt.replace("{safety_policy}", safety_policy)

            # Format user prompt
            user_template = prompt_data.get("user", "")
            user_prompt = format_prompt_template(user_template, text=text[:2000])

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # Call LLM (low temperature for consistency)
            response = self.llm_client.chat(messages, temperature=0.1, max_tokens=512)

            # Parse response
            from src.utils.json_utils import parse_json_from_response
            result = parse_json_from_response(response)

            is_sensitive = result.get("is_sensitive", False)
            reason = result.get("reason", "Unknown violation")
            severity = result.get("severity", "medium")

            return ComplianceResult(
                blocked=is_sensitive,
                level="L2",
                reason=reason,
                severity=severity
            )

        except Exception as e:
            logger.warning(f"L2 filter failed: {e}")
            # Fail-open (allow) on error to avoid blocking legitimate content
            return ComplianceResult(
                blocked=False,
                level="L2",
                reason=f"Check failed: {str(e)}",
                severity="unknown"
            )


class ComplianceGuard(BaseAgent):
    """
    Compliance Guard Agent - Main orchestrator for L1+L2 filtering.

    Usage:
        guard = ComplianceGuard(config, llm_client)
        result = await guard.process({
            "text": "user input or AI output",
            "direction": "input" or "output",
            "workflow_type": "generate_chapter"
        })
    """

    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """
        Initialize ComplianceGuard.

        Args:
            config: Agent configuration with L1/L2 settings
            llm_client: LLM client for L2 checking
        """
        super().__init__(config)
        self.llm_client = llm_client

        # Initialize L1 filter
        l1_config = self.get_config_value("l1_filters", {})
        patterns = l1_config.get("regex_patterns", [])
        blacklist_path = l1_config.get("blacklist_file", None)

        blacklist = set()
        if blacklist_path:
            try:
                with open(blacklist_path, "r", encoding="utf-8") as f:
                    blacklist = {line.strip() for line in f if line.strip()}
            except FileNotFoundError:
                logger.warning(f"Blacklist file not found: {blacklist_path}")

        self.l1_filter = L1Filter(patterns, blacklist)

        # Initialize L2 filter
        self.l2_filter = L2Filter(llm_client)

        # Load safety policy
        self.safety_policy = self.get_config_value("l2_policy", "")

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process compliance check.

        Input:
            {
                "text": str,  # Text to check
                "direction": str,  # "input" or "output"
                "workflow_type": Optional[str]  # For prompt selection
            }

        Output:
            {
                "blocked": bool,
                "level": str,  # "L1" or "L2"
                "reason": str,
                "severity": str
            }
        """
        self.validate_input(input_data, ["text", "direction"])

        text = input_data["text"]
        direction = input_data["direction"]  # "input" or "output"
        workflow_type = input_data.get("workflow_type")

        self.log_info(f"Checking {direction} content (length: {len(text)})")

        # Step 1: L1 Deterministic Filter (fast path)
        l1_result = self.l1_filter.check(text)
        if l1_result:
            self.log_warning(f"L1 blocked: {l1_result.reason}")
            return {
                "blocked": True,
                "level": "L1",
                "reason": l1_result.reason,
                "severity": l1_result.severity,
                "matched_pattern": l1_result.matched_pattern
            }

        # Step 2: L2 Semantic Filter (slow path)
        l2_result = await self.l2_filter.check(text, self.safety_policy, workflow_type)

        if l2_result.blocked:
            self.log_warning(f"L2 blocked: {l2_result.reason}")
        else:
            self.log_info("Content passed all compliance checks")

        return {
            "blocked": l2_result.blocked,
            "level": "L2",
            "reason": l2_result.reason,
            "severity": l2_result.severity
        }

    def get_agent_name(self) -> str:
        return "compliance_guard"


# Backward compatibility with legacy CensorHandler
class CensorHandler:
    """
    Legacy wrapper for ComplianceGuard.

    Maintains compatibility with existing workflow/handlers code.
    """

    def __init__(self, state_manager, dispatcher, llm_client: LLMClient):
        self.state_manager = state_manager
        self.dispatcher = dispatcher
        self.llm_client = llm_client

        # Create ComplianceGuard with minimal config
        config = AgentConfig(
            scenario_name="novel",
            agent_name="compliance_guard",
            config_data={
                "l1_filters": {
                    "regex_patterns": [],
                    "blacklist_file": None
                },
                "l2_policy": "基础合规策略：检查辱骂、色情、暴力内容。"
            }
        )
        self.guard = ComplianceGuard(config, llm_client)

    async def check_content(self, content: str, workflow_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Check content using ComplianceGuard.

        Args:
            content: Content to check
            workflow_type: Optional workflow type

        Returns:
            {
                "is_sensitive": bool,
                "reason": str,
                "severity": str,
                "checked_by": str
            }
        """
        result = await self.guard.process({
            "text": content,
            "direction": "output",
            "workflow_type": workflow_type
        })

        return {
            "is_sensitive": result["blocked"],
            "reason": result["reason"],
            "severity": result["severity"],
            "checked_by": result["level"]
        }
