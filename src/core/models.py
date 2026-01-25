# 提示词模板等核心业务模型（与 API 业务模型分开，便于 init_db 注册）
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from src.core.database import Base


class PromptTemplate(Base):
    """提示词模板表：存储各环节 LLM 提示词，不再依赖本地 YAML 或 Git。"""
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, index=True, nullable=False)  # 例如: writer_chapter, censor_check
    content = Column(Text, nullable=False)  # 提示词内容
    description = Column(String(200))  # 功能描述
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
