"""
任务监控助手 - 独立的 Celery 任务监控页面

功能：
- 实时监控 Redis 队列积压情况
- 显示当前活跃的 Worker 任务
- 展示任务历史记录
- 自动刷新（每秒）
"""

import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import streamlit as st
import redis
from datetime import datetime
import json
import time
import base64
import pickle
from celery.result import AsyncResult

from src.core.celery_config import celery_app

# 页面配置
st.set_page_config(
    page_title="任务监控助手",
    page_icon="🚀",
    layout="wide"
)


def init_redis():
    """初始化 Redis 连接"""
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
        return r
    except Exception as e:
        st.error(f"❌ Redis 连接失败: {e}")
        st.info("请确保 Redis 服务正在运行：`docker-compose up -d redis`")
        return None


def get_queue_depth(r: redis.Redis) -> dict:
    """获取队列积压情况
    
    使用多种方法综合检测：
    1. Celery Inspect API（reserved + scheduled）
    2. 扫描所有 List 类型键，匹配队列名称
    3. 直接查询常见键名格式
    """
    queues = {
        'text_queue': '文本生成队列',
        'media_queue': '多媒体队列',
        'rag_queue': 'RAG索引队列'
    }
    
    depths = {name: 0 for name in queues.values()}
    
    # 方法1: 使用 Celery Inspect API 统计 reserved 和 scheduled 任务
    try:
        i = celery_app.control.inspect()
        reserved = i.reserved() or {}
        scheduled = i.scheduled() or {}
        
        # 统计 reserved 任务（已保留但未开始）
        for worker_name, task_list in reserved.items():
            for task in task_list:
                routing_key = task.get('delivery_info', {}).get('routing_key', '')
                if routing_key:
                    if routing_key.startswith('text'):
                        depths['文本生成队列'] += 1
                    elif routing_key.startswith('media'):
                        depths['多媒体队列'] += 1
                    elif routing_key.startswith('rag'):
                        depths['RAG索引队列'] += 1
        
        # 统计 scheduled 任务（已调度但未执行）
        for worker_name, task_list in scheduled.items():
            for task in task_list:
                routing_key = task.get('request', {}).get('routing_key', '')
                if routing_key:
                    if routing_key.startswith('text'):
                        depths['文本生成队列'] += 1
                    elif routing_key.startswith('media'):
                        depths['多媒体队列'] += 1
                    elif routing_key.startswith('rag'):
                        depths['RAG索引队列'] += 1
    except Exception:
        pass
    
    # 方法2: 扫描所有 List 类型键，智能匹配队列名称
    try:
        all_keys = r.keys('*')
        for key in all_keys:
            try:
                if r.type(key) == 'list':
                    length = r.llen(key)
                    if length > 0:
                        key_lower = key.lower()
                        # 匹配文本队列
                        if any(pattern in key_lower for pattern in ['text', 'text_queue', 'text.default']):
                            if 'media' not in key_lower and 'rag' not in key_lower:
                                depths['文本生成队列'] += length
                        # 匹配媒体队列
                        elif any(pattern in key_lower for pattern in ['media', 'media_queue', 'media.default']):
                            if 'text' not in key_lower and 'rag' not in key_lower:
                                depths['多媒体队列'] += length
                        # 匹配 RAG 队列
                        elif any(pattern in key_lower for pattern in ['rag', 'rag_queue', 'rag.default']):
                            if 'text' not in key_lower and 'media' not in key_lower:
                                depths['RAG索引队列'] += length
            except:
                continue
    except Exception:
        pass
    
    # 方法3: 尝试直接使用队列名称查询（常见格式）
    for queue_key, queue_name in queues.items():
        try:
            # 尝试多种键名格式
            key_patterns = [
                queue_key,  # 'text_queue'
                queue_key.replace('_queue', ''),  # 'text'
                f'tasks.{queue_key}',  # 'tasks.text_queue'
                f'tasks.{queue_key.replace("_queue", "")}',  # 'tasks.text'
                f'tasks.{queue_key.replace("_queue", "")}.default',  # 'tasks.text.default'
                f'celery.{queue_key}',  # 'celery.text_queue'
            ]
            
            for key_pattern in key_patterns:
                try:
                    test_depth = r.llen(key_pattern)
                    if test_depth is not None and test_depth > 0:
                        depths[queue_name] += test_depth
                        break
                except:
                    continue
        except:
            continue
    
    return depths


