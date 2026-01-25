# 提示词模板等核心业务模型（与 API 业务模型分开，便于 init_db 注册）
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from src.core.database import Base


# 默认/通用模板的工作流类型存储值（空串表示不区分工作流或默认）
PROMPT_WORKFLOW_DEFAULT = ""


class PromptTemplate(Base):
    """提示词模板表：按 key + workflow_type 存储各环节 LLM 提示词。workflow_type 为空表示默认/通用。"""
    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("key", "workflow_type", name="uq_prompt_key_workflow"),)

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), index=True, nullable=False)  # 例如: architect, writer_builder
    workflow_type = Column(String(50), nullable=False, default=PROMPT_WORKFLOW_DEFAULT)  # 空串=默认，或 generate_chapter / outline_only 等
    content = Column(Text, nullable=False)  # 提示词内容
    description = Column(String(200))  # 功能描述
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
