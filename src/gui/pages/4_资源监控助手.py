"""
资源监控助手页面

实时监控系统 Token 消耗和成本统计
"""

import streamlit as st
import redis
import os
from pathlib import Path

# ========================================
# 页面配置
# ========================================
st.set_page_config(
    page_title="资源监控助手",
    page_icon="📊",
    layout="wide"
)

st.title("📊 资源监控助手")
st.caption("Resource Monitor - Token & Cost Tracking")

# ========================================
# Redis 连接
# ========================================
@st.cache_resource
def get_redis_client():
    """获取 Redis 连接（缓存）"""
    try:
        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=0,
            decode_responses=True,
            socket_connect_timeout=2
        )
        client.ping()
        return client
    except Exception as e:
        st.error(f"❌ Redis 连接失败: {e}")
        st.info("请确保 Redis 服务已启动 (`docker-compose up -d`)")
        return None

redis_client = get_redis_client()

if redis_client is None:
    st.stop()

# ========================================
# 获取统计数据
# ========================================
def get_stats():
    """从 Redis 获取统计数据"""
    try:
        api_calls = redis_client.get("stats:api_calls")
        prompt_tokens = redis_client.get("stats:prompt_tokens")
        completion_tokens = redis_client.get("stats:completion_tokens")
        image_calls = redis_client.get("stats:image_calls")
        image_cost = redis_client.get("stats:image_cost")
        
        return {
            "api_calls": int(api_calls) if api_calls else 0,
            "prompt_tokens": float(prompt_tokens) if prompt_tokens else 0.0,
            "completion_tokens": float(completion_tokens) if completion_tokens else 0.0,
            "image_calls": int(image_calls) if image_calls else 0,
            "image_cost": float(image_cost) if image_cost else 0.0
        }
    except Exception as e:
        st.error(f"获取统计数据失败: {e}")
        return {
            "api_calls": 0,
            "prompt_tokens": 0.0,
            "completion_tokens": 0.0,
            "image_calls": 0,
            "image_cost": 0.0
        }

stats = get_stats()

# ========================================
# 计算指标
# ========================================
total_tokens = stats["prompt_tokens"] + stats["completion_tokens"]

# 成本估算（DeepSeek-V3 @ OpenRouter 费率）
# Prompt: $0.30 / 1M tokens, Completion: $1.20 / 1M tokens
text_cost = (stats["prompt_tokens"] * 0.30 + stats["completion_tokens"] * 1.20) / 1_000_000
estimated_cost = text_cost + stats["image_cost"]

# ========================================
# 核心指标展示
# ========================================
st.subheader("📈 核心指标")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="累计调用次数",
        value=f"{stats['api_calls']:,}",
        help="自系统启动以来的 API 调用总次数"
    )

with col2:
    # Token 单位转换
    if total_tokens >= 1_000_000:
        token_display = f"{total_tokens / 1_000_000:.2f}M"
    elif total_tokens >= 1_000:
        token_display = f"{total_tokens / 1_000:.1f}k"
    else:
        token_display = f"{int(total_tokens)}"
    
    st.metric(
        label="总 Token 消耗",
        value=token_display,
        help="输入和输出 Token 的总和"
    )

with col3:
    st.metric(
        label="图片生成次数",
        value=f"{stats['image_calls']:,}",
        help="累计图片生成次数"
    )

with col4:
    st.metric(
        label="预估成本 (USD)",
        value=f"${estimated_cost:.4f}",
        help="文本 + 图片总成本"
    )

st.divider()

# ========================================
# 详细统计
# ========================================
st.subheader("📊 详细统计")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 输入 Token (Prompt)")
    st.markdown(f"**数量**: {stats['prompt_tokens']:,.0f}")
    if total_tokens > 0:
        prompt_ratio = (stats['prompt_tokens'] / total_tokens) * 100
        st.markdown(f"**占比**: {prompt_ratio:.1f}%")
        st.progress(prompt_ratio / 100)
    st.markdown(f"**成本**: ${(stats['prompt_tokens'] * 0.30) / 1_000_000:.4f}")

with col2:
    st.markdown("### 输出 Token (Completion)")
    st.markdown(f"**数量**: {stats['completion_tokens']:,.0f}")
    if total_tokens > 0:
        completion_ratio = (stats['completion_tokens'] / total_tokens) * 100
        st.markdown(f"**占比**: {completion_ratio:.1f}%")
        st.progress(completion_ratio / 100)
    st.markdown(f"**成本**: ${(stats['completion_tokens'] * 1.20) / 1_000_000:.4f}")

with col3:
    st.markdown("### 图片生成")
    st.markdown(f"**数量**: {stats['image_calls']:,} 张")
    if estimated_cost > 0:
        image_ratio = (stats['image_cost'] / estimated_cost) * 100
        st.markdown(f"**成本占比**: {image_ratio:.1f}%")
        st.progress(image_ratio / 100)
    st.markdown(f"**成本**: ${stats['image_cost']:.4f}")

st.divider()

# ========================================
# 数据表格
# ========================================
st.subheader("📋 数据汇总")

import pandas as pd

