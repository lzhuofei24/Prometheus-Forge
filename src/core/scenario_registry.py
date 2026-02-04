"""
Scenario Registry - Central registry for scenario management

Provides a singleton registry for registering and retrieving scenarios.
Scenarios are pluggable modules that extend the generic orchestration engine
with domain-specific logic.
"""

import logging
from typing import Dict, Optional, List
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseScenario(ABC):
    """
    Abstract base class for scenarios.

    All scenarios must inherit from this class and implement required methods.
    """

    def __init__(self, config: 'ScenarioConfig'):
        """
        Initialize scenario.

        Args:
            config: Scenario configuration
        """
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.get_name()}")

    @abstractmethod
    def get_name(self) -> str:
        """
        Return scenario name (unique identifier).

        Returns:
            Scenario name (e.g., "novel_generation", "after_sales")
        """
        pass

    @abstractmethod
    def get_version(self) -> str:
        """
        Return scenario version.

        Returns:
            Version string (e.g., "1.0.0")
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """
        Return scenario description.

        Returns:
            Human-readable description
        """
        pass

    def get_routers(self) -> List:
        """
        Return list of FastAPI routers for this scenario.

        Override this to provide scenario-specific API endpoints.

        Returns:
            List of APIRouter instances
        """
        return []

    def get_agents(self) -> Dict[str, any]:
        """
        Return dictionary of scenario-specific agents.

        Override this to provide custom agent configurations.

        Returns:
            Dict mapping agent names to agent instances/configs
        """
        return {}

    def build_context(self, **kwargs) -> Dict:
        """
        Build scenario-specific context.

        Override this to provide domain-specific context building.

        Args:
            **kwargs: Context building parameters

        Returns:
            Context dictionary
        """
        return {}

    def validate(self, data: Dict) -> bool:
        """
        Validate scenario-specific data.

        Override this to provide domain-specific validation.

        Args:
            data: Data to validate

        Returns:
            True if valid, False otherwise
        """
        return True


class ScenarioRegistry:
    """
    Singleton registry for scenarios.

    Usage:
        registry = ScenarioRegistry.get_instance()
        registry.register("novel_generation", novel_scenario)
        scenario = registry.get_scenario("novel_generation")
    """

    _instance: Optional['ScenarioRegistry'] = None
    _scenarios: Dict[str, BaseScenario] = {}

    def __init__(self):
        """Private constructor - use get_instance() instead"""
        if ScenarioRegistry._instance is not None:
            raise RuntimeError("Use ScenarioRegistry.get_instance() instead")

    @classmethod
    def get_instance(cls) -> 'ScenarioRegistry':
        """
        Get singleton instance.

        Returns:
            ScenarioRegistry instance
        """
        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance._scenarios = {}
        return cls._instance

    def register(self, name: str, scenario: BaseScenario) -> None:
        """
        Register a scenario.

        Args:
            name: Scenario name (unique identifier)
            scenario: Scenario instance

        Raises:
            ValueError: If scenario with same name already registered
        """
        if name in self._scenarios:
            logger.warning(f"Scenario '{name}' already registered, overwriting")

        self._scenarios[name] = scenario
        logger.info(f"Registered scenario: {name} (version: {scenario.get_version()})")

    def get_scenario(self, name: str) -> Optional[BaseScenario]:
        """
        Get scenario by name.

        Args:
            name: Scenario name

        Returns:
            Scenario instance or None if not found
        """
        return self._scenarios.get(name)

    def list_scenarios(self) -> List[str]:
        """
        List all registered scenario names.

        Returns:
            List of scenario names
        """
        return list(self._scenarios.keys())

    def get_all_scenarios(self) -> Dict[str, BaseScenario]:
        """
        Get all registered scenarios.

        Returns:
            Dictionary mapping names to scenario instances
        """
        return self._scenarios.copy()

    def unregister(self, name: str) -> bool:
        """
        Unregister a scenario.

        Args:
            name: Scenario name

        Returns:
            True if unregistered, False if not found
        """
        if name in self._scenarios:
            del self._scenarios[name]
            logger.info(f"Unregistered scenario: {name}")
            return True
        return False

    def clear(self) -> None:
        """Clear all registered scenarios (for testing)"""
        self._scenarios.clear()
        logger.info("Cleared all scenarios")


class ScenarioConfig:
    """
    Scenario configuration loader.

    Loads scenario configuration from YAML files.
    """

    def __init__(self, config_data: Dict):
        """
        Initialize configuration.

        Args:
            config_data: Configuration dictionary
        """
        self.config_data = config_data

    @staticmethod
    def from_yaml(yaml_path: str) -> 'ScenarioConfig':
        """
        Load configuration from YAML file.

        Args:
            yaml_path: Path to YAML file

        Returns:
            ScenarioConfig instance

        Raises:
            FileNotFoundError: If file not found
            ValueError: If YAML is invalid
        """
        import yaml
        from pathlib import Path

        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {yaml_path}")

        with open(path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        if not config_data:
            raise ValueError(f"Empty or invalid YAML: {yaml_path}")

        return ScenarioConfig(config_data)

    def get(self, key: str, default=None):
        """
        Get configuration value.

        Args:
            key: Configuration key (supports nested keys with dots, e.g., "agents.planner.temperature")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self.config_data

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    def get_required(self, key: str):
        """
        Get required configuration value.

        Args:
            key: Configuration key

        Returns:
            Configuration value

        Raises:
            ValueError: If key not found
        """
        value = self.get(key)
        if value is None:
            raise ValueError(f"Required configuration key not found: {key}")
        return value

    def get_all(self) -> Dict:
        """
        Get all configuration data.

        Returns:
            Configuration dictionary
        """
        return self.config_data.copy()
