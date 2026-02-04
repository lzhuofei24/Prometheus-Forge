"""
Novel Generation Scenario

Domain-specific implementation for AI-powered novel chapter generation.
This scenario demonstrates the Prometheus Forge architecture with a complete
multi-agent workflow for creative writing assistance.

Components:
- models.py: Domain entities (Novel, Chapter, ChapterDraft, etc.)
- routers/: API endpoints for novel operations
- services/: Business logic layer
- validators/: Domain-specific validation rules
- prompts/: Scenario-specific prompt templates
- novel_scenario.py: Scenario implementation and registration
"""

# Version info
__version__ = "1.0.0"
__scenario_name__ = "novel_generation"

# Auto-register scenario on import
from .novel_scenario import register_scenario
register_scenario()