def get_active_tasks():
    """获取当前活跃的任务"""
    try:
        i = celery_app.control.inspect()
        active = i.active()
        
        if not active:
            return []
        
        tasks = []
        for worker_name, task_list in active.items():
            for task in task_list:
                tasks.append({
                    'worker': worker_name,
                    'task_id': task.get('id', 'N/A'),
                    'task_name': task.get('name', 'Unknown'),
                    'args': task.get('args', ''),
                    'time_start': task.get('time_start', 0)
                })
        
        return tasks
    except Exception as e:
        st.warning(f"无法获取活跃任务: {e}")
        return []


def get_task_history(r: redis.Redis, limit: int = 20) -> list:
    """获取任务历史记录"""
    try:
        # 获取所有 celery-task-meta keys
        pattern = 'celery-task-meta-*'
        keys = r.keys(pattern)
        
        if not keys:
            return []
        
        # 限制数量并按时间排序
        keys = sorted(keys, reverse=True)[:limit]
        
        tasks = []
        for key in keys:
            try:
                data = r.get(key)
                if data:
                    meta = json.loads(data)
                    task_id = key.replace('celery-task-meta-', '')
                    
                    tasks.append({
                        'task_id': task_id,
                        'status': meta.get('status', 'UNKNOWN'),
                        'result': meta.get('result', ''),
                        'date_done': meta.get('date_done', ''),
                        'task_name': meta.get('task_name', 'N/A')
                    })
            except Exception as e:
                continue
        
        return tasks
    except Exception as e:
        st.warning(f"无法获取任务历史: {e}")
        return []


def format_timestamp(timestamp):
    """格式化时间戳"""
    if not timestamp:
        return "N/A"
    try:
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%H:%M:%S")
    except:
        return str(timestamp)


