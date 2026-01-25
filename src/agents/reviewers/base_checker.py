from abc import ABC, abstractmethod
from typing import Dict, Any
from src.core.state import AgentState


class BaseChecker(ABC):
    """审稿员基类，定义统一接口"""
    
    @abstractmethod
    def check(self, state: AgentState) -> Dict[str, Any]:
        """
        检查章节质量
        
        Returns:
            {
                "score": int (0-100),
                "issues": [{"scene_id": int, "type": str, "description": str}, ...],
                "suggestions": [str, ...],
                "strengths": [str, ...]
            }
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """返回Checker名称"""
        pass
