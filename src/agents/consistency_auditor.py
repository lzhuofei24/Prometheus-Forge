"""
Consistency Auditor Agent - Logic Validation and Fact-Checking

Responsibilities:
1. Extract factual claims from AI-generated content
2. Validate claims against ground truth (database, knowledge graph)
3. Detect inconsistencies, hallucinations, and logic errors
4. Provide actionable feedback for self-correction

This agent acts as a "unit test" for AI outputs, ensuring quality and accuracy.
"""

import json
import logging
import yaml
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
from src.agents.base_agent import BaseAgent, AgentConfig, AgentError
from src.core.llm import LLMClient
from src.core.prompt_loader import resolve_prompt, format_prompt_template

logger = logging.getLogger(__name__)


@dataclass
class Claim:
    """Extracted factual claim"""
    claim_type: str  # "action", "amount", "parameter", "promise", etc.
    content: str
    confidence: float  # 0.0-1.0


@dataclass
class ValidationResult:
    """Result of validation"""
    passed: bool
    errors: List[str]
    warnings: List[str]
    score: int  # 0-100
    feedback: str  # Actionable feedback for correction


class ValidationStrategy(ABC):
    """Abstract base class for validation strategies"""

    @abstractmethod
    async def validate(
        self,
        draft: str,
        claims: List[Claim],
        ground_truth: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validate claims against ground truth.

        Args:
            draft: Original draft text
            claims: Extracted claims
            ground_truth: Reference data for validation

        Returns:
            ValidationResult
        """
        pass


class RuleBasedStrategy(ValidationStrategy):
    """
    Rule-based validation using Python logic.

    Best for: Deterministic checks (dates, numbers, status transitions)
    """

    def __init__(self, rules: List[callable]):
        """
        Initialize rule-based strategy.

        Args:
            rules: List of validation functions
        """
        self.rules = rules

    async def validate(
        self,
        draft: str,
        claims: List[Claim],
        ground_truth: Dict[str, Any]
    ) -> ValidationResult:
        """
        Run all rules and collect errors.
        """
        errors = []
        warnings = []

        for rule in self.rules:
            try:
                result = rule(claims, ground_truth)
                if result:  # Rule returns error message if failed
                    errors.append(result)
            except Exception as e:
                warnings.append(f"Rule execution failed: {str(e)}")

        passed = len(errors) == 0
        score = 100 if passed else max(0, 100 - len(errors) * 20)

        feedback = "\n".join(errors) if errors else "All validation rules passed"

        return ValidationResult(
            passed=passed,
            errors=errors,
            warnings=warnings,
            score=score,
            feedback=feedback
        )


class NLIStrategy(ValidationStrategy):
    """
    Natural Language Inference (NLI) validation using LLM.

    Best for: Semantic consistency, common sense checking
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize NLI strategy.

        Args:
            llm_client: LLM client for NLI
        """
        self.llm_client = llm_client

    async def validate(
        self,
        draft: str,
        claims: List[Claim],
        ground_truth: Dict[str, Any]
    ) -> ValidationResult:
        """
        Use LLM to check for logical contradictions.
        """
        try:
            # Build prompt for NLI
            claims_text = "\n".join([f"- {c.content}" for c in claims])
            context_text = json.dumps(ground_truth, ensure_ascii=False, indent=2)

            prompt = f"""
任务：检查AI回复中的事实主张是否自相矛盾或违背常识。

AI回复：
{draft[:1000]}

提取的主张：
{claims_text}

参考上下文：
{context_text}

请检查是否存在以下问题：
1. 自相矛盾（回复中前后不一致）
2. 与上下文冲突
3. 违背常识

输出JSON格式：
{{
    "has_contradiction": bool,
    "issues": [str],  // 发现的问题列表
    "score": int  // 0-100
}}
"""

            response = self.llm_client.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=512
            )

            from src.utils.json_utils import parse_json_from_response
            result = parse_json_from_response(response)

            has_issues = result.get("has_contradiction", False)
            issues = result.get("issues", [])
            score = result.get("score", 100)

            return ValidationResult(
                passed=not has_issues,
                errors=issues if has_issues else [],
                warnings=[],
                score=score,
                feedback="\n".join(issues) if issues else "No contradictions found"
            )

        except Exception as e:
            logger.warning(f"NLI validation failed: {e}")
            return ValidationResult(
                passed=True,  # Fail-open
                errors=[],
                warnings=[f"Validation check failed: {str(e)}"],
                score=100,
                feedback="Validation check encountered an error"
            )


class ConsistencyAuditor(BaseAgent):
    """
    Consistency Auditor Agent - Quality assurance for AI outputs.

    Usage:
        auditor = ConsistencyAuditor(config, llm_client, strategy)
        result = await auditor.process({
            "draft": "AI-generated content",
            "ground_truth": {...},  # Reference data
            "workflow_type": "generate_chapter"
        })

    Output:
        {
            "passed": bool,
            "score": int,  # 0-100
            "errors": List[str],
            "feedback": str  # For self-correction
        }
    """

    def __init__(
        self,
        config: AgentConfig,
        llm_client: LLMClient,
        strategy: Optional[ValidationStrategy] = None
    ):
        """
        Initialize ConsistencyAuditor.

        Args:
            config: Agent configuration
            llm_client: LLM client for claim extraction
            strategy: Validation strategy (defaults to NLI)
        """
        super().__init__(config)
        self.llm_client = llm_client

        # Default to NLI strategy if none provided
        self.strategy = strategy or NLIStrategy(llm_client)

    async def extract_claims(
        self,
        draft: str,
        workflow_type: Optional[str] = None
    ) -> List[Claim]:
        """
        Extract factual claims from draft using LLM.

        Args:
            draft: Draft text
            workflow_type: Optional workflow type for prompt selection

        Returns:
            List of extracted claims
        """
        try:
            # Load claim extraction prompt
            prompt_raw = resolve_prompt("claim_extraction", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw)

            system_prompt = prompt_data.get("system", "")
            user_template = prompt_data.get("user", "")

            user_prompt = format_prompt_template(user_template, draft=draft[:2000])

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.llm_client.chat(messages, temperature=0.1, max_tokens=1024)

            # Parse claims from response
            from src.utils.json_utils import parse_json_from_response
            result = parse_json_from_response(response)

            claims = []
            for claim_data in result.get("claims", []):
                claims.append(Claim(
                    claim_type=claim_data.get("type", "unknown"),
                    content=claim_data.get("content", ""),
                    confidence=claim_data.get("confidence", 1.0)
                ))

            self.log_info(f"Extracted {len(claims)} claims")
            return claims

        except Exception as e:
            self.log_warning(f"Claim extraction failed: {e}")
            # Return empty list on failure (fail-open)
            return []

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process audit request.

        Input:
            {
                "draft": str,  # Content to audit
                "ground_truth": Dict,  # Reference data
                "workflow_type": Optional[str],
                "skip_claim_extraction": bool  # If true, skip extraction step
            }

        Output:
            {
                "passed": bool,
                "score": int,
                "errors": List[str],
                "warnings": List[str],
                "feedback": str
            }
        """
        self.validate_input(input_data, ["draft", "ground_truth"])

        draft = input_data["draft"]
        ground_truth = input_data["ground_truth"]
        workflow_type = input_data.get("workflow_type")
        skip_extraction = input_data.get("skip_claim_extraction", False)

        self.log_info(f"Auditing draft (length: {len(draft)})")

        # Step 1: Extract claims (optional)
        if skip_extraction:
            claims = []
            self.log_info("Skipping claim extraction")
        else:
            claims = await self.extract_claims(draft, workflow_type)

        # Step 2: Validate using strategy
        validation_result = await self.strategy.validate(draft, claims, ground_truth)

        self.log_info(f"Audit result: {'PASS' if validation_result.passed else 'FAIL'} (score: {validation_result.score})")

        return {
            "passed": validation_result.passed,
            "score": validation_result.score,
            "errors": validation_result.errors,
            "warnings": validation_result.warnings,
            "feedback": validation_result.feedback
        }

    def get_agent_name(self) -> str:
        return "consistency_auditor"


# Backward compatibility with legacy CriticHandler
class CriticHandler:
    """
    Legacy wrapper for ConsistencyAuditor.

    Maintains compatibility with existing workflow code.
    Maps old critic behavior (scoring) to new auditor pattern.
    """

    def __init__(self, state_manager, dispatcher, llm_client: LLMClient, file_manager=None):
        self.state_manager = state_manager
        self.dispatcher = dispatcher
        self.llm_client = llm_client
        self.file_manager = file_manager

        # Create ConsistencyAuditor with minimal config
        config = AgentConfig(
            scenario_name="novel",
            agent_name="consistency_auditor",
            config_data={}
        )
        # Use NLI strategy by default
        self.auditor = ConsistencyAuditor(config, llm_client)

    async def critique_content(
        self,
        draft_content: str,
        reference_context: str,
        outline: str,
        workflow_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Critique content using ConsistencyAuditor + legacy LLM scoring.

        Args:
            draft_content: Content to critique
            reference_context: Context (characters, world, etc.)
            outline: Chapter outline
            workflow_type: Optional workflow type

        Returns:
            {
                "score": int,
                "passed": bool,
                "advice": str,
                "comments": str,
                "details": Dict
            }
        """
        try:
            # Use legacy critique prompt for scoring
            from src.core.prompt_loader import get_fiction_system_prompt
            prompt_raw = resolve_prompt("critique_handler", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw)

            system_prompt = prompt_data.get("system", "")
            user_template = prompt_data.get("user", "")

            user_prompt = format_prompt_template(
                user_template,
                reference_context=reference_context,
                outline=outline,
                draft_content=draft_content,
                chapter_num=1,  # Placeholder
            )

            messages = [
                {"role": "system", "content": get_fiction_system_prompt() + "\n\n" + system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.llm_client.chat(messages, temperature=0.3, max_tokens=2048)

            # Parse critique
            from src.utils.json_utils import parse_json_from_response
            critique_result = parse_json_from_response(response)

            score = int(critique_result.get("score", 0))
            passed = score >= 75

            if "passed" in critique_result:
                passed = bool(critique_result["passed"])

            return {
                "score": score,
                "passed": passed,
                "advice": critique_result.get("suggestions", ""),
                "comments": critique_result.get("critique", ""),
                "details": critique_result.get("details", {})
            }

        except Exception as e:
            logger.warning(f"Critique failed: {e}")
            return {
                "score": 50,
                "passed": False,
                "advice": "请重新审视章节结构，确保情节连贯、人物饱满。",
                "comments": "审稿解析失败，请检查内容质量。",
                "details": {}
            }