def get_queue_tasks(r: redis.Redis) -> dict:
    """获取所有队列中的任务详情
    
    返回格式: {
        '文本生成队列': [
            {'task_id': 'xxx', 'task_name': 'text.run_workflow_task', 'queue_key': 'text_queue', 'index': 0, ...},
            ...
        ],
        ...
    }
    """
    
    queues = {
        'text_queue': '文本生成队列',
        'media_queue': '多媒体队列',
        'rag_queue': 'RAG索引队列'
    }
    
    result = {name: [] for name in queues.values()}
    
    # 查找所有可能的队列键
    queue_keys_map = {}  # {queue_name: [actual_redis_keys]}
    
    for queue_key, queue_name in queues.items():
        # 尝试多种键名格式
        key_patterns = [
            queue_key,
            queue_key.replace('_queue', ''),
            f'tasks.{queue_key}',
            f'tasks.{queue_key.replace("_queue", "")}',
            f'tasks.{queue_key.replace("_queue", "")}.default',
        ]
        
        found_keys = []
        for key_pattern in key_patterns:
            try:
                if r.type(key_pattern) == 'list' and r.llen(key_pattern) > 0:
                    found_keys.append(key_pattern)
            except:
                continue
        
        if found_keys:
            queue_keys_map[queue_name] = found_keys
    
    # 从每个队列中读取任务
    for queue_name, redis_keys in queue_keys_map.items():
        for redis_key in redis_keys:
            try:
                # 获取队列长度
                queue_length = r.llen(redis_key)
                
                # 读取所有任务（不删除，只查看）
                for index in range(queue_length):
                    try:
                        # 使用 LINDEX 获取指定位置的任务（不删除）
                        task_data = r.lindex(redis_key, index)
                        if not task_data:
                            continue
                        
                        # 保存原始数据用于删除
                        raw_data = task_data
                        
                        # 解析任务数据（Kombu 可能使用 pickle 或 JSON）
                        task_id = f'Task-{index}'
                        task_name = 'Unknown'
                        novel_name = "N/A"
                        chapter_num = "N/A"
                        
                        try:
                            # 尝试 JSON 解析
                            task_info = json.loads(task_data)
                            
                            # 提取任务信息
                            task_id = task_info.get('headers', {}).get('id') or task_info.get('id', '') or f'Task-{index}'
                            task_name = task_info.get('headers', {}).get('task') or task_info.get('task', 'Unknown')
                            
                            # 解析 body（可能是 base64 编码的 pickle）
                            body = task_info.get('body', '')
                            if body:
                                try:
                                    # 尝试 base64 解码
                                    if isinstance(body, str):
                                        body_decoded = base64.b64decode(body)
                                        args = pickle.loads(body_decoded)
                                        
                                        # 提取小说名和章节号
                                        if isinstance(args, (list, tuple)) and len(args) >= 2:
                                            novel_name = args[0] if isinstance(args[0], str) else "N/A"
                                            chapter_num = args[1] if isinstance(args[1], (int, str)) else "N/A"
                                except:
                                    # 如果解码失败，尝试直接 JSON 解析
                                    try:
                                        if isinstance(body, str):
                                            args = json.loads(body)
                                            if isinstance(args, (list, tuple)) and len(args) >= 2:
                                                novel_name = args[0] if isinstance(args[0], str) else "N/A"
                                                chapter_num = args[1] if isinstance(args[1], (int, str)) else "N/A"
                                    except:
                                        pass
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            # 如果 JSON 解析失败，尝试 pickle
                            try:
                                task_info = pickle.loads(task_data)
                                if isinstance(task_info, dict):
                                    task_id = task_info.get('id', f'Task-{index}')
                                    task_name = task_info.get('task', 'Unknown')
                            except:
                                pass
                        
                        result[queue_name].append({
                            'task_id': task_id,
                            'task_name': task_name,
                            'queue_key': redis_key,
                            'index': index,
                            'novel_name': novel_name,
                            'chapter_num': chapter_num,
                            'raw_data': raw_data  # 保存完整原始数据用于删除
                        })
                    except Exception as e:
                        continue
            except Exception as e:
                continue
    
    return result


def remove_task_from_queue(r: redis.Redis, queue_key: str, task_data: bytes) -> bool:
    """从队列中删除指定任务
    
    参数:
        r: Redis 客户端
        queue_key: 队列键名
        task_data: 任务的原始数据（用于匹配，可能是 bytes 或 str）
    
    返回:
        bool: 是否成功删除
    """
    try:
        # 确保 task_data 是 bytes 类型（Redis 需要）
        if isinstance(task_data, str):
            task_data = task_data.encode('utf-8')
        
        # 使用 LREM 删除匹配的元素
        # LREM key count value
        # count = 0: 删除所有匹配的元素
        removed = r.lrem(queue_key, 0, task_data)
        return removed > 0
    except Exception as e:
        # 如果失败，尝试其他方法：通过索引删除
        try:
            # 获取队列长度
            queue_length = r.llen(queue_key)
            
            # 遍历找到匹配的任务并删除
            for i in range(queue_length):
                item = r.lindex(queue_key, i)
                if item == task_data:
                    # 使用 LSET + LTRIM 或直接使用 LREM
                    # 更简单的方法：使用 LREM 删除第一个匹配的
                    r.lrem(queue_key, 1, task_data)
                    return True
        except:
            pass
        
        return False


