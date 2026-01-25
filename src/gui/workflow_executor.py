"""
工作流执行器 - 后端执行逻辑
分离前后端，避免Streamlit阻塞导致崩溃
"""

import logging
import traceback
import threading
import time
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from src.core.state import AgentState
from src.workflow.graph import NovelWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """工作流执行器，负责后端逻辑执行"""
    
    def __init__(self, workflow: NovelWorkflow):
        self.workflow = workflow
        self.logs = []
        self.current_node = None
        self.node_start_time = None
        self.novel_name = None
        self.last_critique_score = None
        self.last_critique_comments = None
        self.execution_thread = None
        self.execution_result = None
        self.execution_error = None
        self.is_running = False
        self.task_status = None
        self.pending_updates = []
        import threading
        self.update_lock = threading.Lock()
    
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "time": timestamp,
            "message": message,
            "level": level
        }
        self.logs.append(log_entry)
        logger.log(getattr(logging, level), f"[{timestamp}] {message}")
    
    def execute(
        self,
        initial_state: AgentState,
        update_callback: Optional[Callable] = None,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        执行工作流
        
        Args:
            initial_state: 初始状态
            update_callback: 更新回调函数
            timeout: 超时时间（秒）
            
        Returns:
            执行结果字典，包含：
            - success: 是否成功
            - result: 工作流结果（如果成功）
            - error: 错误信息（如果失败）
            - logs: 执行日志
        """
        self.logs = []
        self.novel_name = initial_state.get('novel_name')
        self.current_node = None
        self.node_start_time = None
        self.is_running = True
        self.execution_result = None
        self.execution_error = None
        self.last_critique_score = None
        self.last_critique_comments = None
        
        self.log("开始执行工作流")
        
        try:
            self.log(f"初始状态: novel={initial_state.get('novel_name')}, chapter={initial_state.get('chapter_num')}")
            
            node_name_map = {
                "world_builder": "构建上下文",
                "novelist": "生成内容",
                "critic": "审稿",
                "publisher": "发布"
            }
            
            def safe_update_callback(node_name: str, node_state: AgentState):
                """安全的更新回调，捕获所有异常"""
                try:
                    display_name = node_name_map.get(node_name, node_name)
                    self.current_node = node_name
                    self.node_start_time = time.time()
                    self.log(f"节点执行: {display_name} ({node_name})")

                    if node_name == "critic":
                        self.last_critique_score = node_state.get("critique_score")
                        self.last_critique_comments = node_state.get("critique_comments", "")
                    
                    with self.update_lock:
                        self.task_status = {
                            "node": node_name,
                            "display": display_name,
                            "novel_name": self.novel_name,
                            "elapsed_time": 0,
                            "state": node_state
                        }
                    
                    if update_callback:
                        try:
                            update_callback(node_name, node_state, self.novel_name, 0)
                        except Exception as e:
                            self.log(f"回调函数执行失败: {str(e)}", "WARNING")
                except Exception as e:
                    self.log(f"更新回调异常: {str(e)}", "ERROR")
            
            self.log("调用 workflow.run()")
            try:
                self.log("准备调用 graph.stream()")
                result = self.workflow.run(initial_state, update_callback=safe_update_callback)
                self.log("workflow.run() 执行完成")
                self.current_node = None
                self.node_start_time = None
            except Exception as run_error:
                self.log(f"workflow.run() 调用异常: {str(run_error)}", "ERROR")
                self.log(f"异常类型: {type(run_error).__name__}", "ERROR")
                import traceback
                error_trace = traceback.format_exc()
                self.log(f"详细堆栈:\n{error_trace}", "ERROR")
                self.current_node = None
                self.node_start_time = None
                raise
            
            if result:
                try:
                    novel_name = initial_state.get("novel_name")
                    chapter_num = initial_state.get("chapter_num")
                    if novel_name and chapter_num:
                        chapter_path = self.workflow.file_manager.get_chapter_path(novel_name, chapter_num)
                        critique_path = chapter_path / "critique.md"
                        meta_path = chapter_path / "meta.json"

                        critique_score = self.last_critique_score
                        critique_comments = self.last_critique_comments
                        if critique_comments is None:
                            critique_comments = ""

                        if not critique_comments and critique_score is not None:
                            critique_comments = f"审稿评分: {critique_score}分\n\n（审稿意见未生成）"
                        if not critique_comments and critique_score is None:
                            critique_comments = "（审稿意见未生成）"

                        if not critique_path.exists():
                            critique_content = "# 审稿意见\n\n"
                            if critique_score is not None:
                                critique_content += f"**审稿评分**: {critique_score}分\n\n"
                            critique_content += f"---\n\n{critique_comments}"
                            self.workflow.file_manager.save_content(critique_path, critique_content)

                        if meta_path.exists():
                            meta = self.workflow.file_manager.load_content(meta_path)
                        else:
                            meta = {}
                        if critique_score is not None:
                            meta["critique_score"] = critique_score
                        if critique_comments:
                            meta["critique_comments"] = critique_comments
                        self.workflow.file_manager.save_content(meta_path, meta)
                except Exception as e:
                    self.log(f"补写审稿文件失败: {str(e)}", "WARNING")

                self.log("工作流执行成功")
                self.is_running = False
                return {
                    "success": True,
                    "result": result,
                    "logs": self.logs
                }
            else:
                self.log("工作流返回空结果", "WARNING")
                self.is_running = False
                return {
                    "success": False,
                    "error": "工作流返回空结果",
                    "logs": self.logs
                }
                
        except KeyboardInterrupt:
            self.log("用户中断执行", "WARNING")
            self.is_running = False
            return {
                "success": False,
                "error": "用户中断了任务执行",
                "logs": self.logs
            }
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            self.log(f"工作流执行失败: {error_msg}", "ERROR")
            self.log(f"错误堆栈:\n{error_trace}", "ERROR")
            self.is_running = False
            
            error_result = {
                "success": False,
                "error": error_msg,
                "traceback": error_trace,
                "logs": self.logs
            }
            self.execution_error = error_result
            return error_result
    
    def get_current_status(self) -> Dict[str, Any]:
        """获取当前执行状态，用于定时更新"""
        if not self.is_running or not self.current_node:
            return None
        
        elapsed_time = int(time.time() - self.node_start_time) if self.node_start_time else 0
        
        return {
            "node": self.current_node,
            "novel_name": self.novel_name,
            "elapsed_time": elapsed_time
        }


def test_workflow_step_by_step(workflow: NovelWorkflow, initial_state: AgentState):
    """
    逐步测试工作流，用于诊断问题
    
    Args:
        workflow: 工作流实例
        initial_state: 初始状态
    """
    logger.info("=" * 60)
    logger.info("开始逐步测试工作流")
    logger.info("=" * 60)
    
    try:
        logger.info("步骤1: 测试 world_builder 节点")
        state = workflow._world_builder_node(initial_state.copy())
        logger.info(f"✓ world_builder 完成, state keys: {list(state.keys())}")
        
        logger.info("步骤2: 测试 novelist 节点")
        state = workflow._novelist_node(state)
        logger.info(f"✓ novelist 完成, state keys: {list(state.keys())}")
        
        logger.info("步骤3: 测试 critic 节点")
        state = workflow._critic_node(state)
        logger.info(f"✓ critic 完成, state keys: {list(state.keys())}")
        
        logger.info("步骤4: 测试 publisher 节点")
        state = workflow._publisher_node(state)
        logger.info(f"✓ publisher 完成, state keys: {list(state.keys())}")
        
        logger.info("=" * 60)
        logger.info("所有节点测试完成")
        logger.info("=" * 60)
        
        return state
        
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        logger.error(traceback.format_exc())
        raise
