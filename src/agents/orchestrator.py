import logging
from typing import Dict, Any
from src.core.state import AgentState
from src.utils.file_manager import ProjectManager

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """总控Agent，负责决策工作流的下一步"""
    
    def __init__(self, file_manager: ProjectManager):
        self.file_manager = file_manager
    
    def decide_next_step(self, state: AgentState) -> str:
        """
        决策下一步执行哪个节点
        
        状态机：INIT → PLAN → WRITE → REVIEW → DECISION → [PUBLISH / WRITE(局部重写)]
        
        Returns:
            节点名称: "world_builder" / "planner" / "writer" / "reviewer" / "publisher"
        """
        current_stage = state.get("current_stage", "init")
        logger.info(f"[OrchestratorAgent] 当前阶段: {current_stage}")
        
        if current_stage == "init":
            state["current_stage"] = "plan"
            return "world_builder"
        
        elif current_stage == "plan":
            state["current_stage"] = "write"
            return "planner"
        
        elif current_stage == "write":
            state["current_stage"] = "review"
            return "writer"
        
        elif current_stage == "review":
            state["current_stage"] = "decision"
            return "reviewer"
        
        elif current_stage == "decision":
            return self._make_decision(state)
        
        else:
            logger.warning(f"[OrchestratorAgent] 未知阶段: {current_stage}，默认发布")
            return "publisher"
    
    def _make_decision(self, state: AgentState) -> str:
        """
        决策节点：判断是通过发布、全文重写还是局部重写
        
        Returns:
            "publisher" / "writer" / "planner"
        """
        critique_score = state.get("critique_score", 0)
        attempt_count = state.get("attempt_count", 0)
        target_scenes = state.get("target_scenes", [])
        
        from pathlib import Path
        import yaml
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config" / "settings.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        
        reviewer_config = config_data.get("reviewers", {})
        overall_threshold = reviewer_config.get("overall_pass_threshold", 70)
        max_attempts = reviewer_config.get("max_attempts", 3)
        
        logger.info(f"[OrchestratorAgent] 评分: {critique_score}, 尝试次数: {attempt_count}, 低分场景: {target_scenes}")
        
        if critique_score >= overall_threshold or attempt_count >= max_attempts:
            logger.info(f"[OrchestratorAgent] 决策: 通过发布 (评分达标或达到最大尝试次数)")
            state["rewrite_type"] = "none"
            state["current_stage"] = "publish"
            return "publisher"
        
        if target_scenes and len(target_scenes) <= 2:
            logger.info(f"[OrchestratorAgent] 决策: 局部重写场景 {target_scenes}")
            state["rewrite_type"] = "partial"
            state["attempt_count"] = attempt_count + 1
            state["current_stage"] = "write"
            return "writer"
        
        logger.info(f"[OrchestratorAgent] 决策: 全文重写")
        state["rewrite_type"] = "full"
        state["attempt_count"] = attempt_count + 1
        state["current_stage"] = "plan"
        return "planner"
    
    def init_state(self, state: AgentState) -> AgentState:
        """初始化状态字段"""
        if "current_stage" not in state:
            state["current_stage"] = "init"
        if "attempt_count" not in state:
            state["attempt_count"] = 0
        if "rewrite_type" not in state:
            state["rewrite_type"] = "none"
        if "target_scenes" not in state:
            state["target_scenes"] = []
        if "scene_feedback" not in state:
            state["scene_feedback"] = {}
        if "review_results" not in state:
            state["review_results"] = {}
        
        return state
