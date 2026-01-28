"""
LangGraph 工作流图构建

基于 LangGraph 的状态机编排，替代旧的 Controller 循环。
使用 WorkflowState 和 nodes.py 中定义的异步节点函数。
"""
import logging
from typing import Literal
from langgraph.graph import StateGraph, END

from src.workflow.state import WorkflowState
from src.workflow.nodes import (
    architect_node,
    writer_node,
    censor_node,
    critic_node,
    media_node,
)

logger = logging.getLogger(__name__)


def route_after_censor(state: WorkflowState) -> Literal["critic", "__end__"]:
    """
    路由逻辑：Censor 之后
    
    如果内容敏感，终止工作流；否则继续到 Critic。
    """
    is_sensitive = state.get("is_sensitive", False)
    
    if is_sensitive:
        logger.warning(
            f"工作流 {state.get('workflow_id')} 因敏感内容终止: {state.get('censor_reason', '')}"
        )
        state["status"] = "blocked"
        return "__end__"
    else:
        return "critic"


def route_after_critic(state: WorkflowState) -> Literal["writer", "media", "__end__"]:
    """
    路由逻辑：Critic 之后
    
    根据评分决定下一步：
    - score >= 75: 通过，生成媒体
    - score < 75 且 revision_count < 3: 打回重写（增加 revision_count）
    - 否则: 强制结束（多次修改仍不合格）
    """
    score = state.get("critique_score", 0)
    revision_count = state.get("revision_count", 0)
    workflow_id = state.get("workflow_id", "")
    
    if score >= 75:
        logger.info(f"✅ 工作流 {workflow_id} 审稿通过 (score={score})，继续生成媒体")
        return "media"
    elif revision_count < 3:
        # 打回重写，增加修订次数
        new_revision_count = revision_count + 1
        state["revision_count"] = new_revision_count
        state["feedback"] = state.get("critique_comments") or state.get("advice", "")
        logger.info(
            f"⚠️ 工作流 {workflow_id} 需要修订 (score={score}, revision={new_revision_count}/3)，打回 Writer"
        )
        return "writer"
    else:
        # 达到最大修订次数，强制结束
        logger.warning(
            f"❌ 工作流 {workflow_id} 达到最大修订次数 (revision={revision_count})，强制结束"
        )
        state["status"] = "failed"
        state["error"] = f"审稿评分 {score} 分，已修订 {revision_count} 次仍不合格"
        return "__end__"


def create_workflow_graph(workflow_type: str = "generate_chapter") -> StateGraph:
    """
    创建 LangGraph 工作流图
    
    Args:
        workflow_type: 工作流类型（目前仅支持 "generate_chapter"）
    
    Returns:
        编译后的 LangGraph 图
    
    工作流拓扑：
    architect -> writer -> censor -> [critic | END] -> [writer | media | END] -> END
    
    详细流程：
    1. architect: 生成大纲
    2. writer: 生成正文
    3. censor: 敏感内容审查
    4. critic: 内容质量审稿
       - 如果敏感 -> END (blocked)
       - 如果通过 (score >= 75) -> media
       - 如果需要修订 (score < 75 且 revision_count < 3) -> writer (循环)
       - 如果达到最大修订次数 -> END (failed)
    5. media: 生成配图 -> END
    """
    workflow = StateGraph(WorkflowState)
    
    # 添加所有节点
    workflow.add_node("architect", architect_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("censor", censor_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("media", media_node)
    
    # 设置入口点
    workflow.set_entry_point("architect")
    
    # 添加普通边（顺序执行）
    workflow.add_edge("architect", "writer")
    workflow.add_edge("writer", "censor")
    
    # 添加条件边：censor -> critic 或 END
    workflow.add_conditional_edges(
        "censor",
        route_after_censor,
        {
            "critic": "critic",
            "__end__": END,
        },
    )
    
    # 添加条件边：critic -> writer (修订) | media (通过) | END (失败)
    workflow.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "writer": "writer",  # 修订：回到 writer
            "media": "media",     # 通过：生成媒体
            "__end__": END,       # 失败：结束
        },
    )
    
    # media 完成后结束
    workflow.add_edge("media", END)
    
    # 编译图
    compiled_graph = workflow.compile()
    
    logger.info(f"✅ LangGraph 工作流图已创建 (workflow_type={workflow_type})")
    return compiled_graph


# 为了兼容性，提供一个默认的图实例
_default_graph = None


def get_default_graph() -> StateGraph:
    """获取默认的工作流图（单例模式）"""
    global _default_graph
    if _default_graph is None:
        _default_graph = create_workflow_graph()
    return _default_graph
