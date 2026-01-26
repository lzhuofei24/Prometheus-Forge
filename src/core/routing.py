"""
路由规则：Controller 与 workflows 共用，独立成模块以避免 workflows ↔ controller 循环导入。
"""
from typing import Dict, Any, List, Optional, Callable


class RoutingRule:
    """单步路由规则：由 source_agent 完成后的结果 data 决定下一批 next_agents 或 else_agents。"""

    def __init__(
        self,
        source_agent: str,
        next_agents: List[str],
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None,
        else_agents: Optional[List[str]] = None,
    ):
        self.source_agent = source_agent
        self.next_agents = next_agents
        self.condition = condition
        self.else_agents = else_agents or []

    def decide(self, data: Dict[str, Any]) -> List[str]:
        if self.condition and not self.condition(data):
            return self.else_agents
        return self.next_agents
