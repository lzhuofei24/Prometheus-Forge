"""提示词模板相关 Pydantic Schema"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class PromptSchema(BaseModel):
    """响应：单个提示词模板"""
    id: int
    key: str
    workflow_type: str = ""  # 空=默认/通用，或 generate_chapter / outline_only 等
    content: str
    description: Optional[str] = None
    is_active: bool = True
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PromptUpdate(BaseModel):
    """请求：更新提示词 (content / description / is_active)"""
    content: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PromptCreate(BaseModel):
    """请求：创建提示词"""
    key: str
    workflow_type: str = ""  # 空=默认，或工作流 id 如 outline_only
    content: str = ""
    description: Optional[str] = None
    is_active: bool = True
