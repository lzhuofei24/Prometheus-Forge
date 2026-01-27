"""
WebSocket 路由：推送 LangGraph 节点状态变更 (Node Start / Node End)，供前端 useWorkflowStream 订阅。
"""
from __future__ import annotations

import asyncio
import logging
import queue
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])

# workflow_id -> set of WebSocket
_connections: Dict[str, Set[WebSocket]] = {}
# 全局队列：(workflow_id, event_dict)，由 LangGraph 流写入，消费者广播到对应连接
_stream_queue: queue.Queue = queue.Queue()
_consumer_started = False


async def _broadcast_consumer():
    """后台任务：从 _stream_queue 取事件并广播到该 workflow 的所有 WS。"""
    global _consumer_started
    _consumer_started = True
    loop = asyncio.get_event_loop()
    while True:
        try:
            workflow_id, event = await asyncio.to_thread(_stream_queue.get)
            if workflow_id is None:
                break
            conns = _connections.get(workflow_id) or set()
            dead = set()
            for ws in conns:
                try:
                    await ws.send_json({"workflow_id": workflow_id, **event})
                except Exception as e:
                    logger.debug("ws send failed: %s", e)
                    dead.add(ws)
            for ws in dead:
                conns.discard(ws)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("broadcast_consumer error: %s", e)


def push_workflow_event(workflow_id: str, kind: str, node: str, data: Dict[str, Any]) -> None:
    """由 LangGraph 流式运行处调用，投递到队列。"""
    try:
        _stream_queue.put_nowait((workflow_id, {"kind": kind, "node": node, "data": data}))
    except Exception as e:
        logger.warning("push_workflow_event failed: %s", e)


def start_broadcast_consumer():
    """在 app 启动时调用，启动后台广播任务。"""
    global _consumer_started
    if _consumer_started:
        return
    try:
        asyncio.create_task(_broadcast_consumer())
        _consumer_started = True
    except RuntimeError:
        pass


@router.websocket("/workflow")
async def workflow_stream_ws(
    websocket: WebSocket,
    workflow_id: str = Query(..., description="订阅的工作流 id"),
):
    """订阅指定 workflow_id 的节点状态变更。"""
    await websocket.accept()
    if workflow_id not in _connections:
        _connections[workflow_id] = set()
    _connections[workflow_id].add(websocket)
    start_broadcast_consumer()
    try:
        await websocket.send_json({"kind": "subscribed", "workflow_id": workflow_id})
        while True:
            try:
                _ = await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        _connections.get(workflow_id, set()).discard(websocket)
