import logging
import json
import time
import redis
from typing import Dict, Any, List, Optional
from datetime import datetime

HEARTBEAT_KEY = "system:controller:heartbeat"
HEARTBEAT_TTL = 30
from src.core.state_manager import StateManager
from src.core.celery_config import celery_app
from src.core.app_settings import get_settings
from src.core.routing import RoutingRule
from src.core.workflows import get_routing_rules, DEFAULT_WORKFLOW_ID

logger = logging.getLogger(__name__)

__all__ = ["CentralController", "RoutingRule"]


class CentralController:
    def __init__(self, state_manager: StateManager, redis_client: redis.Redis):
        self.state_manager = state_manager
        self.redis = redis_client
        self.celery = celery_app
        self.running = False
        
        self.listen_queues = [
            "architect_completed",
            "writer_completed",
            "critic_completed",
            "media_completed",
            "censor_completed"
        ]
        
        self.task_map = {
            "architect": "architect.generate_outline",
            "writer": "writer.write_content",
            "critic": "critic.critique_content",
            "media": "media.generate_media",
            "censor": "censor.check_content"
        }

    def run_loop(self):
        self.running = True
        logger.info("🚀 Central Controller started, listening to completed queues...")
        
        while self.running:
            try:
                # 写入心跳，便于 API 通过 Redis 判定 Controller 在线（不依赖 Celery inspect）
                try:
                    self.redis.setex(HEARTBEAT_KEY, HEARTBEAT_TTL, str(time.time()))
                except Exception as e:
                    logger.debug(f"Heartbeat write failed: {e}")
                
                result = self.redis.blpop(self.listen_queues, timeout=1)
                
                if result:
                    queue_name, raw_data = result
                    self.handle_completion(queue_name, raw_data)
                else:
                    if not self.running:
                        break
                        
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down...")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Error in controller loop: {e}", exc_info=True)
                import time
                time.sleep(1)
        
        logger.info("Central Controller stopped")

    def handle_completion(self, queue_name: str, raw_data: str):
        try:
            data = json.loads(raw_data)
            workflow_id = data.get("workflow_id")
            source_agent = data.get("source")
            status = data.get("status")
            
            logger.info(f"📥 Received completion from {source_agent}, workflow: {workflow_id}, status: {status}")
            
            if status == "SUCCESS":
                output_data = data.get("data", {})
                
                if source_agent == "critic":
                    revision_count = self.state_manager.get_state(workflow_id).get("revision_count", 0)
                    if output_data.get("score", 0) < 75 and revision_count < 3:
                        revision_count += 1
                        output_data["revision_count"] = revision_count
                    elif output_data.get("score", 0) >= 75:
                        output_data["revision_count"] = 0
                
                self.state_manager.update_state(workflow_id, output_data)

                next_agents = self.decide_next_step(workflow_id, source_agent, output_data)
                
                if next_agents:
                    for target_agent in next_agents:
                        self.dispatch_task(workflow_id, target_agent)
                else:
                    if source_agent == "censor" and output_data.get("is_sensitive"):
                        logger.info(f"⏸ Workflow {workflow_id} blocked (censor marked sensitive, needs review)")
                        self.state_manager.update_state(workflow_id, {"status": "blocked"})
                    else:
                        logger.info(f"✅ Workflow {workflow_id} completed (no next steps)")
                        self.state_manager.update_state(workflow_id, {"status": "completed"})
            else:
                error = data.get("error", "Unknown error")
                logger.error(f"❌ Task failed for workflow {workflow_id}: {error}")
                self.state_manager.update_state(workflow_id, {
                    "status": "failed",
                    "error": error
                })
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse completion message: {e}")
        except Exception as e:
            logger.error(f"Error handling completion: {e}", exc_info=True)

    def decide_next_step(
        self, workflow_id: str, source_agent: str, data: Dict[str, Any]
    ) -> List[str]:
        state = self.state_manager.get_state(workflow_id) or {}
        workflow_type = state.get("workflow_type") or DEFAULT_WORKFLOW_ID
        routing_rules = get_routing_rules(workflow_type)

        rule = routing_rules.get(source_agent)
        if not rule:
            logger.warning(
                f"No routing rule for agent: {source_agent} (workflow_type={workflow_type})"
            )
            return []

        next_agents = rule.decide(data)
        logger.info(
            f"🔀 Routing [{workflow_type}]: {source_agent} -> {next_agents}"
        )
        return next_agents

    def dispatch_task(self, workflow_id: str, target_agent: str):
        task_name = self.task_map.get(target_agent)
        if not task_name:
            logger.error(f"Unknown agent: {target_agent}")
            return
        
        state = self.state_manager.get_state(workflow_id)
        if not state:
            logger.error(f"Workflow {workflow_id} state not found")
            return
        
        target_queue = f"{target_agent}_pending"
        
        if target_agent == "architect":
            args = [workflow_id, state.get("novel_name"), state.get("chapter_num")]
        elif target_agent == "writer":
            revision_count = state.get("revision_count", 0)
            if revision_count > 0:
                task_name = "writer.revise_content"
                feedback = state.get("advice") or state.get("critique_comments", "")
                args = [workflow_id, feedback]
            else:
                args = [workflow_id]
        elif target_agent == "critic":
            args = [workflow_id]
        elif target_agent == "media":
            args = [workflow_id]
        elif target_agent == "censor":
            args = [workflow_id]
        else:
            logger.error(f"Unknown task mapping for agent: {target_agent}")
            return
        
        try:
            self.celery.send_task(
                task_name,
                queue=target_queue,
                args=args
            )
            logger.info(f"📤 Dispatched {task_name} to {target_queue} for workflow {workflow_id}")
        except Exception as e:
            logger.error(f"Failed to dispatch task: {e}", exc_info=True)

    def stop(self):
        self.running = False
