"""
Task Planner Agent - Intent Classification and DAG Compilation

Responsibilities:
1. Classify user intent from natural language input
2. Generate execution plan (DAG) based on intent and scenario rules
3. Route to appropriate tools/agents

This agent is the "brain" of the workflow - it decides what needs to be done.
"""

import json
import logging
import yaml
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from src.agents.base_agent import BaseAgent, AgentConfig, AgentError
from src.core.llm import LLMClient
from src.core.prompt_loader import resolve_prompt, format_prompt_template

logger = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """Single step in execution plan"""
    id: str
    tool: str  # Tool/agent to invoke
    args: Dict[str, Any]
    dependency: Optional[str] = None  # ID of step this depends on


@dataclass
class Plan:
    """Execution plan (DAG)"""
    intent: str  # Classified intent
    steps: List[PlanStep]
    metadata: Dict[str, Any]


class TaskPlanner(BaseAgent):
    """
    Task Planner Agent - Orchestrates workflow by planning execution steps.

    Usage:
        planner = TaskPlanner(config, llm_client)
        result = await planner.process({
            "user_query": "Generate chapter 1",
            "context": {...},
            "workflow_type": "generate_chapter"
        })

    Output:
        {
            "intent": "GENERATE_CHAPTER",
            "plan": {
                "steps": [
                    {"id": "s1", "tool": "build_context", "args": {...}},
                    {"id": "s2", "tool": "generate_outline", "args": {...}, "dependency": "s1"},
                    ...
                ]
            }
        }
    """

    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """
        Initialize TaskPlanner.

        Args:
            config: Agent configuration with intent/DAG templates
            llm_client: LLM client for intent classification and planning
        """
        super().__init__(config)
        self.llm_client = llm_client

    async def classify_intent(
        self,
        user_query: str,
        context: Dict[str, Any],
        workflow_type: Optional[str] = None
    ) -> str:
        """
        Classify user intent using LLM.

        Args:
            user_query: Natural language query
            context: Context data (e.g., user level, current state)
            workflow_type: Optional workflow type for prompt selection

        Returns:
            Intent string (e.g., "GENERATE_CHAPTER", "REVISE_CHAPTER")
        """
        try:
            # Load intent classification prompt
            prompt_raw = resolve_prompt("intent_classifier", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw)

            system_prompt = prompt_data.get("system", "")
            user_template = prompt_data.get("user", "")

            # Format prompt with context
            user_prompt = format_prompt_template(
                user_template,
                user_query=user_query,
                **context
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # Call LLM for classification
            response = self.llm_client.chat(messages, temperature=0.1, max_tokens=512)

            # Parse intent from response
            # Expected format: "INTENT_NAME" or JSON {"intent": "INTENT_NAME"}
            from src.utils.json_utils import parse_json_from_response
            try:
                result = parse_json_from_response(response)
                intent = result.get("intent", response.strip())
            except:
                intent = response.strip()

            self.log_info(f"Classified intent: {intent}")
            return intent

        except Exception as e:
            self.log_error(f"Intent classification failed: {e}")
            # Default to workflow_type if available
            return workflow_type or "UNKNOWN"

    async def compile_dag(
        self,
        intent: str,
        context: Dict[str, Any],
        workflow_type: Optional[str] = None
    ) -> Plan:
        """
        Compile execution plan (DAG) based on intent.

        Args:
            intent: Classified intent
            context: Context data
            workflow_type: Optional workflow type

        Returns:
            Plan object with steps
        """
        try:
            # Load DAG compilation prompt
            prompt_raw = resolve_prompt("dag_compiler", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw)

            system_prompt = prompt_data.get("system", "")
            user_template = prompt_data.get("user", "")

            # Format prompt
            user_prompt = format_prompt_template(
                user_template,
                intent=intent,
                **context
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            # Call LLM for DAG generation
            response = self.llm_client.chat(messages, temperature=0.3, max_tokens=2048)

            # Parse DAG from response
            from src.utils.json_utils import parse_json_from_response
            dag_data = parse_json_from_response(response)

            if not dag_data or "steps" not in dag_data:
                raise ValueError("Invalid DAG format: missing 'steps'")

            # Convert to Plan object
            steps = [
                PlanStep(
                    id=step["id"],
                    tool=step["tool"],
                    args=step.get("args", {}),
                    dependency=step.get("dependency")
                )
                for step in dag_data["steps"]
            ]

            plan = Plan(
                intent=intent,
                steps=steps,
                metadata=dag_data.get("metadata", {})
            )

            self.log_info(f"Compiled plan with {len(steps)} steps")
            return plan

        except Exception as e:
            self.log_error(f"DAG compilation failed: {e}")
            raise AgentError(
                self.get_agent_name(),
                f"Failed to compile execution plan: {str(e)}"
            )

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process planning request.

        Input:
            {
                "user_query": str,  # Natural language input
                "context": Dict,  # Context data
                "workflow_type": Optional[str],
                "skip_intent_classification": bool  # If true, use workflow_type as intent
            }

        Output:
            {
                "intent": str,
                "plan": {
                    "steps": List[Dict],
                    "metadata": Dict
                }
            }
        """
        self.validate_input(input_data, ["user_query", "context"])

        user_query = input_data["user_query"]
        context = input_data["context"]
        workflow_type = input_data.get("workflow_type")
        skip_intent = input_data.get("skip_intent_classification", False)

        # Step 1: Intent Classification
        if skip_intent and workflow_type:
            intent = workflow_type
            self.log_info(f"Skipping intent classification, using: {intent}")
        else:
            intent = await self.classify_intent(user_query, context, workflow_type)

        # Step 2: DAG Compilation
        plan = await self.compile_dag(intent, context, workflow_type)

        return {
            "intent": intent,
            "plan": {
                "steps": [asdict(step) for step in plan.steps],
                "metadata": plan.metadata
            }
        }

    def get_agent_name(self) -> str:
        return "task_planner"


# Backward compatibility with legacy ArchitectHandler
class ArchitectHandler:
    """
    Legacy wrapper for TaskPlanner.

    Maintains compatibility with existing workflow code.
    Maps old architect behavior to new TaskPlanner.
    """

    def __init__(self, state_manager, dispatcher, llm_client: LLMClient, file_manager=None):
        self.state_manager = state_manager
        self.dispatcher = dispatcher
        self.llm_client = llm_client
        self.file_manager = file_manager

        # Create TaskPlanner with minimal config
        config = AgentConfig(
            scenario_name="novel",
            agent_name="task_planner",
            config_data={}
        )
        self.planner = TaskPlanner(config, llm_client)

    async def generate_outline(
        self,
        novel_name: str,
        chapter_num: int,
        reference_context: str,
        workflow_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate chapter outline using TaskPlanner.

        This is a simplified version that just does outline generation
        without full intent classification and DAG compilation.

        Args:
            novel_name: Novel title
            chapter_num: Chapter number
            reference_context: Context string (characters, world, previous chapters)
            workflow_type: Optional workflow type

        Returns:
            {"outline": str}  # JSON string of scenes
        """
        try:
            # Load outline generation prompt (architect prompt)
            from src.core.prompt_loader import get_fiction_system_prompt
            prompt_raw = resolve_prompt("architect", workflow_type=workflow_type)
            prompt_data = yaml.safe_load(prompt_raw)

            system_prompt = prompt_data.get("system", "")
            user_template = prompt_data.get("user", "")

            user_prompt = format_prompt_template(
                user_template,
                reference_context=reference_context,
                chapter_num=chapter_num,
                feedback_section="",
            )

            messages = [
                {"role": "system", "content": get_fiction_system_prompt() + "\n\n" + system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = self.llm_client.chat(messages, temperature=0.7, max_tokens=4096)

            # Parse outline JSON
            from src.utils.json_utils import parse_json_from_response
            outline_json = parse_json_from_response(response)

            if not outline_json or "scenes" not in outline_json:
                raise ValueError("Outline generation failed: no valid scenes returned")

            outline = json.dumps(outline_json, ensure_ascii=False)
            return {"outline": outline}

        except Exception as e:
            logger.error(f"Outline generation failed: {e}")
            raise ValueError(f"Failed to generate outline: {str(e)}")
