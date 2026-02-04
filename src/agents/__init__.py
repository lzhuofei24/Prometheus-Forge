"""
Prometheus Forge - Generic Agent Layer

This module contains scenario-agnostic agents that form the core
orchestration engine. These agents are designed to be reusable across
different scenarios through configuration injection.

Agents:
- BaseAgent: Abstract foundation class
- ComplianceGuard: Bi-directional safety firewall (L1 + L2)
- TaskPlanner: Intent classification and DAG compilation (TODO)
- Executor: RAG-powered generation engine (TODO)
- ConsistencyAuditor: Logic validation and fact-checking (TODO)
- KnowledgeManager: Memory consolidation and graph updates (TODO)
"""

from .base_agent import BaseAgent, AgentConfig, AgentError
from .compliance_guard import ComplianceGuard, CensorHandler
from .task_planner import TaskPlanner, ArchitectHandler
from .consistency_auditor import ConsistencyAuditor, CriticHandler
from .executor import Executor, WriterHandler
from .knowledge_manager import KnowledgeManager, KnowledgeHandler

__all__ = [
    "BaseAgent",
    "AgentConfig",
    "AgentError",
    "ComplianceGuard",
    "CensorHandler",
    "TaskPlanner",
    "ArchitectHandler",
    "ConsistencyAuditor",
    "CriticHandler",
    "Executor",
    "WriterHandler",
    "KnowledgeManager",
    "KnowledgeHandler",
]
