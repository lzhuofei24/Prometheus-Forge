import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from pathlib import Path
from typing import Optional, Dict, Any, List
import threading
import queue
from datetime import datetime
from ..utils.novel_query import NovelQuery
from ..core.config import Settings
from ..core.llm import LLMClient
from ..core.state import AgentState
from ..rag.indexer import VectorIndexer
from ..rag.retriever import VectorRetriever
from ..agents.builder import WorldBuilder
from ..agents.novelist import Novelist
from ..agents.editor import ChiefEditor, Critic
from ..workflow.graph import NovelWorkflow
from ..utils.file_manager import ProjectManager


class CardFrame(ttk.Frame):
    def __init__(self, parent, text="", font=None, command=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.command = command
        self.config(relief=tk.RAISED, borderwidth=1, style="Card.TFrame")
        
        label = ttk.Label(self, text=text, font=font, cursor="hand2" if command else "", justify=tk.LEFT)
        label.pack(padx=8, pady=6, anchor=tk.W)
        
        if command:
            def on_click(event):
                command()
            label.bind("<Button-1>", on_click)
            self.bind("<Button-1>", on_click)


class NovelViewer:
    def __init__(self, root: tk.Tk, workspace_root: Path):
        self.root = root
        self.root.title("小说查看器")
        
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        self.root.geometry(f"{screen_width}x{screen_height}")
        
        base_size = max(14, int(screen_width / 100))
        self.font_title = ("微软雅黑", base_size + 2, "bold")
        self.font_large = ("微软雅黑", base_size + 1, "bold")
        self.font_medium = ("微软雅黑", base_size)
        self.font_normal = ("微软雅黑", base_size)
        self.font_small = ("微软雅黑", base_size - 2)
        self.font_content = ("微软雅黑", base_size + 1)
        
        self.query = NovelQuery(workspace_root)
        self.current_novel: Optional[str] = None
        self.current_chapter: Optional[int] = None
        self.content_text_widget: Optional[tk.Text] = None
        self.outline_text_widget: Optional[tk.Text] = None
        self.chapter_title_widget: Optional[tk.Entry] = None
        
        self.task_queue = queue.Queue()
        self.running_tasks: Dict[str, Dict[str, Any]] = {}
        self.task_lock = threading.Lock()
        self.update_queue = queue.Queue()
        self.task_refresh_timer = None
        
        config = Settings.load_from_yaml(Path("config/settings.yaml"))
        llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens
        )
        indexer = VectorIndexer(
            persist_directory=Path(config.paths.chroma_db),
            collection_name="novel_chunks"
        )
        retriever = VectorRetriever(indexer.collection)
        file_manager = ProjectManager(workspace_root)
        
        world_builder = WorldBuilder(llm_client, retriever, file_manager)
        novelist = Novelist(llm_client, file_manager)
        chief_editor = ChiefEditor(llm_client, file_manager)
        critic = Critic(llm_client, file_manager)
        
        self.workflow = NovelWorkflow(
            world_builder=world_builder,
            novelist=novelist,
            chief_editor=chief_editor,
            critic=critic,
            file_manager=file_manager
        )
        self.file_manager = file_manager
        
        style = ttk.Style()
        style.configure("Card.TFrame", background="white", relief=tk.RAISED, borderwidth=1)
        
        self.setup_ui()
        self.refresh_novel_list()
        self.start_task_processor()
        self.start_update_processor()
        self.start_task_refresh_timer()
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        left_panel = ttk.Frame(main_frame, width=300)
        left_panel.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        left_panel.columnconfigure(0, weight=1)
        
        right_panel = ttk.Frame(main_frame)
        right_panel.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)
        
        self.setup_left_panel(left_panel)
        self.setup_right_panel(right_panel)
    
    def setup_left_panel(self, parent):
        ttk.Label(parent, text="小说列表", font=self.font_large).grid(row=0, column=0, pady=(0, 10), sticky=tk.W)
        
        novel_canvas_frame = ttk.Frame(parent)
        novel_canvas_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        novel_canvas_frame.columnconfigure(0, weight=1)
        novel_canvas_frame.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        
        novel_canvas = tk.Canvas(novel_canvas_frame, highlightthickness=0)
        novel_scrollbar = ttk.Scrollbar(novel_canvas_frame, orient=tk.VERTICAL, command=novel_canvas.yview)
        self.novel_cards_frame = ttk.Frame(novel_canvas)
        
        novel_canvas_window = novel_canvas.create_window((0, 0), window=self.novel_cards_frame, anchor=tk.NW)
        
        novel_canvas.configure(yscrollcommand=novel_scrollbar.set)
        novel_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        novel_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        def configure_novel_canvas(event):
            canvas_width = event.width
            novel_canvas.itemconfig(novel_canvas_window, width=canvas_width)
        
        novel_canvas.bind('<Configure>', configure_novel_canvas)
        self.novel_canvas = novel_canvas
        self.novel_cards_frame = self.novel_cards_frame
        
        refresh_btn = ttk.Button(parent, text="刷新", command=self.refresh_novel_list)
        refresh_btn.grid(row=2, column=0, pady=(0, 20), sticky=tk.W+tk.E)
        
        ttk.Label(parent, text="任务队列", font=self.font_large).grid(row=3, column=0, pady=(10, 10), sticky=tk.W)
        
        task_canvas_frame = ttk.Frame(parent)
        task_canvas_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        task_canvas_frame.columnconfigure(0, weight=1)
        task_canvas_frame.rowconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)
        
        task_canvas = tk.Canvas(task_canvas_frame, highlightthickness=0)
        task_scrollbar = ttk.Scrollbar(task_canvas_frame, orient=tk.VERTICAL, command=task_canvas.yview)
        self.task_cards_frame = ttk.Frame(task_canvas)
        
        task_canvas_window = task_canvas.create_window((0, 0), window=self.task_cards_frame, anchor=tk.NW)
        
        task_canvas.configure(yscrollcommand=task_scrollbar.set)
        task_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        task_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        def configure_task_canvas(event):
            canvas_width = event.width
            task_canvas.itemconfig(task_canvas_window, width=canvas_width)
        
        task_canvas.bind('<Configure>', configure_task_canvas)
        self.task_canvas = task_canvas
    
    def setup_right_panel(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        header_frame.columnconfigure(0, weight=1)
        
        self.title_label = ttk.Label(header_frame, text="请选择小说", font=self.font_title)
        self.title_label.grid(row=0, column=0, sticky=tk.W)
        
        self.novel_info_label = ttk.Label(header_frame, text="", font=self.font_normal)
        self.novel_info_label.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        button_frame = ttk.Frame(header_frame)
        button_frame.grid(row=2, column=0, sticky=tk.W, pady=(10, 0))
        
        self.new_chapter_btn = ttk.Button(button_frame, text="新建章节", command=self.create_new_chapter, state=tk.DISABLED)
        self.new_chapter_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.save_btn = ttk.Button(button_frame, text="保存", command=self.save_chapter_content, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.rewrite_btn = ttk.Button(button_frame, text="根据意见重写", command=self.rewrite_with_feedback, state=tk.DISABLED)
        self.rewrite_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.delete_chapter_btn = ttk.Button(button_frame, text="删除章节", command=self.delete_chapter, state=tk.DISABLED)
        self.delete_chapter_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.back_btn = ttk.Button(button_frame, text="返回", command=self.back_to_novel_list, state=tk.DISABLED)
        self.back_btn.pack(side=tk.LEFT)
        
        self.save_status_label = ttk.Label(header_frame, text="", font=self.font_normal, foreground="green")
        self.save_status_label.grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        
        self.content_frame = ttk.Frame(parent)
        self.content_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)
        
        self.show_novel_list_view()
    
    def start_task_processor(self):
        def process_task(task):
            task_id = task['task_id']
            task_type = task['type']
            novel_name = task['novel_name']
            chapter_num = task['chapter_num']
            
            with self.task_lock:
                self.running_tasks[task_id] = {
                    'type': task_type,
                    'novel_name': novel_name,
                    'chapter_num': chapter_num,
                    'status': 'running',
                    'start_time': datetime.now()
                }
            
            self.root.after(0, self.update_task_display)
            self.root.after(0, lambda: self.disable_chapter_buttons(novel_name, chapter_num))
            
            try:
                if task_type == 'workflow':
                    result = self._run_workflow_task(task)
                elif task_type == 'rewrite':
                    result = self._rewrite_task(task)
                else:
                    result = None
                
                with self.task_lock:
                    if task_id in self.running_tasks:
                        self.running_tasks[task_id]['status'] = 'completed'
                        self.running_tasks[task_id]['result'] = result
                
                self.update_queue.put({
                    'type': 'task_completed',
                    'task_id': task_id,
                    'novel_name': novel_name,
                    'chapter_num': chapter_num,
                    'task_type': task_type
                })
            except Exception as e:
                with self.task_lock:
                    if task_id in self.running_tasks:
                        self.running_tasks[task_id]['status'] = 'failed'
                        self.running_tasks[task_id]['error'] = str(e)
                
                self.update_queue.put({
                    'type': 'task_failed',
                    'task_id': task_id,
                    'novel_name': novel_name,
                    'chapter_num': chapter_num,
                    'error': str(e)
                })
            finally:
                self.root.after(0, lambda: self.enable_chapter_buttons(novel_name, chapter_num))
                self.root.after(0, self.update_task_display)
        
        def process_tasks():
            while True:
                try:
                    task = self.task_queue.get(timeout=1)
                    thread = threading.Thread(target=lambda: process_task(task), daemon=True)
                    thread.start()
                    self.task_queue.task_done()
                except queue.Empty:
                    continue
        
        thread = threading.Thread(target=process_tasks, daemon=True)
        thread.start()
    
    def start_update_processor(self):
        def process_updates():
            self.root.after(100, self.check_updates)
        
        def check():
            try:
                while True:
                    update = self.update_queue.get_nowait()
                    if update['type'] == 'task_completed':
                        self._handle_task_completed(update)
                    elif update['type'] == 'task_failed':
                        self._handle_task_failed(update)
            except queue.Empty:
                pass
            finally:
                self.root.after(100, process_updates)
        
        self.check_updates = check
        process_updates()
    
    def start_task_refresh_timer(self):
        def refresh():
            self.update_task_display()
            self.task_refresh_timer = self.root.after(100, refresh)
        
        self.task_refresh_timer = self.root.after(100, refresh)
    
    def _run_workflow_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        novel_name = task['novel_name']
        chapter_num = task['chapter_num']
        user_feedback = task.get('user_feedback')
        
        try:
            existing_chapters = self.file_manager.list_chapters(novel_name)
            previous_chapters = [ch for ch in existing_chapters if ch < chapter_num]
            previous_context = None
            
            if previous_chapters:
                previous_context = []
                for ch_num in previous_chapters[-3:]:
                    ch_path = self.file_manager.get_chapter_path(novel_name, ch_num)
                    outline_path = ch_path / "outline.md"
                    if outline_path.exists():
                        outline = self.file_manager.load_content(outline_path)
                        previous_context.append({
                            "chapter_num": ch_num,
                            "outline": outline[:200]
                        })
            
            initial_state: AgentState = {
                "novel_name": novel_name,
                "chapter_num": chapter_num,
                "outline": None,
                "draft_content": None,
                "critique_comments": user_feedback,
                "critique_score": None,
                "revision_count": 0,
                "reference_context": None,
                "character_bios": None,
                "world_setting": None,
                "reference_style": None,
                "character_updates": {},
                "previous_context": previous_context,
                "status": "draft",
                "current_node": None
            }
            
            task_id = task.get('task_id')
            
            def update_callback(node_name: str, node_state: AgentState):
                if task_id:
                    with self.task_lock:
                        if task_id in self.running_tasks:
                            self.running_tasks[task_id]['current_node'] = node_name
                            self.running_tasks[task_id]['state'] = node_state
            
            result = self.workflow.run(initial_state, update_callback=update_callback)
            return result
        except Exception as e:
            raise Exception(f"工作流执行失败: {str(e)}")
    
    def _rewrite_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        novel_name = task['novel_name']
        chapter_num = task['chapter_num']
        user_feedback = task.get('user_feedback')
        rewrite_type = task.get('rewrite_type', 'content')
        
        try:
            chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
            outline_path = chapter_path / "outline.md"
            content_path = chapter_path / "content.md"
            
            existing_outline = None
            existing_content = None
            
            if outline_path.exists():
                existing_outline = self.file_manager.load_content(outline_path)
            if content_path.exists():
                existing_content = self.file_manager.load_content(content_path)
            
            existing_chapters = self.file_manager.list_chapters(novel_name)
            previous_chapters = [ch for ch in existing_chapters if ch < chapter_num]
            previous_context = None
            
            if previous_chapters:
                previous_context = []
                for ch_num in previous_chapters[-3:]:
                    ch_path = self.file_manager.get_chapter_path(novel_name, ch_num)
                    prev_outline_path = ch_path / "outline.md"
                    if prev_outline_path.exists():
                        outline = self.file_manager.load_content(prev_outline_path)
                        previous_context.append({
                            "chapter_num": ch_num,
                            "outline": outline[:200]
                        })
            
            if rewrite_type == 'outline':
                initial_state: AgentState = {
                    "novel_name": novel_name,
                    "chapter_num": chapter_num,
                    "outline": None,
                    "draft_content": None,
                    "critique_comments": user_feedback,
                    "critique_score": None,
                    "revision_count": 0,
                    "reference_context": None,
                    "character_bios": None,
                    "world_setting": None,
                    "reference_style": None,
                    "character_updates": {},
                    "previous_context": previous_context,
                    "status": "draft",
                    "current_node": None
                }
            else:
                initial_state: AgentState = {
                    "novel_name": novel_name,
                    "chapter_num": chapter_num,
                    "outline": existing_outline,
                    "draft_content": None,
                    "critique_comments": user_feedback,
                    "critique_score": None,
                    "revision_count": 0,
                    "reference_context": None,
                    "character_bios": None,
                    "world_setting": None,
                    "reference_style": None,
                    "character_updates": {},
                    "previous_context": previous_context,
                    "status": "draft",
                    "current_node": None
                }
            
            task_id = task.get('task_id')
            
            def update_callback(node_name: str, node_state: AgentState):
                if task_id:
                    with self.task_lock:
                        if task_id in self.running_tasks:
                            self.running_tasks[task_id]['current_node'] = node_name
                            self.running_tasks[task_id]['state'] = node_state
            
            result = self.workflow.run(initial_state, update_callback=update_callback)
            return result
        except Exception as e:
            raise Exception(f"重写任务执行失败: {str(e)}")
    
    def _handle_task_completed(self, update: Dict[str, Any]):
        novel_name = update['novel_name']
        chapter_num = update['chapter_num']
        task_type = update['task_type']
        
        if self.current_novel == novel_name and self.current_chapter == chapter_num:
            self.show_chapter_detail_view(novel_name, chapter_num)
        
        task_id = update['task_id']
        with self.task_lock:
            if task_id in self.running_tasks:
                result = self.running_tasks[task_id].get('result', {})
                score = result.get('critique_score')
                del self.running_tasks[task_id]
        
        self.update_task_display()
        
        if task_type == 'workflow':
            self._show_chapter_completion_dialog(novel_name, chapter_num, score)
        elif task_type == 'rewrite':
            self._show_chapter_completion_dialog(novel_name, chapter_num, None, "根据修改意见重写完成！")
    
    def _show_chapter_completion_dialog(self, novel_name: str, chapter_num: int, score: Optional[int] = None, custom_message: Optional[str] = None):
        dialog = tk.Toplevel(self.root)
        dialog.title("章节生成完成")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        main_frame = ttk.Frame(dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        if custom_message:
            message_text = custom_message
        elif score:
            message_text = f"章节生成完成！评分：{score}分"
        else:
            message_text = "章节生成完成！"
        
        ttk.Label(main_frame, text=message_text, font=self.font_normal).pack(pady=(0, 10))
        ttk.Label(main_frame, text=f"《{novel_name}》 - 第{chapter_num}章", font=self.font_medium).pack(pady=(0, 20))
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack()
        
        def jump_to_chapter():
            dialog.destroy()
            self.current_novel = novel_name
            self.current_chapter = chapter_num
            self.show_chapter_detail_view(novel_name, chapter_num)
            self.refresh_novel_list()
        
        ttk.Button(button_frame, text="跳转到章节", command=jump_to_chapter).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="关闭", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def _handle_task_failed(self, update: Dict[str, Any]):
        task_id = update['task_id']
        error = update.get('error', '未知错误')
        
        with self.task_lock:
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
        
        self.update_task_display()
        messagebox.showerror("错误", f"生成失败：{error}")
    
    def update_task_display(self):
        for widget in self.task_cards_frame.winfo_children():
            widget.destroy()
        
        with self.task_lock:
            tasks = list(self.running_tasks.values())
        
        for i, task in enumerate(tasks):
            status_icon = "🔄" if task['status'] == 'running' else "❌"
            task_type_map = {
                'workflow': '工作流',
                'rewrite': '重写'
            }
            task_type = task_type_map.get(task['type'], task['type'])
            novel_name = task['novel_name']
            chapter_num = task['chapter_num']
            
            if task['status'] == 'running':
                elapsed = (datetime.now() - task['start_time']).total_seconds()
                current_node = task.get('current_node', '')
                node_name_map = {
                    'world_builder': '构建上下文',
                    'novelist': '生成内容',
                    'critic': '审稿',
                    'publisher': '发布'
                }
                node_display = node_name_map.get(current_node, current_node or '初始化')
                display_text = f"{status_icon} {novel_name}\n第{chapter_num}章 - {task_type}\n运行中 ({int(elapsed)}秒) - {node_display}"
            else:
                display_text = f"{status_icon} {novel_name}\n第{chapter_num}章 - {task_type}\n失败"
            
            card = CardFrame(
                self.task_cards_frame,
                text=display_text,
                font=self.font_small
            )
            card.grid(row=i, column=0, sticky=(tk.W, tk.E), padx=2, pady=2)
            self.task_cards_frame.columnconfigure(0, weight=1)
        
        self.task_canvas.update_idletasks()
        self.task_canvas.configure(scrollregion=self.task_canvas.bbox("all"))
    
    def disable_chapter_buttons(self, novel_name: str, chapter_num: int):
        if self.current_novel == novel_name and self.current_chapter == chapter_num:
            self.save_btn.config(state=tk.DISABLED)
            self.rewrite_btn.config(state=tk.DISABLED)
            if self.content_text_widget:
                self.content_text_widget.config(state=tk.DISABLED)
            if self.outline_text_widget:
                self.outline_text_widget.config(state=tk.DISABLED)
            if self.chapter_title_widget:
                self.chapter_title_widget.config(state=tk.DISABLED)
    
    def enable_chapter_buttons(self, novel_name: str, chapter_num: int):
        if self.current_novel == novel_name and self.current_chapter == chapter_num:
            self.save_btn.config(state=tk.NORMAL)
            self.rewrite_btn.config(state=tk.NORMAL)
            if self.content_text_widget:
                self.content_text_widget.config(state=tk.NORMAL)
            if self.outline_text_widget:
                self.outline_text_widget.config(state=tk.NORMAL)
            if self.chapter_title_widget:
                self.chapter_title_widget.config(state=tk.NORMAL)
    
    def show_novel_list_view(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        info_label = ttk.Label(self.content_frame, text="从左侧列表选择小说查看", font=self.font_medium)
        info_label.grid(row=0, column=0, pady=50)
    
    def show_novel_detail_view(self, novel_name: str):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        novel_info = self.query.get_novel_info(novel_name)
        if not novel_info:
            messagebox.showerror("错误", f"无法加载小说信息：{novel_name}")
            return
        
        self.title_label.config(text=f"《{novel_name}》")
        self.novel_info_label.config(text="")
        self.save_status_label.config(text="")
        self.back_btn.config(state=tk.NORMAL)
        self.new_chapter_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.DISABLED)
        self.rewrite_btn.config(state=tk.DISABLED)
        self.delete_chapter_btn.config(state=tk.DISABLED)
        self.content_text_widget = None
        self.outline_text_widget = None
        self.chapter_title_widget = None
        
        main_container = ttk.Frame(self.content_frame)
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=1)
        
        chapters_frame = ttk.Frame(main_container, width=250)
        chapters_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        chapters_frame.columnconfigure(0, weight=1)
        chapters_frame.rowconfigure(1, weight=1)
        
        ttk.Label(chapters_frame, text="目录", font=self.font_large).grid(row=0, column=0, pady=(0, 10), sticky=tk.W)
        
        chapters_canvas = tk.Canvas(chapters_frame, highlightthickness=0)
        chapters_scrollbar = ttk.Scrollbar(chapters_frame, orient=tk.VERTICAL, command=chapters_canvas.yview)
        chapters_cards_frame = ttk.Frame(chapters_canvas)
        
        chapters_canvas_window = chapters_canvas.create_window((0, 0), window=chapters_cards_frame, anchor=tk.NW)
        
        chapters_canvas.configure(yscrollcommand=chapters_scrollbar.set)
        chapters_canvas.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        chapters_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        
        def configure_chapters_canvas(event):
            canvas_width = event.width
            chapters_canvas.itemconfig(chapters_canvas_window, width=canvas_width)
        
        chapters_canvas.bind('<Configure>', configure_chapters_canvas)
        
        chapters_summary = self.query.get_chapters_summary(novel_name)
        
        for i, ch_info in enumerate(chapters_summary):
            title = ch_info.get('title', '')
            if not title:
                title = ""
            else:
                import re
                title = re.sub(r'^第\d+章\s*', '', title).strip()
            
            if title:
                display_text = f"第{ch_info['chapter_num']}章 {title}\n[{ch_info['status']}] {ch_info['word_count']}字"
            else:
                display_text = f"第{ch_info['chapter_num']}章\n[{ch_info['status']}] {ch_info['word_count']}字"
            
            def make_chapter_command(n, ch_num):
                return lambda: self._select_chapter(n, ch_num)
            
            card = CardFrame(
                chapters_cards_frame,
                text=display_text,
                font=self.font_small,
                command=make_chapter_command(novel_name, ch_info['chapter_num'])
            )
            card.grid(row=i, column=0, sticky=(tk.W, tk.E), padx=2, pady=2)
            chapters_cards_frame.columnconfigure(0, weight=1)
        
        chapters_canvas.update_idletasks()
        chapters_canvas.configure(scrollregion=chapters_canvas.bbox("all"))
        
        content_area = ttk.Frame(main_container)
        content_area.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        content_area.columnconfigure(0, weight=1)
        content_area.rowconfigure(0, weight=1)
        
        info_label = ttk.Label(content_area, text="请从左侧目录选择章节查看", font=self.font_medium)
        info_label.grid(row=0, column=0, pady=50)
    
    def show_chapter_detail_view(self, novel_name: str, chapter_num: int):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        chapter_info = self.query.get_chapter_info(novel_name, chapter_num)
        if not chapter_info:
            messagebox.showerror("错误", f"无法加载章节信息：第{chapter_num}章")
            return
        
        task_key = f"{novel_name}_{chapter_num}"
        is_generating = any(
            t['novel_name'] == novel_name and t['chapter_num'] == chapter_num and t['status'] == 'running'
            for t in self.running_tasks.values()
        )
        
        self.title_label.config(text=f"《{novel_name}》 - 第{chapter_num}章")
        self.novel_info_label.config(text="")
        self.save_status_label.config(text="")
        self.back_btn.config(state=tk.NORMAL)
        self.new_chapter_btn.config(state=tk.NORMAL)
        self.save_btn.config(state=tk.NORMAL if not is_generating else tk.DISABLED)
        self.rewrite_btn.config(state=tk.NORMAL if not is_generating else tk.DISABLED)
        self.delete_chapter_btn.config(state=tk.NORMAL if not is_generating else tk.DISABLED)
        
        main_container = ttk.Frame(self.content_frame)
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=1)
        
        chapters_frame = ttk.Frame(main_container, width=250)
        chapters_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        chapters_frame.columnconfigure(0, weight=1)
        chapters_frame.rowconfigure(1, weight=1)
        
        ttk.Label(chapters_frame, text="目录", font=self.font_large).grid(row=0, column=0, pady=(0, 10), sticky=tk.W)
        
        chapters_canvas = tk.Canvas(chapters_frame, highlightthickness=0)
        chapters_scrollbar = ttk.Scrollbar(chapters_frame, orient=tk.VERTICAL, command=chapters_canvas.yview)
        chapters_cards_frame = ttk.Frame(chapters_canvas)
        
        chapters_canvas_window = chapters_canvas.create_window((0, 0), window=chapters_cards_frame, anchor=tk.NW)
        
        chapters_canvas.configure(yscrollcommand=chapters_scrollbar.set)
        chapters_canvas.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        chapters_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        
        def configure_chapters_canvas(event):
            canvas_width = event.width
            chapters_canvas.itemconfig(chapters_canvas_window, width=canvas_width)
        
        chapters_canvas.bind('<Configure>', configure_chapters_canvas)
        
        chapters_summary = self.query.get_chapters_summary(novel_name)
        
        for i, ch_info in enumerate(chapters_summary):
            title = ch_info.get('title', '')
            if not title:
                title = ""
            else:
                import re
                title = re.sub(r'^第\d+章\s*', '', title).strip()
            
            if title:
                display_text = f"第{ch_info['chapter_num']}章 {title}\n[{ch_info['status']}] {ch_info['word_count']}字"
            else:
                display_text = f"第{ch_info['chapter_num']}章\n[{ch_info['status']}] {ch_info['word_count']}字"
            
            def make_chapter_command(n, ch_num):
                return lambda: self._select_chapter(n, ch_num)
            
            card = CardFrame(
                chapters_cards_frame,
                text=display_text,
                font=self.font_small,
                command=make_chapter_command(novel_name, ch_info['chapter_num'])
            )
            if ch_info['chapter_num'] == chapter_num:
                card.config(relief=tk.SUNKEN)
            card.grid(row=i, column=0, sticky=(tk.W, tk.E), padx=2, pady=2)
            chapters_cards_frame.columnconfigure(0, weight=1)
        
        chapters_canvas.update_idletasks()
        chapters_canvas.configure(scrollregion=chapters_canvas.bbox("all"))
        
        content_area = ttk.Frame(main_container)
        content_area.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        content_area.columnconfigure(0, weight=1)
        content_area.rowconfigure(1, weight=1)
        
        main_frame = ttk.Frame(content_area)
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        title_frame.columnconfigure(1, weight=1)
        
        ttk.Label(title_frame, text="章节标题：", font=self.font_normal).grid(row=0, column=0, padx=(0, 10))
        
        meta = chapter_info.get('meta', {})
        chapter_title_full = meta.get('title', "")
        
        import re
        if chapter_title_full:
            chapter_title_display = re.sub(r'^第\d+章\s*', '', chapter_title_full).strip()
        else:
            chapter_title_display = ""
        
        self.chapter_title_widget = ttk.Entry(title_frame, font=self.font_normal)
        self.chapter_title_widget.insert(0, chapter_title_display)
        self.chapter_title_widget.grid(row=0, column=1, sticky=(tk.W, tk.E))
        if is_generating:
            self.chapter_title_widget.config(state=tk.DISABLED)
        
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        content_frame = ttk.Frame(notebook, padding="10")
        notebook.add(content_frame, text="正文")
        
        self.content_text_widget = scrolledtext.ScrolledText(
            content_frame, 
            wrap=tk.WORD, 
            font=self.font_content,
            spacing1=5,
            spacing2=3,
            spacing3=5,
            tabs=('1c', '2c', '3c', '4c')
        )
        self.content_text_widget.pack(fill=tk.BOTH, expand=True)
        self.content_text_widget.insert(tk.END, chapter_info.get('content', '暂无正文'))
        if is_generating:
            self.content_text_widget.config(state=tk.DISABLED)
        
        outline_frame = ttk.Frame(notebook, padding="10")
        notebook.add(outline_frame, text="大纲")
        
        self.outline_text_widget = scrolledtext.ScrolledText(
            outline_frame, 
            wrap=tk.WORD, 
            font=self.font_normal,
            spacing1=3,
            spacing2=2,
            spacing3=3
        )
        self.outline_text_widget.pack(fill=tk.BOTH, expand=True)
        self.outline_text_widget.insert(tk.END, chapter_info.get('outline', '暂无大纲'))
        if is_generating:
            self.outline_text_widget.config(state=tk.DISABLED)
        
        meta_frame = ttk.Frame(notebook, padding="10")
        notebook.add(meta_frame, text="元数据")
        
        meta_text = scrolledtext.ScrolledText(meta_frame, wrap=tk.WORD, font=self.font_normal, spacing1=2, spacing2=1, spacing3=2)
        meta_text.pack(fill=tk.BOTH, expand=True)
        
        meta_text.insert(tk.END, f"章节编号: {meta.get('chapter_num', chapter_num)}\n")
        meta_text.insert(tk.END, f"标题: {meta.get('title', '无')}\n")
        meta_text.insert(tk.END, f"状态: {meta.get('status', 'unknown')}\n")
        meta_text.insert(tk.END, f"字数: {meta.get('word_count', 0)}\n")
        meta_text.insert(tk.END, f"创建时间: {meta.get('created_at', '无')}\n")
        meta_text.insert(tk.END, f"更新时间: {meta.get('updated_at', '无')}\n")
        
        character_states = meta.get('character_states', {})
        if character_states:
            meta_text.insert(tk.END, f"\n=== 人物状态 ===\n")
            for name, state in character_states.items():
                appeared = "出现" if state.get('appeared', False) else "未出现"
                meta_text.insert(tk.END, f"{name}: {appeared}\n")
        
        meta_text.config(state=tk.DISABLED)
    
    def refresh_novel_list(self):
        for widget in self.novel_cards_frame.winfo_children():
            widget.destroy()
        
        novels = self.query.list_novels()
        for i, novel in enumerate(novels):
            chapters_summary = self.query.get_chapters_summary(novel)
            chapter_count = len(chapters_summary)
            display_text = f"{novel}\n({chapter_count}章)"
            
            def make_command(n):
                return lambda: self._select_novel(n)
            
            card = CardFrame(
                self.novel_cards_frame,
                text=display_text,
                font=self.font_normal,
                command=make_command(novel)
            )
            card.grid(row=i, column=0, sticky=(tk.W, tk.E), padx=2, pady=2)
            self.novel_cards_frame.columnconfigure(0, weight=1)
        
        self.novel_canvas.update_idletasks()
        self.novel_canvas.configure(scrollregion=self.novel_canvas.bbox("all"))
    
    def _select_novel(self, novel_name: str):
        self.current_novel = novel_name
        self.current_chapter = None
        self.show_novel_detail_view(novel_name)
    
    
    def create_new_chapter(self, novel_name: Optional[str] = None):
        if not novel_name:
            novel_name = self.current_novel
        
        if not novel_name:
            messagebox.showwarning("警告", "请先选择小说")
            return
        
        next_chapter_num = self.file_manager.get_next_chapter_num(novel_name)
        self.file_manager.init_chapter(novel_name, next_chapter_num)
        self.current_chapter = next_chapter_num
        
        with self.task_lock:
            if any(t['novel_name'] == novel_name and t['chapter_num'] == next_chapter_num and t['status'] == 'running' for t in self.running_tasks.values()):
                messagebox.showwarning("警告", "该章节正在生成中，请稍候...")
                return
        
        task_id = f"{novel_name}_{next_chapter_num}_workflow_{datetime.now().timestamp()}"
        task = {
            'task_id': task_id,
            'type': 'workflow',
            'novel_name': novel_name,
            'chapter_num': next_chapter_num
        }
        
        self.task_queue.put(task)
        self.show_chapter_detail_view(novel_name, next_chapter_num)
    
    def _select_chapter(self, novel_name: str, chapter_num: int):
        self.current_chapter = chapter_num
        self.show_chapter_detail_view(novel_name, chapter_num)
    
    def rewrite_with_feedback(self):
        if not self.current_novel or not self.current_chapter:
            return
        
        with self.task_lock:
            if any(t['novel_name'] == self.current_novel and t['chapter_num'] == self.current_chapter and t['status'] == 'running' for t in self.running_tasks.values()):
                messagebox.showwarning("警告", "该章节正在生成中，请稍候...")
                return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("输入修改意见")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="请选择要重写的内容：", font=self.font_normal).pack(pady=10)
        
        rewrite_type = tk.StringVar(value="content")
        ttk.Radiobutton(dialog, text="重写正文", variable=rewrite_type, value="content").pack(anchor=tk.W, padx=20)
        ttk.Radiobutton(dialog, text="重写大纲", variable=rewrite_type, value="outline").pack(anchor=tk.W, padx=20)
        
        ttk.Label(dialog, text="修改意见：", font=self.font_normal).pack(pady=(20, 5), anchor=tk.W, padx=20)
        
        feedback_text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=self.font_normal, height=10)
        feedback_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        
        def submit():
            feedback = feedback_text.get("1.0", tk.END).strip()
            if not feedback:
                messagebox.showwarning("警告", "请输入修改意见")
                return
            
            dialog.destroy()
            
            try:
                task_id = f"{self.current_novel}_{self.current_chapter}_rewrite_{datetime.now().timestamp()}"
                task = {
                    'task_id': task_id,
                    'type': 'rewrite',
                    'novel_name': self.current_novel,
                    'chapter_num': self.current_chapter,
                    'user_feedback': feedback,
                    'rewrite_type': rewrite_type.get()
                }
                
                self.task_queue.put(task)
                messagebox.showinfo("提示", "已加入任务队列，正在根据修改意见重写...")
            except Exception as e:
                messagebox.showerror("错误", f"添加任务失败：{e}")
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="确定", command=submit).pack(side=tk.RIGHT, padx=5)
    
    def delete_chapter(self):
        if not self.current_novel or not self.current_chapter:
            return
        
        result = messagebox.askyesno("确认删除", f"确定要删除《{self.current_novel}》第{self.current_chapter}章吗？\n此操作不可恢复！")
        if not result:
            return
        
        try:
            chapter_path = self.file_manager.get_chapter_path(self.current_novel, self.current_chapter)
            if chapter_path.exists():
                import shutil
                shutil.rmtree(chapter_path)
            
            self.current_chapter = None
            self.show_novel_detail_view(self.current_novel)
            self.refresh_novel_list()
            messagebox.showinfo("成功", "章节已删除")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败：{e}")
    
    def save_chapter_content(self):
        if not self.current_novel or not self.current_chapter:
            return
        
        if not self.content_text_widget or not self.outline_text_widget:
            return
        
        try:
            content = self.content_text_widget.get("1.0", tk.END).rstrip('\n')
            outline = self.outline_text_widget.get("1.0", tk.END).rstrip('\n')
            chapter_title_input = self.chapter_title_widget.get().strip() if self.chapter_title_widget else ""
            
            chapter_title = chapter_title_input if chapter_title_input else ""
            
            chapter_path = self.file_manager.get_chapter_path(self.current_novel, self.current_chapter)
            
            self.file_manager.save_content(chapter_path / "content.md", content)
            self.file_manager.save_content(chapter_path / "outline.md", outline)
            
            meta_path = chapter_path / "meta.json"
            if meta_path.exists():
                meta = self.file_manager.load_content(meta_path)
            else:
                meta = {}
            
            meta["chapter_num"] = self.current_chapter
            meta["title"] = chapter_title
            meta["word_count"] = len(content)
            meta["updated_at"] = datetime.now().isoformat()
            if not meta.get("created_at"):
                meta["created_at"] = meta["updated_at"]
            
            self.file_manager.save_content(meta_path, meta)
            
            self.save_status_label.config(text="保存成功", foreground="green")
            self.root.after(3000, lambda: self.save_status_label.config(text=""))
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")
    
    def back_to_novel_list(self):
        if self.current_chapter and self.current_novel:
            self.current_chapter = None
            self.content_text_widget = None
            self.outline_text_widget = None
            self.chapter_title_widget = None
            self.save_btn.config(state=tk.DISABLED)
            self.rewrite_btn.config(state=tk.DISABLED)
            self.show_novel_detail_view(self.current_novel)
        elif self.current_novel:
            self.current_novel = None
            self.current_chapter = None
            self.content_text_widget = None
            self.outline_text_widget = None
            self.chapter_title_widget = None
            self.title_label.config(text="请选择小说")
            self.novel_info_label.config(text="")
            self.back_btn.config(state=tk.DISABLED)
            self.new_chapter_btn.config(state=tk.DISABLED)
            self.save_btn.config(state=tk.DISABLED)
            self.rewrite_btn.config(state=tk.DISABLED)
            self.show_novel_list_view()


def main():
    config = Settings.load_from_yaml(Path("config/settings.yaml"))
    workspace_root = Path(config.paths.workspace)
    
    root = tk.Tk()
    app = NovelViewer(root, workspace_root)
    root.mainloop()


if __name__ == "__main__":
    main()
