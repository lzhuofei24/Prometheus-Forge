"""
Novel Generation Scenario Implementation

Domain-specific scenario for AI-powered novel chapter generation.
Integrates all components: agents, routers, services, validators.
"""

import logging
from typing import Dict, Any, List
from pathlib import Path
from src.core.scenario_registry import BaseScenario, ScenarioConfig

logger = logging.getLogger(__name__)


class NovelScenario(BaseScenario):
    """
    Novel Generation Scenario - Complete implementation.

    This scenario demonstrates the full Prometheus Forge architecture
    with multi-agent workflow, RAG, and domain-specific business logic.
    """

    def __init__(self, config: ScenarioConfig):
        """
        Initialize novel scenario.

        Args:
            config: Scenario configuration
        """
        super().__init__(config)
        self.logger.info("Initializing Novel Generation Scenario")

    def get_name(self) -> str:
        """Return scenario name"""
        return self.config.get("scenario.name", "novel_generation")

    def get_version(self) -> str:
        """Return scenario version"""
        return self.config.get("scenario.version", "1.0.0")

    def get_description(self) -> str:
        """Return scenario description"""
        return self.config.get(
            "scenario.description",
            "AI-powered novel chapter generation"
        )

    def get_routers(self) -> List:
        """
        Return FastAPI routers for novel API endpoints.

        Returns:
            List of APIRouter instances
        """
        try:
            from scenarios.novel.routers.novel_router import router
            return [router]
        except ImportError as e:
            self.logger.warning(f"Failed to import novel routers: {e}")
            return []

    def get_agents(self) -> Dict[str, Any]:
        """
        Return agent configurations for this scenario.

        Returns:
            Dict mapping agent names to configurations
        """
        return {
            "task_planner": self.config.get("agents.task_planner", {}),
            "compliance_guard": self.config.get("agents.compliance_guard", {}),
            "executor": self.config.get("agents.executor", {}),
            "consistency_auditor": self.config.get("agents.consistency_auditor", {}),
            "knowledge_manager": self.config.get("agents.knowledge_manager", {})
        }

    def build_context(self, **kwargs) -> Dict[str, Any]:
        """
        Build novel-specific context for chapter generation.

        Args:
            novel_name: Novel title
            chapter_num: Chapter number
            **kwargs: Additional context parameters

        Returns:
            Context dictionary with reference_context, character_bios, etc.
        """
        novel_name = kwargs.get("novel_name")
        chapter_num = kwargs.get("chapter_num")

        if not novel_name or chapter_num is None:
            raise ValueError("build_context requires novel_name and chapter_num")

        try:
            from scenarios.novel.context_builder import NovelContextBuilder

            # Load context building settings
            context_config = self.config.get("context", {})
            max_tokens = context_config.get("max_tokens", 24000)

            builder = NovelContextBuilder(max_tokens=max_tokens)

            result = builder.build_context(
                novel_name=novel_name,
                chapter_num=chapter_num,
                include_recent_content=context_config.get("include_recent_chapters", True),
                include_outlines=context_config.get("include_outlines", True),
                max_recent_chapters=context_config.get("max_recent_chapters", 3),
                max_outline_chapters=context_config.get("max_outline_chapters", 15)
            )

            return result

        except Exception as e:
            self.logger.error(f"Context building failed: {e}")
            raise

    def validate(self, data: Dict[str, Any]) -> bool:
        """
        Validate novel-specific data.

        Args:
            data: Data to validate (e.g., chapter draft, outline)

        Returns:
            True if valid, False otherwise
        """
        # Basic validation - can be extended
        if "content" in data:
            content = data["content"]
            if not isinstance(content, str):
                return False
            if len(content) == 0:
                return False

        if "outline" in data:
            outline = data["outline"]
            if isinstance(outline, str):
                try:
                    import json
                    outline_dict = json.loads(outline)
                    if "scenes" not in outline_dict:
                        return False
                except:
                    return False

        return True

    def get_workflow_config(self) -> Dict[str, Any]:
        """
        Get workflow configuration for this scenario.

        Returns:
            Workflow configuration dictionary
        """
        return self.config.get("workflow", {})

    def get_validation_rules(self) -> List[Dict[str, Any]]:
        """
        Get validation rules for this scenario.

        Returns:
            List of validation rule configurations
        """
        return self.config.get("domain.validation_rules", [])

    def get_character_schema(self) -> Dict[str, Any]:
        """
        Get character data schema.

        Returns:
            Character schema configuration
        """
        return self.config.get("domain.character_schema", {
            "fields": ["name", "personality", "appearance", "background"]
        })


def register_scenario():
    """
    Register the novel generation scenario.

    Called automatically when this module is imported.
    """
    try:
        # Load configuration
        config_path = Path(__file__).parent / "config.yaml"
        config = ScenarioConfig.from_yaml(str(config_path))

        # Create scenario instance
        scenario = NovelScenario(config)

        # Register with registry
        from src.core.scenario_registry import ScenarioRegistry
        registry = ScenarioRegistry.get_instance()
        registry.register(scenario.get_name(), scenario)

        logger.info(f"Novel scenario registered: {scenario.get_name()} v{scenario.get_version()}")

    except Exception as e:
        logger.error(f"Failed to register novel scenario: {e}")
        raise


# Auto-register on module import
register_scenario()