df = pd.DataFrame([
    {
        "类型": "文本生成",
        "指标": "API 调用次数",
        "数值": f"{stats['api_calls']:,}",
        "单位": "次"
    },
    {
        "类型": "文本生成",
        "指标": "输入 Token",
        "数值": f"{stats['prompt_tokens']:,.0f}",
        "单位": "tokens"
    },
    {
        "类型": "文本生成",
        "指标": "输出 Token",
        "数值": f"{stats['completion_tokens']:,.0f}",
        "单位": "tokens"
    },
    {
        "类型": "文本生成",
        "指标": "总 Token",
        "数值": f"{total_tokens:,.0f}",
        "单位": "tokens"
    },
    {
        "类型": "文本生成",
        "指标": "文本成本",
        "数值": f"{text_cost:.6f}",
        "单位": "USD"
    },
    {
        "类型": "图片生成",
        "指标": "生成次数",
        "数值": f"{stats['image_calls']:,}",
        "单位": "张"
    },
    {
        "类型": "图片生成",
        "指标": "图片成本",
        "数值": f"{stats['image_cost']:.6f}",
        "单位": "USD"
    },
    {
        "类型": "总计",
        "指标": "总成本",
        "数值": f"{estimated_cost:.6f}",
        "单位": "USD"
    }
])

st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()

# ========================================
# 管理操作
# ========================================
st.subheader("⚙️ 管理操作")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("#### 📥 导出统计")
    if st.button("导出为 JSON", use_container_width=True):
        import json
        from datetime import datetime
        
        export_data = {
            "export_time": datetime.now().isoformat(),
            "stats": stats,
            "metadata": {
                "text_cost": text_cost,
                "total_cost": estimated_cost,
                "total_tokens": total_tokens
            }
        }
        
        json_str = json.dumps(export_data, indent=2, ensure_ascii=False)
        st.download_button(
            label="💾 下载 JSON 文件",
            data=json_str,
            file_name=f"stats_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True
        )

with col2:
    st.markdown("#### 📤 导入统计")
    uploaded_file = st.file_uploader("选择 JSON 文件", type=["json"], label_visibility="collapsed")
    if uploaded_file is not None:
        try:
            import json
            import_data = json.load(uploaded_file)
            
            if "stats" in import_data:
                imported_stats = import_data["stats"]
                
                # 显示预览
                st.info(f"导入数据：{imported_stats.get('api_calls', 0)} 次调用")
                
                if st.button("确认导入（覆盖当前数据）", type="secondary", use_container_width=True):
                    try:
                        pipe = redis_client.pipeline()
                        pipe.set("stats:api_calls", imported_stats.get("api_calls", 0))
                        pipe.set("stats:prompt_tokens", imported_stats.get("prompt_tokens", 0))
                        pipe.set("stats:completion_tokens", imported_stats.get("completion_tokens", 0))
                        pipe.set("stats:image_calls", imported_stats.get("image_calls", 0))
                        pipe.set("stats:image_cost", imported_stats.get("image_cost", 0))
                        pipe.execute()
                        st.success("✅ 统计数据已导入")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ 导入失败: {e}")
            else:
                st.error("❌ 无效的 JSON 格式")
        except Exception as e:
            st.error(f"❌ 文件解析失败: {e}")

with col3:
    st.markdown("#### 🔴 重置数据")
    if st.button("重置所有统计", type="primary", use_container_width=True):
        try:
            redis_client.delete("stats:api_calls")
            redis_client.delete("stats:prompt_tokens")
            redis_client.delete("stats:completion_tokens")
            redis_client.delete("stats:image_calls")
            redis_client.delete("stats:image_cost")
            st.success("✅ 统计数据已重置")
            st.rerun()
        except Exception as e:
            st.error(f"❌ 重置失败: {e}")
    st.caption("⚠️ 重置后无法恢复")

# ========================================
# 页脚说明
# ========================================
st.divider()

with st.expander("💡 费率说明"):
    st.markdown("""
    **费率标准**（2026年1月 - 已更新）
    
    | 服务 | 费率 |
    |------|------|
    | 文本输入 (Prompt) | $0.30 / 1M tokens |
    | 文本输出 (Completion) | $1.20 / 1M tokens |
    | 图片生成 | $0.20 / image (估算) |
    
    **说明**：
    - **DeepSeek-V3** @ OpenRouter 文本费率（已验证准确）
    - **Gemini 2.5 Flash Image** @ OpenRouter 图片费率
      - Input: $0.30/M tokens
      - Output: $2.50/M tokens  
      - Image tokens: $30/M tokens（自动计入output）
      - 实际测试: 100 input + 1,303 output ≈ $0.0388/image
    - 本系统从API response读取实际token消耗，精确计算成本
    - 统计数据存储在 Redis 中，已启用持久化（RDB+AOF）
    - 本页面仅供参考，请以 OpenRouter 账单为准
    """)

with st.expander("🔧 技术细节"):
    st.markdown("""
    **统计实现**：
    - 文本埋点：`src/core/llm.py` 的 `LLMClient.chat()` 方法
    - 图片埋点：`src/workers/tasks.py` 的 `generate_image_task()` 方法
    - 存储方式：Redis (db=0)
    - Key 格式：
      - `stats:api_calls`: 文本API累计调用次数
      - `stats:prompt_tokens`: 累计输入 Token
      - `stats:completion_tokens`: 累计输出 Token
      - `stats:image_calls`: 图片生成累计次数
      - `stats:image_cost`: 图片生成累计成本
    
    **数据持久化**：
    - ✅ Redis RDB: 60秒内至少1个key变化就保存快照
    - ✅ Redis AOF: 每秒同步一次操作日志
    - ✅ 数据卷: 挂载到 `redis_data` 卷，重启后数据保留
    - ✅ 导出/导入: JSON格式，支持跨系统迁移
    
    **持久化机制**：
    - RDB: 定期保存完整快照，恢复快但可能丢失最近1分钟数据
    - AOF: 记录每次写操作，数据安全性高
    - 双持久化: 结合两者优点，最大程度保证数据安全
    """)
