"""提示词模板 API：列表、按 key 查询、更新。"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.models import PromptTemplate
from src.api.schemas.prompts import PromptSchema, PromptUpdate, PromptCreate

router = APIRouter(prefix="/api/prompts", tags=["Prompts"])

# 当前代码中实际按 key 解析的提示词（prompt_loader / 各 handler 使用）
# 未在 DB 中配置时会回退到 config/prompts/*.yaml
EXPECTED_KEYS = [
    "fiction_system",  # 创作合规系统提示，各 Agent 共用
    "writing",         # config/prompts/writing.yaml
    "critique",        # config/prompts/critique.yaml
    "extraction",      # config/prompts/extraction.yaml
    "plot_check",      # config/prompts/plot_check.yaml
    "style_check",     # config/prompts/style_check.yaml
    "character_check", # config/prompts/character_check.yaml
]


@router.get("/expected-keys")
async def get_expected_keys():
    """返回系统使用的所有预期 key，用于前端合并展示「已配置 + 未配置」"""
    return {"keys": EXPECTED_KEYS}


@router.get("", response_model=list[PromptSchema])
async def list_prompts(db: AsyncSession = Depends(get_db)):
    """返回所有提示词模板列表"""
    result = await db.execute(
        select(PromptTemplate).order_by(PromptTemplate.key)
    )
    rows = result.scalars().all()
    return [
        PromptSchema(
            id=r.id,
            key=r.key,
            content=r.content or "",
            description=r.description,
            is_active=r.is_active if r.is_active is not None else True,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get("/{key}", response_model=PromptSchema)
async def get_prompt(key: str, db: AsyncSession = Depends(get_db)):
    """按 key 获取单个提示词"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.key == key)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return PromptSchema(
        id=row.id,
        key=row.key,
        content=row.content or "",
        description=row.description,
        is_active=row.is_active if row.is_active is not None else True,
        updated_at=row.updated_at,
    )


@router.put("/{key}", response_model=PromptSchema)
async def update_prompt(
    key: str,
    body: PromptUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新指定 key 的 content / description / is_active"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.key == key)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Prompt not found")
    if body.content is not None:
        row.content = body.content
    if body.description is not None:
        row.description = body.description
    if body.is_active is not None:
        row.is_active = body.is_active
    row.updated_at = datetime.utcnow()
    await db.flush()
    await db.commit()
    await db.refresh(row)
    return PromptSchema(
        id=row.id,
        key=row.key,
        content=row.content or "",
        description=row.description,
        is_active=row.is_active if row.is_active is not None else True,
        updated_at=row.updated_at,
    )


@router.post("", response_model=PromptSchema)
async def create_prompt(
    body: PromptCreate,
    db: AsyncSession = Depends(get_db),
):
    """（可选）创建新提示词"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.key == body.key)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Prompt key '{body.key}' already exists")
    row = PromptTemplate(
        key=body.key,
        content=body.content or "",
        description=body.description,
        is_active=body.is_active,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    await db.refresh(row)
    return PromptSchema(
        id=row.id,
        key=row.key,
        content=row.content or "",
        description=row.description,
        is_active=row.is_active if row.is_active is not None else True,
        updated_at=row.updated_at,
    )
