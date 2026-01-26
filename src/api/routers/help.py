"""帮助与系统概念：列表、按 key 查询、更新。概念仅通过数据库查询得到，用于帮助页展示与全站术语统一。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel

from src.core.database import get_db
from src.api.models import SystemConcept

router = APIRouter(prefix="/api/help", tags=["help"])


class ConceptIn(BaseModel):
    label: str
    description: Optional[str] = None
    scope: Optional[str] = None
    sort_order: int = 0


class ConceptOut(BaseModel):
    id: str
    key: str
    label: str
    description: Optional[str] = None
    scope: Optional[str] = None
    sort_order: int


# 默认概念（key -> label, description），首次无数据时写入
DEFAULT_CONCEPTS = [
    ("flow_type", "流程类型", "如「生成新章节」「仅生成大纲」等，表示一种任务流程的模板。在流程监控中切换的是流程类型；在写作助手、审批助手中选择的「启动形式」也对应流程类型。", "workflow", 10),
    ("run", "运行", "一次具体的任务执行，有唯一运行 ID。一次「运行」属于某种「流程类型」，会经过多个环节（架构师、写作、审稿等）直到结束。", "workflow", 20),
    ("start_form", "启动形式", "与「流程类型」同义，偏重「以何种方式启动」的含义。审批助手中「启动形式」即按流程类型筛选。", "approval", 30),
    ("workflow_monitor", "流程监控", "用于查看各环节队列、拓扑与调度的页面。页面内可切换「流程类型」查看不同模板的拓扑。", "nav", 40),
    ("pending_write", "待审批写入", "Agent 产出的大纲或正文在落库前需用户审批，这些待落库记录称为待审批写入。", "approval", 50),
]


async def _ensure_concepts_seeded(db: AsyncSession) -> None:
    r = await db.execute(select(SystemConcept).limit(1))
    if r.scalar_one_or_none() is not None:
        return
    for key, label, description, scope, sort_order in DEFAULT_CONCEPTS:
        c = SystemConcept(key=key, label=label, description=description or "", scope=scope or "", sort_order=sort_order)
        db.add(c)
    await db.flush()


@router.get("/concepts", response_model=List[ConceptOut])
async def list_concepts(
    scope: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """返回所有系统概念，用于帮助页展示及全站术语展示。可选 scope 筛选。"""
    await _ensure_concepts_seeded(db)
    q = select(SystemConcept).order_by(SystemConcept.sort_order, SystemConcept.key)
    if scope is not None and str(scope).strip():
        q = q.where(SystemConcept.scope == scope.strip())
    r = await db.execute(q)
    rows = r.scalars().all()
    return [ConceptOut(id=x.id, key=x.key, label=x.label, description=x.description, scope=x.scope, sort_order=x.sort_order) for x in rows]


@router.get("/concepts/{key}", response_model=ConceptOut)
async def get_concept(
    key: str,
    db: AsyncSession = Depends(get_db),
):
    """按 key 取单条概念。"""
    await _ensure_concepts_seeded(db)
    r = await db.execute(select(SystemConcept).where(SystemConcept.key == key))
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Concept not found")
    return ConceptOut(id=row.id, key=row.key, label=row.label, description=row.description, scope=row.scope, sort_order=row.sort_order)


@router.put("/concepts/{key}", response_model=ConceptOut)
async def update_concept(
    key: str,
    body: ConceptIn,
    db: AsyncSession = Depends(get_db),
):
    """更新概念的 label、description、scope、sort_order。"""
    await _ensure_concepts_seeded(db)
    r = await db.execute(select(SystemConcept).where(SystemConcept.key == key))
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Concept not found")
    row.label = body.label
    row.description = body.description if body.description is not None else row.description
    row.scope = body.scope if body.scope is not None else (row.scope or "")
    row.sort_order = body.sort_order
    await db.flush()
    await db.refresh(row)
    return ConceptOut(id=row.id, key=row.key, label=row.label, description=row.description, scope=row.scope, sort_order=row.sort_order)
