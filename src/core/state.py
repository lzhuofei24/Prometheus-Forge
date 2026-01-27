"""
全局工作流状态：Agent 间通信协议。

- AgentState: 现有 workflow/graph、import_graph、agents 等使用的状态（保持兼容）。
- NovelState: 新 LangGraph 编排层用的结构化状态，支持可回溯、可人工介入。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


# 现有流程使用的状态类型（workflow/graph.py、import_graph、agents 等）
AgentState = Dict[str, Any]


class NovelState(TypedDict, total=False):
    """
    图谱内全局状态，所有节点读写此结构。
    图中对 critique_comments 使用 reducer（如 operator.add）做追加，在此仅做类型声明。
    """

    # 标识与定位
    novel_id: str
    chapter_index: int
    workflow_id: str
    novel_name: str
    chapter_num: int
    workflow_type: str

    # 核心内容
    outline: Optional[str]
    content: Optional[str]
    draft_content: Optional[str]

    # 审核与评价
    critique_score: Optional[int]
    critique_comments: List[str]  # 累计历史；图中用 Annotated[List, operator.add] 追加
    revision_count: int
    is_sensitive: bool
    censor_reason: Optional[str]

    # 记忆与图谱
    context_summary: str
    entities: List[str]
    reference_context: Optional[str]

    # 控制流
    next_step: str
    user_feedback: Optional[str]
    status: str

    # 兼容现有字段（writer/critic 等写入）
    score: Optional[int]
    advice: Optional[str]
    comments: Optional[str]
    passed: Optional[bool]
    details: Optional[dict]
    rolling_summary: Optional[str]
    entities_extracted: Optional[int]
    chapter_indexed: Optional[int]