def main():
    st.title("🚀 任务监控助手")
    st.caption("实时监控 Celery 任务队列和 Worker 状态")
    
    # 初始化 Redis
    r = init_redis()
    if not r:
        st.stop()
    
    # 控制面板
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        auto_refresh = st.checkbox("🔄 自动刷新", value=True)
    with col2:
        refresh_interval = st.selectbox("刷新间隔", [1, 2, 5, 10], index=0, format_func=lambda x: f"{x}秒")
    with col3:
        if st.button("🔃 手动刷新"):
            st.rerun()
    
    st.divider()
    
    # A. 队列积压监控
    st.markdown("### 📊 队列积压监控")
    
    # 提示信息
    if all(d == 0 for d in get_queue_depth(r).values()):
        st.info("💡 **提示**: 队列为空是正常的。如果刚提交了任务，可能已被 Worker 立即取走，请查看下方的 'Worker 活动监控' 查看正在执行的任务。")
    
    depths = get_queue_depth(r)
    
    # 调试：如果所有队列都是 0，显示 Redis 键列表帮助诊断
    if all(d == 0 for d in depths.values()):
        with st.expander("🔍 调试：查看 Redis 中的队列键（所有队列为空时显示）", expanded=False):
            st.caption("💡 **说明**: 如果队列为空，这是正常情况。任务提交后可能立即被 Worker 取走，此时队列长度为 0，但可以在 'Worker 活动监控' 中看到正在执行的任务。")
            try:
                all_keys = r.keys('*')
                
                # 查找所有 List 类型的键（队列通常是 List 类型）
                list_keys = []
                for key in all_keys[:500]:  # 检查前500个键
                    try:
                        if r.type(key) == 'list':
                            length = r.llen(key)
                            list_keys.append((key, length))
                    except:
                        continue
                
                if list_keys:
                    # 按长度排序，显示非空的
                    list_keys_sorted = sorted([(k, l) for k, l in list_keys if l > 0], key=lambda x: x[1], reverse=True)
                    if list_keys_sorted:
                        st.markdown("**所有非空的 List 类型键（可能是队列）:**")
                        st.code('\n'.join([f"{key} (长度: {length})" for key, length in list_keys_sorted[:30]]))
                        st.caption(f"显示前 30 个（共 {len(list_keys_sorted)} 个非空）")
                    else:
                        st.info("所有 List 类型键都为空（队列中确实没有任务）")
                
                # 查找所有包含队列关键词的键
                queue_keywords = ['text', 'media', 'rag', 'queue', 'tasks', 'celery', 'kombu']
                related_keys = [k for k in all_keys if any(kw in k.lower() for kw in queue_keywords)]
                if related_keys:
                    st.markdown("**所有队列相关的键:**")
                    st.code('\n'.join(sorted(related_keys)[:50]))
                    st.caption(f"显示前 50 个（共 {len(related_keys)} 个）")
                
                # 显示 Worker 状态
                try:
                    i = celery_app.control.inspect()
                    active = i.active() or {}
                    reserved = i.reserved() or {}
                    if active or reserved:
                        st.markdown("**Worker 状态:**")
                        if active:
                            for worker, tasks in active.items():
                                st.caption(f"🔧 {worker}: {len(tasks)} 个活跃任务")
                        if reserved:
                            total_reserved = sum(len(tasks) for tasks in reserved.values())
                            if total_reserved > 0:
                                st.caption(f"⏳ 总计 {total_reserved} 个已保留但未开始的任务")
                except:
                    pass
                
            except Exception as e:
                st.error(f"无法列出键: {e}")
    
    cols = st.columns(len(depths))
    for idx, (queue_name, depth) in enumerate(depths.items()):
        with cols[idx]:
            if depth == -1:
                st.metric(
                    label=queue_name,
                    value="错误",
                    delta=None,
                    delta_color="off"
                )
            elif depth > 0:
                st.metric(
                    label=queue_name,
                    value=depth,
                    delta=f"{depth} 个任务积压",
                    delta_color="inverse"
                )
            else:
                st.metric(
                    label=queue_name,
                    value=depth,
                    delta="空闲",
                    delta_color="normal"
                )
    
    st.divider()
    
    # A2. 队列任务列表（可删除）
    st.markdown("### 📋 队列任务列表")
    st.caption("查看所有队列中的任务，可以手动删除不需要的任务")
    
    queue_tasks = get_queue_tasks(r)
    
    has_tasks = any(len(tasks) > 0 for tasks in queue_tasks.values())
    
    if not has_tasks:
        st.info("📭 所有队列中都没有待处理的任务")
    else:
        for queue_name, tasks in queue_tasks.items():
            if len(tasks) > 0:
                with st.expander(f"**{queue_name}** ({len(tasks)} 个任务)", expanded=True):
                    for idx, task in enumerate(tasks):
                        col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                        
                        with col1:
                            st.markdown(f"**{task['task_name']}**")
                            st.caption(f"Task ID: `{task['task_id'][:16]}...`")
                        
                        with col2:
                            if task['novel_name'] != 'N/A':
                                st.caption(f"📚 {task['novel_name']}")
                            else:
                                st.caption("📚 N/A")
                        
                        with col3:
                            if task['chapter_num'] != 'N/A':
                                st.caption(f"📄 第 {task['chapter_num']} 章")
                            else:
                                st.caption("📄 N/A")
                        
                        with col4:
                            # 删除按钮
                            delete_key = f"delete_{queue_name}_{task['task_id']}_{idx}"
                            if st.button("🗑️ 删除", key=delete_key, help="删除此任务", use_container_width=True, type="secondary"):
                                try:
                                    # 尝试删除任务
                                    success = remove_task_from_queue(r, task['queue_key'], task['raw_data'])
                                    if success:
                                        st.success(f"✅ 任务已删除: {task['task_id'][:16]}...")
                                        time.sleep(0.5)  # 短暂延迟以便用户看到成功消息
                                        st.rerun()
                                    else:
                                        st.warning(f"⚠️ 删除失败: 任务可能已被 Worker 取走或不存在")
                                        time.sleep(1)
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"❌ 删除失败: {e}")
                                    time.sleep(1)
                                    st.rerun()
                        
                        if idx < len(tasks) - 1:
                            st.divider()
    
    st.divider()
    
    # B. Worker 活动监控
    st.markdown("### 🔧 Worker 活动监控")
    active_tasks = get_active_tasks()
    
    if not active_tasks:
        st.info("📭 当前无活跃任务")
    else:
        st.success(f"🔥 当前有 {len(active_tasks)} 个任务正在执行")
        
        for task in active_tasks:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**🔹 {task['task_name']}**")
                    st.caption(f"Worker: `{task['worker']}`")
                    st.caption(f"Task ID: `{task['task_id'][:16]}...`")
                
                with col2:
                    elapsed = int(time.time() - task['time_start'])
                    st.metric("运行时长", f"{elapsed}s")
    
    st.divider()
    
    # C. 任务历史
    st.markdown("### 📜 任务历史记录")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("最近 20 条任务记录")
    with col2:
        history_limit = st.selectbox("显示数量", [10, 20, 50], index=1, label_visibility="collapsed")
    
    task_history = get_task_history(r, limit=history_limit)
    
    if not task_history:
        st.info("📭 暂无任务历史")
    else:
        # 状态统计
        status_counts = {}
        for task in task_history:
            status = task['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        stat_cols = st.columns(len(status_counts) if status_counts else 1)
        for idx, (status, count) in enumerate(status_counts.items()):
            with stat_cols[idx]:
                emoji = "✅" if status == "SUCCESS" else ("❌" if status == "FAILURE" else "⏳")
                st.metric(f"{emoji} {status}", count)
        
        st.divider()
        
        # 任务列表
        for task in task_history:
            status = task['status']
            
            # 状态图标和颜色
            if status == "SUCCESS":
                status_icon = "✅"
                border_color = "green"
            elif status == "FAILURE":
                status_icon = "❌"
                border_color = "red"
            elif status == "PENDING":
                status_icon = "⏳"
                border_color = "orange"
            else:
                status_icon = "❓"
                border_color = "gray"
            
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.markdown(f"**{status_icon} {task.get('task_name', 'Unknown Task')}**")
                    st.caption(f"Task ID: `{task['task_id'][:16]}...`")
                
                with col2:
                    st.caption(f"状态: **{status}**")
                    if task['date_done']:
                        st.caption(f"完成: {format_timestamp(task['date_done'])}")
                
                with col3:
                    # 查看详情按钮
                    if st.button("📋 详情", key=f"detail_{task['task_id']}", use_container_width=True):
                        with st.expander("任务详情", expanded=True):
                            st.json({
                                'task_id': task['task_id'],
                                'status': task['status'],
                                'result': task['result'],
                                'date_done': task['date_done']
                            })
    
    # 自动刷新逻辑
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == "__main__":
    main()
