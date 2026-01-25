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
from src.core.prompt_manager import PromptRouter

st.set_page_config(
    page_title="Prompt Registry - Novel-Agent",
    page_icon="🧠",
    layout="wide"
)

def init_session_state():
    if "prompt_router" not in st.session_state or st.session_state.prompt_router is None:
        try:
            st.session_state.prompt_router = PromptRouter()
        except Exception as e:
            st.error(f"PromptRouter 初始化失败: {e}")
            st.session_state.prompt_router = None

def main():
    init_session_state()
    
    st.title("🧠 Prompt Registry - 提示词工程台")
    st.markdown("管理风格模板，实现动态提示词路由")
    
    router = st.session_state.prompt_router
    if router is None:
        st.error("PromptRouter 未初始化")
        return
    
    tab_list, tab_add, tab_test = st.tabs(["📋 模板列表", "➕ 新建模板", "🔍 语义路由测试"])
    
    with tab_list:
        st.markdown("### 已存储的风格模板")
        
        col_refresh, col_info = st.columns([1, 4])
        with col_refresh:
            if st.button("🔄 刷新", key="refresh_templates", use_container_width=True):
                if router:
                    router._encoder = None
                st.rerun()
        
        try:
            if router is None:
                st.error("PromptRouter 未初始化")
                return
            
            all_items = router.list_templates()
            
            if all_items is None:
                st.warning("无法获取模板列表")
                return
            
            ids = all_items.get('ids', [])
            metadatas = all_items.get('metadatas', [])
            documents = all_items.get('documents', [])
            
            if ids and len(ids) > 0:
                st.markdown(f"**共 {len(ids)} 个模板**")
                
                for i, template_id in enumerate(ids):
                    metadata = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
                    document = documents[i] if i < len(documents) and documents[i] else ""
                    
                    name = metadata.get('name', template_id) if isinstance(metadata, dict) else template_id
                    description = metadata.get('description', '') if isinstance(metadata, dict) else ''
                    full_content = metadata.get('full_content', document) if isinstance(metadata, dict) else document
                    
                    with st.expander(f"**{name}**", expanded=False):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.markdown(f"**描述 (Small)**: {description}")
                            st.markdown(f"**ID**: `{template_id}`")
                            
                            if full_content:
                                with st.expander("查看完整提示词 (Big)", expanded=False):
                                    st.code(full_content, language="text")
                        
                        with col2:
                            if st.button("删除", key=f"delete_{template_id}", type="secondary"):
                                if router.delete_template(template_id):
                                    st.success(f"已删除模板: {name}")
                                    st.rerun()
                                else:
                                    st.error("删除失败")
            else:
                st.info("暂无模板，请在「新建模板」标签页添加")
        except Exception as e:
            st.error(f"加载模板列表失败: {e}")
            import traceback
            with st.expander("查看错误详情"):
                st.code(traceback.format_exc())
    
    with tab_add:
        st.markdown("### 创建新风格模板")
        st.markdown("""
        **Small-to-Big 策略**:
        - **Name**: 模板的唯一标识
        - **Description (Small)**: 简短描述，用于向量检索（如："打斗场景、激烈战斗、动作描写"）
        - **System Prompt (Big)**: 完整的风格指令，将作为 System Prompt 的一部分
        """)
        
        with st.form("add_template_form", clear_on_submit=True):
            template_name = st.text_input("模板名称 *", placeholder="例如：打斗场景模板")
            template_description = st.text_area(
                "描述 (Small) *", 
                placeholder="简短描述，用于向量检索\n例如：打斗场景、激烈战斗、动作描写、招式对决",
                height=100,
                help="这个描述会被向量化并用于语义匹配"
            )
            template_content = st.text_area(
                "完整提示词 (Big) *", 
                placeholder="完整的风格提示词内容\n例如：\n你是一位擅长描写激烈战斗场面的作家。请使用以下技巧：\n1. 详细描写动作细节\n2. 突出招式名称和效果\n3. 营造紧张氛围...",
                height=300,
                help="这是完整的 System Prompt，会在匹配时使用"
            )
            
            submitted = st.form_submit_button("添加模板", use_container_width=True, type="primary")
            
            if submitted:
                if template_name and template_description and template_content:
                    try:
                        router.add_template(template_name, template_description, template_content)
                        st.success(f"✅ 模板 '{template_name}' 已添加")
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"添加失败: {e}")
                        import traceback
                        with st.expander("查看错误详情"):
                            st.code(traceback.format_exc())
                else:
                    st.warning("请填写所有必填字段（标记 * 的字段）")
    
    with tab_test:
        st.markdown("### 语义路由测试")
        st.markdown("""
        输入一段剧情摘要，系统会通过向量相似度计算，找出最匹配的风格模板。
        
        **工作原理**:
        1. 将输入的剧情摘要向量化
        2. 在 ChromaDB 中搜索最相似的 Description (Small)
        3. 返回匹配的模板及其相似度分数
        """)
        
        test_query = st.text_area(
            "输入测试剧情摘要", 
            placeholder="例如：主角在森林中遇到神秘敌人，双方展开激烈战斗。主角使出绝招，剑气纵横，场面惊心动魄...",
            height=150
        )
        
        if st.button("🔍 匹配测试", use_container_width=True, type="primary"):
            if test_query:
                try:
                    with st.spinner("正在计算相似度..."):
                        best_prompt = router.get_best_prompt(test_query)
                        
                        if best_prompt:
                            st.success("✅ 找到匹配模板")
                            
                            try:
                                collection = router.collection
                                query_embedding = router.encoder.encode(test_query).tolist()
                                results = collection.query(
                                    query_embeddings=[query_embedding],
                                    n_results=1,
                                    include=['metadatas', 'distances']
                                )
                                
                                if results['metadatas'] and len(results['metadatas'][0]) > 0:
                                    matched_meta = results['metadatas'][0][0]
                                    distance = results['distances'][0][0] if results['distances'] and len(results['distances'][0]) > 0 else None
                                    similarity = 1 - distance if distance is not None else None
                                    
                                    col1, col2 = st.columns(2)
                                    
                                    with col1:
                                        st.markdown("#### 匹配结果")
                                        st.markdown(f"**模板名称**: {matched_meta.get('name', 'Unknown')}")
                                        st.markdown(f"**描述**: {matched_meta.get('description', '')}")
                                    
                                    with col2:
                                        if similarity is not None:
                                            st.metric("相似度", f"{similarity:.2%}")
                                            st.metric("距离", f"{distance:.4f}")
                                    
                                    st.divider()
                                    st.markdown("#### 匹配的完整提示词 (Big)")
                                    st.code(best_prompt, language="text")
                                    
                                    st.info("💡 这个提示词会在生成章节时自动注入到 System Prompt 中")
                            except Exception as e:
                                st.warning(f"无法计算相似度: {e}")
                                st.markdown("#### 匹配的完整提示词")
                                st.code(best_prompt, language="text")
                        else:
                            st.warning("⚠️ 未找到匹配的模板")
                            st.info("💡 提示：请确保已创建相关风格的模板")
                except Exception as e:
                    st.error(f"检索失败: {e}")
                    import traceback
                    with st.expander("查看错误详情"):
                        st.code(traceback.format_exc())
            else:
                st.warning("请输入剧情摘要")

if __name__ == "__main__":
    main()
