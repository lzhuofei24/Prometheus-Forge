"""
Base Agent - Generic Agent Foundation

Abstract base class for all Prometheus Forge agents.
Provides common interface and lifecycle management.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Base configuration for agents"""
    scenario_name: str
    agent_name: str
    config_data: Dict[str, Any]


class BaseAgent(ABC):
    """
    Abstract base class for all agents in Prometheus Forge.

    All agents should inherit from this class and implement:
    - process(): Main agent logic
    - get_agent_name(): Agent identifier

    Agents are stateless - they receive input and produce output
    without maintaining internal state between invocations.
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        """
        Initialize the agent.

        Args:
            config: Agent configuration from scenario
        """
        self.config = config or AgentConfig(
            scenario_name="unknown",
            agent_name=self.__class__.__name__,
            config_data={}
        )
        self.logger = logging.getLogger(f"{__name__}.{self.get_agent_name()}")

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process input and return output.

        This is the main entry point for agent logic.
        Agents should be idempotent when possible.

        Args:
            input_data: Input data dictionary

        Returns:
            Output data dictionary

        Raises:
            AgentError: If processing fails
        """
        pass

    @abstractmethod
    def get_agent_name(self) -> str:
        """
        Return the agent's identifier.

        Returns:
            Agent name (e.g., "compliance_guard", "task_planner")
        """
        pass

    def validate_input(self, input_data: Dict[str, Any], required_keys: list) -> None:
        """
        Validate that required keys are present in input.

        Args:
            input_data: Input data dictionary
            required_keys: List of required key names

        Raises:
            ValueError: If required keys are missing
        """
        missing = [key for key in required_keys if key not in input_data]
        if missing:
            raise ValueError(f"{self.get_agent_name()}: Missing required keys: {missing}")

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with default fallback.

        Args:
            key: Configuration key
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self.config.config_data.get(key, default)

    def log_info(self, message: str, **kwargs):
        """Log info message with agent context"""
        self.logger.info(f"[{self.get_agent_name()}] {message}", extra=kwargs)

    def log_warning(self, message: str, **kwargs):
        """Log warning message with agent context"""
        self.logger.warning(f"[{self.get_agent_name()}] {message}", extra=kwargs)

    def log_error(self, message: str, **kwargs):
        """Log error message with agent context"""
        self.logger.error(f"[{self.get_agent_name()}] {message}", extra=kwargs)


class AgentError(Exception):
    """Base exception for agent errors"""
    def __init__(self, agent_name: str, message: str, details: Optional[Dict] = None):
        self.agent_name = agent_name
        self.message = message
        self.details = details or {}
        super().__init__(f"[{agent_name}] {message}")
