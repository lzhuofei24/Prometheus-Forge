import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_IMPL"] = "chromadb.telemetry.posthog.Posthog"

from pathlib import Path
import sys
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

import streamlit as st
from src.utils.file_manager import ProjectManager
from src.utils.novel_query import NovelQuery
from src.core.config import Settings
import time

st.set_page_config(
    page_title="检索助手 - Novel-Agent",
    page_icon="🔍",
    layout="wide"
)

def init_components():
    if "file_manager" not in st.session_state or st.session_state.file_manager is None:
        try:
            config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
            workspace_root = Path(config.paths.workspace)
            st.session_state.file_manager = ProjectManager(workspace_root)
            st.session_state.workspace_root = workspace_root
        except Exception as e:
            st.error(f"初始化失败: {e}")
            st.session_state.file_manager = None
            st.session_state.workspace_root = None
    
    if "query" not in st.session_state or st.session_state.query is None:
        if st.session_state.file_manager and hasattr(st.session_state, 'workspace_root'):
            st.session_state.query = NovelQuery(st.session_state.workspace_root)
    
    if "search_results" not in st.session_state:
        st.session_state.search_results = None
    
    if "vector_indexer" not in st.session_state:
        st.session_state.vector_indexer = None

def main():
    init_components()
    
    st.title("🔍 检索助手")
    st.markdown("从已索引的小说内容中检索最相似的文本片段")
    
    if st.session_state.file_manager is None:
        st.error("系统未正确初始化，请返回主页")
        return
    
    file_manager = st.session_state.file_manager
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if st.session_state.query is None:
            st.error("查询对象未初始化")
            return
            
        novels = st.session_state.query.list_novels()
        
        scope = st.radio(
            "检索范围",
            ["全部小说", "指定小说"],
            horizontal=True,
            key="search_scope"
        )
        
        selected_novel = None
        if scope == "指定小说" and novels:
            selected_novel = st.selectbox(
                "选择小说",
                novels,
                key="search_novel"
            )
            
            # 确保 indexer 已初始化并缓存
            if st.session_state.vector_indexer is None:
                from src.rag.indexer import VectorIndexer
                from pathlib import Path
                persist_dir = Path(st.session_state.workspace_root).parent / "data" / "novel_content_db"
                try:
                    st.session_state.vector_indexer = VectorIndexer(persist_directory=persist_dir, collection_name="novel_content")
                except Exception:
                    pass  # 如果初始化失败，方法内部会创建新的
            
            # 使用缓存的 indexer
            status = file_manager.get_index_status(selected_novel, indexer=st.session_state.vector_indexer)
            if status["indexed"]:
                col_status, col_delete = st.columns([3, 1])
                with col_status:
                    st.info(f"✅ 已索引 {status['chunk_count']} 个文本片段")
                with col_delete:
                    if st.button("🗑️ 删除索引", key=f"delete_index_{selected_novel}", type="secondary"):
                        if st.session_state.get(f"confirm_delete_{selected_novel}", False):
                            try:
                                delete_result = file_manager.delete_novel_index(selected_novel, indexer=st.session_state.vector_indexer)
                                if delete_result.get("success"):
                                    st.success(f"✅ 已删除 {delete_result.get('deleted_count', 0)} 个索引片段")
                                    st.session_state[f"confirm_delete_{selected_novel}"] = False
                                    st.rerun()
                                else:
                                    st.error(f"❌ 删除失败: {delete_result.get('error', '未知错误')}")
                            except Exception as e:
                                st.error(f"❌ 删除异常: {str(e)}")
                        else:
                            st.session_state[f"confirm_delete_{selected_novel}"] = True
                            st.warning("⚠️ 再次点击确认删除")
                            st.rerun()
            else:
                st.warning("⚠️ 该小说尚未索引")
                if st.button("立即索引", key=f"index_{selected_novel}"):
                    progress_bar = st.progress(0, text="准备索引...")
                    status_text = st.empty()
                    
                    import logging
                    import sys
                    
                    # 临时设置日志级别为 INFO
                    root_logger = logging.getLogger()
                    original_level = root_logger.level
                    root_logger.setLevel(logging.INFO)
                    
                    # 添加 Streamlit 日志处理器
                    log_messages = []
                    class StreamlitLogHandler(logging.Handler):
                        def emit(self, record):
                            log_messages.append(self.format(record))
                            if len(log_messages) > 50:
                                log_messages.pop(0)
                            # 更新进度显示
                            if "[索引]" in record.getMessage():
                                msg = record.getMessage()
                                if "章节" in msg and "/" in msg:
                                    try:
                                        parts = msg.split("处理章节")[1].split(":")[0].strip()
                                        current, total = parts.split("/")
                                        progress = int(current) / int(total)
                                        progress_bar.progress(progress, text=f"正在索引第 {current}/{total} 章...")
                                    except:
                                        pass
                                status_text.text(msg[-100:] if len(msg) > 100 else msg)
                    
                    handler = StreamlitLogHandler()
                    handler.setFormatter(logging.Formatter('%(message)s'))
                    root_logger.addHandler(handler)
                    
                    try:
                        # 传入缓存的 indexer（如果有）
                        result = file_manager.index_novel_content(
                            selected_novel, 
                            indexer=st.session_state.vector_indexer
                        )
                        
                        # 缓存 indexer 供下次使用
                        if "indexer" in result:
                            st.session_state.vector_indexer = result["indexer"]
                        
                        # 恢复日志级别
                        root_logger.setLevel(original_level)
                        root_logger.removeHandler(handler)
                        
                        progress_bar.progress(1.0, text="索引完成！")
                        
                        if "error" in result:
                            st.error(f"❌ 索引失败: {result['error']}")
                        else:
                            st.success(f"✅ 索引完成！")
                            st.info(f"📊 已索引 {result['indexed_chapters']} 章，共 {result['total_chunks']} 个片段")
                            if result.get('skipped_chapters', 0) > 0:
                                st.warning(f"⚠️ 跳过 {result['skipped_chapters']} 章（内容不足或缺失）")
                            if result.get('failed_chapters'):
                                st.error(f"❌ 失败 {len(result['failed_chapters'])} 章: {result['failed_chapters']}")
                        
                        # 显示日志
                        with st.expander("📋 详细日志", expanded=False):
                            st.text("\n".join(log_messages[-30:]))
                    except Exception as e:
                        root_logger.setLevel(original_level)
                        root_logger.removeHandler(handler)
                        st.error(f"❌ 索引异常: {str(e)}")
                        import traceback
                        with st.expander("查看错误详情"):
                            st.code(traceback.format_exc())
                    
                    st.rerun()
    
    with col2:
        if novels:
            with st.expander("📊 索引管理", expanded=False):
                for novel in novels:
                    status = file_manager.get_index_status(novel, indexer=st.session_state.vector_indexer)
                    if status["indexed"]:
                        st.text(f"✅ {novel}")
                        st.caption(f"   {status['chunk_count']} chunks")
                        col_idx, col_del = st.columns([1, 1])
                        with col_del:
                            if st.button("🗑️", key=f"del_idx_{novel}", use_container_width=True, help="删除索引"):
                                try:
                                    delete_result = file_manager.delete_novel_index(novel, indexer=st.session_state.vector_indexer)
                                    if delete_result.get("success"):
                                        st.success(f"✅ 已删除")
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"❌ {str(e)}")
                    else:
                        st.text(f"⚪ {novel}")
                        if st.button("索引", key=f"idx_{novel}", use_container_width=True):
                            with st.spinner(f"索引 {novel}..."):
                                result = file_manager.index_novel_content(
                                    novel,
                                    indexer=st.session_state.vector_indexer
                                )
                                # 缓存 indexer
                                if "indexer" in result:
                                    st.session_state.vector_indexer = result["indexer"]
                                if "error" not in result:
                                    st.success(f"✅ {result['total_chunks']} chunks")
                                    st.rerun()
    
    st.divider()
    
    query_text = st.text_area(
        "输入检索文本（至少10个字）",
        height=120,
        placeholder="例如：夜晚的街道上弥漫着雾气，路灯的光芒在雾中若隐若现...",
        key="search_query"
    )
    
    col_a, col_b = st.columns(2)
    with col_a:
        top_k = st.slider("检索数量", 1, 20, 10, key="search_top_k")
    with col_b:
        threshold = st.slider("相似度阈值", 0.0, 1.0, 0.5, 0.05, key="search_threshold")
    
    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 3])
    with col_btn1:
        search_btn = st.button("🔍 开始检索", use_container_width=True, type="primary")
    with col_btn2:
        clear_btn = st.button("🗑️ 清空结果", use_container_width=True)
    
    if clear_btn:
        st.session_state.search_results = None
        st.rerun()
    
    if search_btn:
        if not query_text or len(query_text.strip()) < 10:
            st.error("请输入至少10个字的检索文本")
        else:
            with st.spinner("正在检索..."):
                start_time = time.time()
                
                results = file_manager.search_similar_content(
                    query_text=query_text,
                    novel_name=selected_novel if scope == "指定小说" else None,
                    top_k=top_k,
                    threshold=threshold,
                    indexer=st.session_state.vector_indexer
                )
                
                elapsed = time.time() - start_time
                st.session_state.search_results = {
                    "results": results,
                    "query": query_text,
                    "elapsed": elapsed
                }
    
    if st.session_state.search_results:
        results_data = st.session_state.search_results
        results = results_data["results"]
        elapsed = results_data["elapsed"]
        
        st.divider()
        st.markdown(f"### 📊 检索结果 ({len(results)} 条) - 耗时 {elapsed:.2f}s")
        
        if not results:
            st.warning("未找到相似内容，建议：")
            st.markdown("- 降低相似度阈值")
            st.markdown("- 更换关键词或扩展查询文本")
            st.markdown("- 确认小说已索引")
        else:
            for idx, result in enumerate(results):
                with st.expander(
                    f"{idx+1}️⃣ 相似度：{result['similarity']:.2%} | {result['novel_name']} 第{result['chapter_num']}章",
                    expanded=idx < 3
                ):
                    st.markdown(f"**文本预览：**")
                    st.text_area("预览", result["preview"], height=150, key=f"result_{idx}", disabled=True, label_visibility="collapsed")
                    
                    st.progress(result['similarity'], text=f"相似度: {result['similarity']:.2%}")
                    
                    col_x, col_y = st.columns([1, 3])
                    with col_x:
                        if st.button("📖 定位到章节", key=f"goto_{idx}"):
                            st.session_state.current_novel = result['novel_name']
                            st.session_state.current_chapter = result['chapter_num']
                            st.switch_page("pages/1_写作助手.py")
                    with col_y:
                        st.caption(f"Chunk #{result['chunk_index']}")

if __name__ == "__main__":
    main()
