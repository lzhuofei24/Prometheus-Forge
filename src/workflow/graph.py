from typing import Literal
from langgraph.graph import StateGraph, END
from src.core.state import AgentState
from src.agents.builder import WorldBuilder
from src.agents.novelist import Novelist
from src.agents.editor import ChiefEditor, Critic
from src.agents.orchestrator import OrchestratorAgent
from src.agents.planner import PlannerAgent
from src.agents.writer import WriterAgent
from src.agents.reviewers import ReviewerTeam
from src.utils.file_manager import ProjectManager


class NovelWorkflow:
    def __init__(
        self,
        world_builder,  # Optional[WorldBuilder] - 可以为 None（启动优化）
        novelist: Novelist,
        chief_editor: ChiefEditor,
        critic: Critic,
        file_manager: ProjectManager,
        llm_client=None,
        use_new_architecture: bool = False
    ):
        self.world_builder = world_builder
        self.novelist = novelist
        self.chief_editor = chief_editor
        self.critic = critic
        self.file_manager = file_manager
        self.use_new_architecture = use_new_architecture
        
        if use_new_architecture and llm_client:
            self.orchestrator = OrchestratorAgent(file_manager)
            self.planner = PlannerAgent(llm_client, file_manager)
            self.writer = WriterAgent(llm_client, file_manager)
            self.reviewer_team = ReviewerTeam(llm_client, file_manager)
        
        self.graph = self._build_graph()
    
    def _build_graph(self):
        if self.use_new_architecture:
            return self._build_new_graph()
        else:
            return self._build_legacy_graph()
    
    def _build_new_graph(self):
        """新架构：分层多Agent"""
        workflow = StateGraph(AgentState)
        
        workflow.add_node("orchestrator_init", self._orchestrator_init_node)
        workflow.add_node("world_builder", self._world_builder_node)
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("writer", self._writer_node)
        workflow.add_node("reviewer", self._reviewer_node)
        workflow.add_node("orchestrator_decision", self._orchestrator_decision_node)
        workflow.add_node("publisher", self._publisher_node)
        
        workflow.set_entry_point("orchestrator_init")
        
        workflow.add_conditional_edges(
            "orchestrator_init",
            self._route_from_init,
            {
                "world_builder": "world_builder",
                "planner": "planner",
                "writer": "writer",
                "reviewer": "reviewer",
                "publisher": "publisher"
            }
        )
        
        workflow.add_conditional_edges(
            "world_builder",
            self._route_after_world_builder,
            {
                "planner": "planner",
                "writer": "writer",
                "reviewer": "reviewer",
                "publisher": "publisher"
            }
        )
        
        workflow.add_conditional_edges(
            "planner",
            self._route_after_planner,
            {
                "writer": "writer",
                "publisher": "publisher"
            }
        )
        
        workflow.add_conditional_edges(
            "writer",
            self._route_after_writer,
            {
                "reviewer": "reviewer",
                "publisher": "publisher"
            }
        )
        
        workflow.add_conditional_edges(
            "reviewer",
            self._route_after_reviewer,
            {
                "orchestrator_decision": "orchestrator_decision"
            }
        )
        
        workflow.add_conditional_edges(
            "orchestrator_decision",
            self._route_from_decision,
            {
                "planner": "planner",
                "writer": "writer",
                "publisher": "publisher"
            }
        )
        
        workflow.add_edge("publisher", END)
        
        return workflow.compile()
    
    def _build_legacy_graph(self):
        """旧架构：保持向后兼容"""
        workflow = StateGraph(AgentState)
        
        workflow.add_node("world_builder", self._world_builder_node)
        workflow.add_node("novelist", self._novelist_node)
        workflow.add_node("critic", self._critic_node)
        workflow.add_node("publisher", self._publisher_node)
        
        workflow.set_entry_point("world_builder")
        
        workflow.add_edge("world_builder", "novelist")
        workflow.add_edge("novelist", "critic")
        
        workflow.add_conditional_edges(
            "critic",
            self._should_approve,
            {
                "approve": "publisher",
                "reject": "novelist"
            }
        )
        
        workflow.add_edge("publisher", END)
        
        return workflow.compile()
    
    def _world_builder_node(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("_world_builder_node 开始执行")
            state["current_node"] = "world_builder"
            
            # ⚡ 优化：如果 world_builder 未初始化（启动优化），跳过上下文构建
            if self.world_builder is None:
                logger.warning("world_builder 未初始化，跳过上下文构建（基础功能仍可用）")
                state["context"] = ""
                state["world_setting"] = ""
                state["previous_context"] = ""
                return state
            
            logger.info("调用 world_builder.build_context()")
            state = self.world_builder.build_context(state)
            logger.info("world_builder.build_context() 完成")
            return state
        except Exception as e:
            logger.error(f"_world_builder_node 执行失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _novelist_node(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("_novelist_node 开始执行")
            state["current_node"] = "novelist"
            
            # 获取反馈（用于迭代重写）
            feedback = state.get("actionable_feedback")
            revision_count = state.get("revision_count", 0)
            
            if feedback and revision_count > 0:
                logger.info(f"🔄 迭代重写（第 {revision_count} 次）: {feedback[:100]}...")
            
            if not state.get("outline"):
                logger.info("生成大纲")
                state = self.novelist.generate_outline(state)
                outline = state.get("outline")
                if outline and state.get("novel_name") and state.get("chapter_num"):
                    try:
                        from src.core.db_service import DatabaseService
                        novel = DatabaseService.get_or_create_novel(state["novel_name"])
                        DatabaseService.save_outline(novel.id, state["chapter_num"], outline)
                    except Exception as e:
                        logger.warning("大纲写入数据库失败（已写入文件）: %s", e)
            
            logger.info("生成正文")
            # 传递feedback给generate_draft
            state = self.novelist.generate_draft(state, feedback=feedback)
            logger.info("_novelist_node 完成")
            return state
        except Exception as e:
            logger.error(f"_novelist_node 执行失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _critic_node(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("_critic_node 开始执行")
            state["current_node"] = "critic"
            logger.info("调用 critic.critique()")
            state = self.critic.critique(state)
            critique_score = state.get('critique_score')
            critique_comments = state.get('critique_comments', '')
            actionable_feedback = state.get('actionable_feedback', '')
            
            logger.info(f"审稿完成: score={critique_score}")
            logger.info(f"comments: {repr(critique_comments[:100]) if critique_comments else 'None'}")
            logger.info(f"actionable_feedback: {repr(actionable_feedback[:100]) if actionable_feedback else 'None'}")
            
            if state.get("character_updates"):
                if self.world_builder is not None:
                    logger.info("更新人物设定")
                    state = self.world_builder.update_global_settings(state)
                else:
                    logger.warning("world_builder 未初始化，跳过人物设定更新")
            
            revision_count = state.get("revision_count", 0)
            should_approve = self.critic.should_approve(state)
            logger.info(f"审稿结果: should_approve={should_approve}, revision_count={revision_count}")
            
            if not should_approve:
                state["revision_count"] = revision_count + 1
                logger.info(f"📊 Score {critique_score}. Retrying with feedback: {actionable_feedback[:150] if actionable_feedback else 'No specific feedback'}")
                logger.info(f"需要重写，revision_count 更新为 {state['revision_count']}")
                
                # 确保feedback被保存到state供下一轮使用
                if not actionable_feedback:
                    state["actionable_feedback"] = critique_comments  # 降级使用comments
                    logger.warning("未获取到actionable_feedback，使用comments作为反馈")
            
            logger.info("_critic_node 完成")
            return state
        except Exception as e:
            logger.error(f"_critic_node 执行失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _publisher_node(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("_publisher_node 开始执行")
            logger.info(f"publisher节点接收到的state keys: {list(state.keys())}")
            logger.info(f"publisher节点接收到的critique_score: {state.get('critique_score')}")
            logger.info(f"publisher节点接收到的critique_comments: {repr(state.get('critique_comments', '')[:100]) if state.get('critique_comments') else 'None'}")
            state["current_node"] = "publisher"
            state["current_stage"] = "published"
            self._save_stage_progress(state, "published")
            novel_name = state["novel_name"]
            chapter_num = state["chapter_num"]
            
            chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
            meta_path = chapter_path / "meta.json"
            content_path = chapter_path / "content.md"
            
            draft_content = state.get("draft_content", "")
            if not draft_content and content_path.exists():
                draft_content = self.file_manager.load_content(content_path)
            
            if meta_path.exists():
                meta = self.file_manager.load_content(meta_path)
            else:
                meta = {}
            
            meta["status"] = "published"
            from datetime import datetime
            meta["updated_at"] = datetime.now().isoformat()
            
            if draft_content:
                extracted_title = self._extract_title_from_content(draft_content)
                if extracted_title:
                    meta["title"] = extracted_title
                elif not meta.get("title"):
                    meta["title"] = ""
            
            critique_comments = state.get("critique_comments", "")
            critique_score = state.get("critique_score", None)
            
            logger.info(f"发布节点: critique_comments类型={type(critique_comments)}, 长度={len(critique_comments) if critique_comments else 0}, 值={repr(critique_comments[:100]) if critique_comments else 'None'}")
            logger.info(f"发布节点: critique_score={critique_score}")
            logger.info(f"发布节点: state中所有keys={list(state.keys())}")
            
            if critique_score is not None:
                meta["critique_score"] = critique_score
                logger.info(f"审稿评分已保存到meta.json: {critique_score}")
            else:
                logger.warning("审稿评分未找到，可能审稿节点未执行")
            
            if critique_comments:
                meta["critique_comments"] = critique_comments
                logger.info("审稿意见已保存到meta.json")
            elif critique_score is not None:
                critique_comments = f"审稿评分: {critique_score}分\n\n（审稿意见未生成）"
                meta["critique_comments"] = critique_comments
                logger.info("审稿意见为空，但存在评分，使用默认审稿意见")
            else:
                critique_comments = "（审稿意见未生成）"
                meta["critique_comments"] = critique_comments
                logger.info("审稿意见和评分都为空，使用默认审稿意见")
            
            critique_path = chapter_path / "critique.md"
            critique_content = f"# 审稿意见\n\n"
            if critique_score is not None:
                critique_content += f"**审稿评分**: {critique_score}分\n\n"
            critique_content += f"---\n\n{critique_comments if critique_comments else '（审稿意见未生成）'}"
            logger.info(f"准备保存critique.md到: {critique_path}")
            self.file_manager.save_content(critique_path, critique_content)
            logger.info(f"审稿意见已保存到critique.md: {critique_path}")
            
            self.file_manager.save_content(meta_path, meta)
            logger.info("meta.json 保存完成")
            
            state["status"] = "published"
            logger.info("_publisher_node 完成")
            return state
        except Exception as e:
            logger.error(f"_publisher_node 执行失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    def _extract_title_from_content(self, content: str) -> str:
        import re
        lines = content.strip().split('\n')
        for line in lines[:10]:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                title = re.sub(r'^#+\s*', '', line).strip()
                title = re.sub(r'^《[^》]+》\s*', '', title)
                title = re.sub(r'^第\d+章[：:\s]*', '', title).strip()
                if title and len(title) < 50:
                    return title
            elif len(line) < 50 and not line.startswith('```'):
                title = re.sub(r'^《[^》]+》\s*', '', line)
                title = re.sub(r'^第\d+章[：:\s]*', '', title).strip()
                if title:
                    return title
        return ""
    
    def _orchestrator_init_node(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[新架构] orchestrator_init_node 开始")
        
        state["current_node"] = "orchestrator_init"
        state = self.orchestrator.init_state(state)
        next_step = self.orchestrator.decide_next_step(state)
        state["_next_step"] = next_step
        
        # 更新meta.json记录当前stage
        self._save_stage_progress(state, "orchestrator_init")
        
        logger.info(f"[新架构] 初始化完成，下一步: {next_step}")
        return state
    
    def _planner_node(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[新架构] planner_node 开始")
        
        state["current_node"] = "planner"
        self._save_stage_progress(state, "planner")
        
        state = self.planner.plan_chapter(state)
        next_step = self.orchestrator.decide_next_step(state)
        state["_next_step"] = next_step
        
        logger.info(f"[新架构] 规划完成，下一步: {next_step}")
        return state
    
    def _writer_node(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[新架构] writer_node 开始")
        
        state["current_node"] = "writer"
        self._save_stage_progress(state, "writer")
        
        rewrite_type = state.get("rewrite_type", "none")
        target_scenes = state.get("target_scenes", [])
        
        if rewrite_type == "partial" and target_scenes:
            logger.info(f"[新架构] 局部重写模式，场景: {target_scenes}")
            state = self.writer.write_scenes(state, scene_ids=target_scenes)
        else:
            logger.info("[新架构] 全文写作模式")
            state = self.writer.write_scenes(state)
        
        next_step = self.orchestrator.decide_next_step(state)
        state["_next_step"] = next_step
        
        logger.info(f"[新架构] 写作完成，下一步: {next_step}")
        return state
    
    def _reviewer_node(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[新架构] reviewer_node 开始")
        
        state["current_node"] = "reviewer"
        self._save_stage_progress(state, "reviewer")
        
        state = self.reviewer_team.review_parallel(state)
        
        if state.get("character_updates"):
            logger.info("[新架构] 更新人物设定")
            state = self.world_builder.update_global_settings(state)
        
        state["_next_step"] = "orchestrator_decision"
        
        logger.info("[新架构] 审稿完成，进入决策节点")
        return state
    
    def _orchestrator_decision_node(self, state: AgentState) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[新架构] orchestrator_decision_node 开始")
        
        state["current_node"] = "orchestrator_decision"
        self._save_stage_progress(state, "orchestrator_decision")
        
        next_step = self.orchestrator.decide_next_step(state)
        state["_next_step"] = next_step
        
        logger.info(f"[新架构] 决策完成，下一步: {next_step}")
        return state
    
    def _route_from_init(self, state: AgentState) -> str:
        return state.get("_next_step", "world_builder")
    
    def _route_after_world_builder(self, state: AgentState) -> str:
        return state.get("_next_step", "planner")
    
    def _route_after_planner(self, state: AgentState) -> str:
        return state.get("_next_step", "writer")
    
    def _route_after_writer(self, state: AgentState) -> str:
        return state.get("_next_step", "reviewer")
    
    def _route_after_reviewer(self, state: AgentState) -> str:
        return state.get("_next_step", "orchestrator_decision")
    
    def _route_from_decision(self, state: AgentState) -> str:
        return state.get("_next_step", "publisher")
    
    def _save_stage_progress(self, state: AgentState, stage_name: str):
        """保存当前阶段到meta.json，供GUI轮询显示"""
        try:
            novel_name = state.get("novel_name")
            chapter_num = state.get("chapter_num")
            if not novel_name or not chapter_num:
                return
            
            chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
            meta_path = chapter_path / "meta.json"
            
            if meta_path.exists():
                meta = self.file_manager.load_content(meta_path)
            else:
                meta = {}
            
            meta["current_stage"] = stage_name
            from datetime import datetime
            meta["stage_updated_at"] = datetime.now().isoformat()
            
            self.file_manager.save_content(meta_path, meta)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"保存stage进度失败: {e}")
    
    def _should_approve(self, state: AgentState) -> Literal["approve", "reject"]:
        if self.critic.should_approve(state):
            return "approve"
        else:
            return "reject"
    
    def run(self, initial_state: AgentState, update_callback=None) -> AgentState:
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("NovelWorkflow.run() 开始执行")
            logger.info(f"初始状态 keys: {list(initial_state.keys())}")
            
            if update_callback:
                logger.info("使用 stream 模式执行（带回调）")
                final_state = initial_state
                try:
                    logger.info("开始迭代 graph.stream()")
                    event_count = 0
                    final_state = initial_state
                    try:
                        for event in self.graph.stream(initial_state):
                            event_count += 1
                            logger.info(f"收到事件 #{event_count}: {list(event.keys())}")
                            
                            for node_name, node_state in event.items():
                                logger.info(f"处理节点: {node_name}")
                                
                                if node_name == "critic":
                                    score = node_state.get("critique_score")
                                    comments = node_state.get("critique_comments", "")
                                    logger.info(f"[审稿节点] score={score}, comments长度={len(comments)}")
                                
                                if node_name == "publisher":
                                    score = node_state.get("critique_score")
                                    comments = node_state.get("critique_comments", "")
                                    logger.info(f"[发布节点] 从state读取: score={score}, comments类型={type(comments)}, comments长度={len(comments) if comments else 0}, comments值前100字符={repr(comments[:100]) if comments else 'None'}")
                                    logger.info(f"[发布节点] state中所有keys: {list(node_state.keys())}")
                                try:
                                    if update_callback:
                                        logger.info(f"调用回调函数: {node_name}")
                                        if callable(update_callback):
                                            try:
                                                import inspect
                                                sig = inspect.signature(update_callback)
                                                if len(sig.parameters) > 2:
                                                    novel_name = node_state.get("novel_name", "")
                                                    update_callback(node_name, node_state, novel_name, 0)
                                                else:
                                                    update_callback(node_name, node_state)
                                            except:
                                                update_callback(node_name, node_state)
                                        logger.info(f"回调函数完成: {node_name}")
                                    final_state = node_state
                                    logger.info(f"节点 {node_name} 处理完成")
                                except Exception as callback_error:
                                    logger.error(f"回调函数执行失败 ({node_name}): {str(callback_error)}")
                                    import traceback
                                    logger.error(traceback.format_exc())
                                    raise
                        
                        logger.info(f"stream 迭代完成，共 {event_count} 个事件")
                        return final_state
                    except StopIteration:
                        logger.info("stream 迭代正常结束")
                        return final_state
                    except Exception as stream_iter_error:
                        logger.error(f"stream 迭代异常: {str(stream_iter_error)}")
                        import traceback
                        logger.error(traceback.format_exc())
                        raise
                except Exception as stream_error:
                    logger.error(f"graph.stream() 执行失败: {str(stream_error)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    raise
            else:
                logger.info("使用 invoke 模式执行（无回调）")
                try:
                    result = self.graph.invoke(initial_state)
                    logger.info("graph.invoke() 执行完成")
                    return result
                except Exception as invoke_error:
                    logger.error(f"graph.invoke() 执行失败: {str(invoke_error)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    raise
        except Exception as e:
            logger.error(f"NovelWorkflow.run() 异常: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise