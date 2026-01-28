"""
LangGraph 工作流状态定义

定义 WorkflowState (TypedDict)，用于 LangGraph 状态机编排。
状态字段需涵盖小说生成全流程所需的数据，并能无缝映射到 StateManager 的 Redis 状态。
"""
from typing import TypedDict, Optional, Dict, Any, List


class WorkflowState(TypedDict, total=False):
    """
    LangGraph 工作流状态
    
    所有字段都是可选的（total=False），因为状态是逐步构建的。
    字段设计参考了 StateManager 中的数据结构，确保能无缝映射。
    """
    
    # ========== 基础标识信息 ==========
    workflow_id: str  # 工作流唯一标识
    novel_name: str  # 小说名称
    chapter_num: int  # 章节编号
    workflow_type: str  # 工作流类型：generate_chapter, outline_only, content_only, etc.
    
    # ========== 核心内容数据 ==========
    outline: Optional[str]  # 章节大纲（JSON 字符串格式）
    draft_content: Optional[str]  # 草稿正文
    reference_context: Optional[str]  # 参考上下文（人物设定、世界观、前文等）
    
    # ========== Critic 审稿结果 ==========
    critique_score: Optional[int]  # 审稿评分（0-100）
    critique_comments: Optional[str]  # 审稿意见
    revision_count: int  # 修订次数（用于控制最大修订次数）
    advice: Optional[str]  # 改进建议（兼容字段）
    
    # ========== Censor 审查结果 ==========
    is_sensitive: Optional[bool]  # 是否敏感
    censor_result: Optional[Dict[str, Any]]  # 审查详细结果
    censor_reason: Optional[str]  # 敏感原因
    
    # ========== Media 媒体生成 ==========
    media_generated: Optional[bool]  # 媒体是否已生成
    media_url: Optional[str]  # 媒体 URL（如果有）
    
    # ========== Knowledge 知识更新 ==========
    knowledge_updated: Optional[bool]  # 知识库是否已更新
    entities_extracted: Optional[int]  # 提取的实体数量
    
    # ========== 状态控制 ==========
    status: str  # 工作流状态：processing, completed, failed, blocked
    current_agent: Optional[str]  # 当前执行的 agent 名称
    error: Optional[str]  # 错误信息（如果有）
    error_traceback: Optional[str]  # 错误堆栈（用于调试）
    
    # ========== 扩展字段（用于特定工作流类型）==========
    feedback: Optional[str]  # 用户反馈（用于修订）
    previous_context: Optional[List[Dict[str, Any]]]  # 前文上下文（用于生成）
    character_bios: Optional[List[Dict[str, Any]]]  # 人物设定（兼容字段）
    world_setting: Optional[str]  # 世界观设定（兼容字段）
    
    # ========== 元数据 ==========
    created_at: Optional[str]  # 创建时间（ISO 格式）
    updated_at: Optional[str]  # 更新时间（ISO 格式）
