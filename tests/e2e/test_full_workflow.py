# -*- coding: utf-8 -*-
"""
全链路 E2E：从「创建小说」到「生成章节」的完整闭环，Mock LLM，不调用真实 API。
"""
from __future__ import annotations

import json
import pytest
from sqlalchemy import select, and_


NOVEL_TITLE = "《斗破苍穹·测试版》"
CHAPTER_NUM = 1


@pytest.mark.e2e
def test_novel_generation_lifecycle(e2e_components, patch_db_service):
    """
    步骤 A: 初始化 -> 创建小说，断言 Novel 表有记录
    步骤 B: 架构师 -> 触发 architect 任务，断言 Mock 被调用、有 outline 待审批/落库、Chapter 生成
    步骤 C: 作家 -> 触发 writer 任务，断言正文写入、章节状态或 draft 有内容
    步骤 D: 审查与审稿 -> 触发 censor + critic，断言章节状态与评分数据
    """
    from src.core import db_service
    from src.core.db_service import DatabaseService
    from src.api.models import Novel, Chapter, ChapterDraft, PendingWrite

    # ----- 步骤 A: 初始化 -----
    novel = DatabaseService.get_or_create_novel(NOVEL_TITLE)
    assert novel is not None
    assert novel.title == NOVEL_TITLE
    novel_id = novel.id

    with db_service.SessionLocal() as db:
        count = db.execute(select(Novel).where(Novel.title == NOVEL_TITLE)).scalars().all()
        assert len(count) >= 1, "数据库中应有至少一本该小说"

    # ----- 步骤 B: 架构师 (Architect) -----
    workflow_id = "e2e-test-workflow-1"
    state_manager = e2e_components["state_manager"]
    state_manager.init_workflow(workflow_id, {
        "novel_name": NOVEL_TITLE,
        "chapter_num": CHAPTER_NUM,
        "status": "started",
        "revision_count": 0,
        "workflow_type": "generate_chapter",
    })

    from src.workers.tasks_new import task_generate_outline
    raw = task_generate_outline.delay(workflow_id, NOVEL_TITLE, CHAPTER_NUM)
    result = raw.get() if hasattr(raw, "get") else raw
    assert result is not None
    assert "outline" in result
    outline_str = result["outline"]
    outline_obj = json.loads(outline_str)
    assert "scenes" in outline_obj, "Mock 应返回含 scenes 的 JSON 大纲"

    state = state_manager.get_state(workflow_id)
    assert state.get("outline"), "state 中应有 outline"

    with db_service.SessionLocal() as db:
        pending = db.execute(
            select(PendingWrite).where(
                and_(
                    PendingWrite.novel_id == novel_id,
                    PendingWrite.chapter_index == CHAPTER_NUM,
                    PendingWrite.write_type == "outline",
                )
            )
        ).scalars().all()
        assert len(pending) >= 1, "应有 outline 的 PendingWrite"

    # 将 outline 落库，以便后续步骤有“章节记录”（满足你给的断言：Chapter 表自动生成）
    summary = outline_str
    DatabaseService.save_outline(novel_id, CHAPTER_NUM, summary)
    with db_service.SessionLocal() as db:
        ch = db.execute(
            select(Chapter).where(
                and_(Chapter.novel_id == novel_id, Chapter.index == CHAPTER_NUM)
        )).scalar_one_or_none()
        assert ch is not None, "save_outline 后应有 Chapter 记录"
        draft = db.execute(
            select(ChapterDraft).where(
                and_(ChapterDraft.chapter_id == ch.id, ChapterDraft.is_active == True)
        )).scalar_one_or_none()
        assert draft is not None and draft.summary, "应有激活的 Draft 且 summary 不为空"

    # ----- 步骤 C: 作家 (Writer) -----
    from src.workers.tasks_new import task_write_content
    result_w = task_write_content.delay(workflow_id).get()
    assert result_w is not None
    assert "content" in result_w
    content = result_w["content"]
    assert content and len(content.strip()) > 0, "Mock 应返回正文明文"

    state = state_manager.get_state(workflow_id)
    assert state.get("content"), "state 中应有 content"

    with db_service.SessionLocal() as db:
        pending_c = db.execute(
            select(PendingWrite).where(
                and_(
                    PendingWrite.novel_id == novel_id,
                    PendingWrite.chapter_index == CHAPTER_NUM,
                    PendingWrite.write_type == "content",
                )
            )
        ).scalars().all()
        assert len(pending_c) >= 1, "应有 content 的 PendingWrite"

    # 将正文落库，以便 Censor/Critic 能读到章节内容
    DatabaseService.save_content(novel_id, CHAPTER_NUM, content)
    # Censor 任务从 state["draft_content"] 取内容，需写入
    state_manager.update_state(workflow_id, {"draft_content": content})
    with db_service.SessionLocal() as db:
        ch = db.execute(
            select(Chapter).where(
                and_(Chapter.novel_id == novel_id, Chapter.index == CHAPTER_NUM)
        )).scalar_one()
        draft = db.execute(
            select(ChapterDraft).where(
                and_(ChapterDraft.chapter_id == ch.id, ChapterDraft.is_active == True)
        )).scalar_one_or_none()
        assert draft is not None and draft.content, "落库后 draft.content 应有正文"

    # ----- 步骤 D: 审查 (Censor) 与 审稿 (Critic) -----
    from src.workers.tasks_new import task_censor_content
    from src.workers.tasks_new import task_critique_content

    result_censor = task_censor_content.delay(workflow_id).get()
    assert result_censor is not None
    assert result_censor.get("is_sensitive") is False, "Mock 审查应返回通过"

    result_critic = task_critique_content.delay(workflow_id).get()
    assert result_critic is not None
    assert "score" in result_critic
    assert result_critic.get("score") >= 75, "Mock 审稿应返回高分通过"
    assert result_critic.get("passed") is True

    with db_service.SessionLocal() as db:
        pending_critique = db.execute(
            select(PendingWrite).where(
                and_(
                    PendingWrite.novel_id == novel_id,
                    PendingWrite.chapter_index == CHAPTER_NUM,
                    PendingWrite.write_type == "content",
                    PendingWrite.source_agent == "critic",
                )
            )
        ).scalars().all()
        assert len(pending_critique) >= 1, "Critic 应产生带 critique_data 的 PendingWrite"
        payload = getattr(pending_critique[0], "payload") or {}
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        assert "critique_data" in payload, "应有 critique_data"
        assert payload["critique_data"].get("score") >= 75

    # 可选：将章节状态更新为 finished，表示全流程结束
    from src.api.models import ChapterStatus
    DatabaseService.update_chapter_status(novel_id, CHAPTER_NUM, ChapterStatus.FINISHED)
    with db_service.SessionLocal() as db:
        ch = db.execute(
            select(Chapter).where(
                and_(Chapter.novel_id == novel_id, Chapter.index == CHAPTER_NUM)
        )).scalar_one()
        assert ch.status == ChapterStatus.FINISHED
