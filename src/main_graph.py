"""
LangGraph 工作流执行入口

替代旧的 Controller 循环，使用 LangGraph 状态机编排工作流。
"""
import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from src.workflow.graph import create_workflow_graph
from src.workflow.state import WorkflowState
from src.core.state_manager import StateManager
from src.core.dispatcher import Dispatcher
from src.core.events import EventType, EventSource, AuditLogEntry, EventPayload
from src.core.app_settings import get_settings

# 加载环境变量
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_workflow(
    workflow_id: str,
    novel_name: str,
    chapter_num: int,
    workflow_type: str = "generate_chapter",
    sync_to_redis: bool = True,
) -> WorkflowState:
    """
    执行 LangGraph 工作流
    
    Args:
        workflow_id: 工作流唯一标识
        novel_name: 小说名称
        chapter_num: 章节编号
        workflow_type: 工作流类型（默认：generate_chapter）
        sync_to_redis: 是否同步状态到 Redis（默认：True）
    
    Returns:
        最终的工作流状态
    """
    # 初始化组件
    settings = get_settings()
    state_manager = StateManager(
        redis_host=settings.redis_host,
        redis_port=settings.redis_port,
        redis_db=settings.redis_db,
    )
    dispatcher = Dispatcher(state_manager)
    
    # 1. 初始化 Redis 状态
    initial_state_dict = {
        "novel_name": novel_name,
        "chapter_num": chapter_num,
        "workflow_type": workflow_type,
        "status": "started",
        "revision_count": 0,
    }
    
    if sync_to_redis:
        state_manager.init_workflow(workflow_id, initial_state_dict)
        
        # 记录工作流启动审计日志
        state_manager.add_audit_log(
            workflow_id,
            AuditLogEntry(
                workflow_id=workflow_id,
                source=EventSource.SYSTEM,
                event_type=EventType.WORKFLOW_STARTED,
                details={
                    "novel_name": novel_name,
                    "chapter_num": chapter_num,
                    "workflow_type": workflow_type,
                },
            ),
        )
        
        # 发送工作流启动事件
        event_payload = EventPayload(
            workflow_id=workflow_id,
            event_type=EventType.WORKFLOW_STARTED,
            data=initial_state_dict,
            source=EventSource.SYSTEM,
        )
        dispatcher.handle_event(event_payload)
    
    # 2. 构建初始 WorkflowState
    initial_state: WorkflowState = {
        "workflow_id": workflow_id,
        "novel_name": novel_name,
        "chapter_num": chapter_num,
        "workflow_type": workflow_type,
        "status": "processing",
        "revision_count": 0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    
    # 3. 获取工作流图
    app = create_workflow_graph(workflow_type)
    
    # 4. 运行图（异步流式执行）
    logger.info(f"🚀 开始执行工作流 {workflow_id} (novel={novel_name}, chapter={chapter_num})")
    
    final_state = None
    try:
        async for event in app.astream(initial_state):
            # event 格式: {node_name: node_state}
            for node_name, node_state in event.items():
                logger.info(f"✅ 节点 '{node_name}' 执行完成")
                
                # 更新最终状态
                final_state = node_state
                
                # 同步状态到 Redis（如果启用）
                if sync_to_redis:
                    # 将 WorkflowState 转换为 Redis 状态格式
                    redis_state = {
                        "novel_name": node_state.get("novel_name"),
                        "chapter_num": str(node_state.get("chapter_num", 0)),
                        "workflow_type": node_state.get("workflow_type", "generate_chapter"),
                        "status": node_state.get("status", "processing"),
                        "revision_count": str(node_state.get("revision_count", 0)),
                    }
                    
                    # 添加可选字段
                    if node_state.get("outline"):
                        redis_state["outline"] = node_state["outline"]
                    if node_state.get("draft_content"):
                        redis_state["draft_content"] = node_state["draft_content"]
                    if node_state.get("reference_context"):
                        redis_state["reference_context"] = node_state["reference_context"]
                    if node_state.get("critique_score") is not None:
                        redis_state["critique_score"] = str(node_state["critique_score"])
                    if node_state.get("critique_comments"):
                        redis_state["critique_comments"] = node_state["critique_comments"]
                    if node_state.get("is_sensitive") is not None:
                        redis_state["is_sensitive"] = str(node_state["is_sensitive"])
                    
                    state_manager.update_state(workflow_id, redis_state)
                    
                    # 记录节点完成审计日志
                    # 映射节点名称到 EventSource
                    source_map = {
                        "architect": EventSource.AGENT_ARCHITECT,
                        "writer": EventSource.AGENT_WRITER,
                        "critic": EventSource.AGENT_CRITIC,
                        "censor": EventSource.AGENT_CENSOR,
                        "media": EventSource.AGENT_MEDIA,
                    }
                    source = source_map.get(node_name, EventSource.SYSTEM)
                    
                    state_manager.add_audit_log(
                        workflow_id,
                        AuditLogEntry(
                            workflow_id=workflow_id,
                            source=source,
                            event_type=EventType.TASK_COMPLETED,
                            details={
                                "node": node_name,
                                "state": {k: v for k, v in node_state.items() if k != "workflow_id"},
                            },
                        ),
                    )
        
        # 5. 工作流完成
        if final_state:
            final_status = final_state.get("status", "completed")
            if final_status == "processing":
                final_status = "completed"
            
            if sync_to_redis:
                state_manager.update_state(workflow_id, {"status": final_status})
                
                # 记录工作流完成审计日志（使用 TASK_COMPLETED，因为 WORKFLOW_COMPLETED 不存在）
                state_manager.add_audit_log(
                    workflow_id,
                    AuditLogEntry(
                        workflow_id=workflow_id,
                        source=EventSource.SYSTEM,
                        event_type=EventType.TASK_COMPLETED,
                        details={
                            "final_status": final_status,
                            "critique_score": final_state.get("critique_score"),
                            "revision_count": final_state.get("revision_count", 0),
                            "workflow_completed": True,
                        },
                    ),
                )
            
            logger.info(
                f"🏁 工作流 {workflow_id} 执行完成 (status={final_status}, "
                f"score={final_state.get('critique_score', 'N/A')}, "
                f"revisions={final_state.get('revision_count', 0)})"
            )
        else:
            logger.warning(f"⚠️ 工作流 {workflow_id} 未返回最终状态")
            final_state = initial_state
            final_state["status"] = "unknown"
        
        return final_state
        
    except Exception as e:
        logger.error(f"❌ 工作流 {workflow_id} 执行失败: {e}", exc_info=True)
        
        # 更新错误状态
        error_state = final_state or initial_state
        error_state["status"] = "failed"
        error_state["error"] = str(e)
        import traceback
        error_state["error_traceback"] = traceback.format_exc()
        
        if sync_to_redis:
            state_manager.update_state(workflow_id, {
                "status": "failed",
                "error": str(e),
            })
            
            # 记录错误审计日志（使用 TASK_FAILED，因为 WORKFLOW_FAILED 不存在）
            state_manager.add_audit_log(
                workflow_id,
                AuditLogEntry(
                    workflow_id=workflow_id,
                    source=EventSource.SYSTEM,
                    event_type=EventType.TASK_FAILED,
                    details={"error": str(e), "workflow_failed": True},
                    error=str(e),
                ),
            )
        
        return error_state


async def main():
    """CLI 测试入口（极简回归：50 字微型故事，降低 Token 消耗）"""
    # 极简测试数据：强制生成极短内容，大幅降低 API 调用成本
    workflow_id = str(uuid.uuid4())
    novel_name = "关于烤面包机的50字微型故事"
    chapter_num = 1
    
    print("=" * 60)
    print("LangGraph 回归测试（Token 节约模式）")
    print("=" * 60)
    print(f"Workflow ID: {workflow_id}")
    print(f"Novel: {novel_name}")
    print(f"Chapter: {chapter_num}")
    print("=" * 60)
    print()
    
    try:
        final_state = await run_workflow(
            workflow_id=workflow_id,
            novel_name=novel_name,
            chapter_num=chapter_num,
            workflow_type="generate_chapter",
            sync_to_redis=True,
        )
        
        print()
        print("=" * 60)
        print("工作流执行结果")
        print("=" * 60)
        print(f"状态: {final_state.get('status')}")
        print(f"审稿评分: {final_state.get('critique_score', 'N/A')}")
        print(f"修订次数: {final_state.get('revision_count', 0)}")
        if final_state.get("error"):
            print(f"错误: {final_state['error']}")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断执行")
    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
