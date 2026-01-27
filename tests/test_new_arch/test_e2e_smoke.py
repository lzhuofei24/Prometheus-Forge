"""
集成冒烟测试：Mock LLM / _run_handler，通过 API 触发 LangGraph，轮询至 completed，断言状态与审计路径。

需要加载 app（请使用: pytest tests/test_new_arch/test_e2e_smoke.py -v）。
需安装 celery、可用的 conftest（含 async_client、state_manager）。
"""
from __future__ import annotations

import asyncio
import pytest

pytest.importorskip("celery")

from unittest.mock import patch
from httpx import AsyncClient

from src.core.events import AuditLogEntry, EventType, EventSource
from src.core.workflows import WORKFLOW_GENERATE_CHAPTER


@pytest.mark.asyncio
async def test_workflow_start_langgraph_poll_until_completed(
    async_client: AsyncClient,
    state_manager,
):
    """POST /workflow/start (use_langgraph=True) -> 轮询 GET /workflow/{id}/state 至 status=completed；断言审计日志含节点路径。"""
    call_log = []

    def fake_run_handler(workflow_id: str, agent_name: str, state: dict, input_data=None):
        call_log.append(agent_name)
        source_map = {
            "architect": EventSource.AGENT_ARCHITECT,
            "writer": EventSource.AGENT_WRITER,
            "critic": EventSource.AGENT_CRITIC,
            "censor": EventSource.AGENT_CENSOR,
            "knowledge": EventSource.AGENT_KNOWLEDGE,
        }
        ev = source_map.get(agent_name, EventSource.SYSTEM)
        state_manager.add_audit_log(
            workflow_id,
            AuditLogEntry(workflow_id=workflow_id, source=ev, event_type=EventType.TASK_COMPLETED, details={"node": agent_name}),
        )
        if agent_name == "architect":
            return {"outline": "测试大纲", "next_step": "writer"}
        if agent_name == "writer":
            return {"content": "测试正文", "draft_content": "测试正文", "next_step": "censor"}
        if agent_name == "critic":
            return {"critique_score": 90, "next_step": "censor"}
        if agent_name == "censor":
            return {"is_sensitive": False, "next_step": "end", "status": "completed"}
        return {}

    with patch("src.api.routers.workflow.state_manager", state_manager), \
         patch("src.core.workflow_graph._run_handler", side_effect=fake_run_handler):
        r = await async_client.post(
            "/workflow/start",
            json={
                "novel_name": "冒烟小说",
                "chapter_num": 1,
                "workflow_type": WORKFLOW_GENERATE_CHAPTER,
                "use_langgraph": True,
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    workflow_id = body.get("workflow_id")
    assert workflow_id, "应返回 workflow_id"

    for _ in range(50):
        s = await async_client.get(f"/workflow/{workflow_id}/state")
        assert s.status_code == 200, s.text
        data = s.json()
        if data.get("status") == "completed":
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("workflow 未在限定轮数内变为 completed")

    assert data.get("status") == "completed"
    assert data.get("outline") or data.get("draft_content"), "终态应有大纲或正文"

    trace_r = await async_client.get(f"/workflow/{workflow_id}/trace")
    assert trace_r.status_code == 200
    logs = trace_r.json().get("logs") or []
    sources = [lg.get("source", "") for lg in logs]
    assert any("architect" in s or "writer" in s or "critic" in s or "censor" in s for s in sources), \
        "审计日志应包含节点执行路径（knowledge 已脱离工作流）"
