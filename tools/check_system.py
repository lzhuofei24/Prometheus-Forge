#!/usr/bin/env python
"""
系统状态检查脚本
检查 Redis、Celery Workers 和依赖是否正常
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_redis():
    """检查 Redis 连接"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=2)
        r.ping()
        print("✅ Redis 连接正常")
        return True
    except ImportError:
        print("❌ redis 库未安装，请运行: pip install redis")
        return False
    except Exception as e:
        print(f"❌ Redis 连接失败: {e}")
        print("   请确保 Docker 已启动并运行: docker-compose up -d")
        return False

def check_celery():
    """检查 Celery 配置"""
    try:
        from src.core.celery_config import celery_app
        print("✅ Celery 配置加载成功")
        return True
    except Exception as e:
        print(f"❌ Celery 配置加载失败: {e}")
        return False

def check_dependencies():
    """检查关键依赖"""
    deps = {
        'celery': 'celery',
        'redis': 'redis',
        'chromadb': 'chromadb',
        'sentence_transformers': 'sentence-transformers',
        'edge_tts': 'edge-tts',
        'PIL': 'pillow',
        'requests': 'requests'
    }
    
    missing = []
    for module, package in deps.items():
        try:
            if module == 'PIL':
                __import__('PIL')
            else:
                __import__(module)
            print(f"✅ {package} 已安装")
        except ImportError:
            print(f"❌ {package} 未安装")
            missing.append(package)
    
    return len(missing) == 0, missing

def check_workers():
    """检查 Celery Workers 状态"""
    try:
        from celery import current_app
        inspect = current_app.control.inspect()
        active = inspect.active()
        
        if active:
            print("✅ 检测到运行中的 Celery Workers:")
            for worker, tasks in active.items():
                print(f"   - {worker}: {len(tasks)} 个活跃任务")
            return True
        else:
            print("⚠️  未检测到运行中的 Celery Workers")
            print("   请启动 Workers:")
            print("   celery -A src.workers.tasks worker -Q text_queue -c 1 --loglevel=info")
            print("   celery -A src.workers.tasks worker -Q rag_queue,media_queue -c 2 --loglevel=info")
            return False
    except Exception as e:
        print(f"⚠️  无法检查 Workers 状态: {e}")
        return False

def main():
    print("=" * 50)
    print("Novel-Agent 系统状态检查")
    print("=" * 50)
    print()
    
    all_ok = True
    
    print("[1/4] 检查依赖...")
    deps_ok, missing = check_dependencies()
    if not deps_ok:
        print(f"\n   缺少依赖: {', '.join(missing)}")
        print(f"   请运行: pip install {' '.join(missing)}")
        all_ok = False
    print()
    
    print("[2/4] 检查 Celery 配置...")
    celery_ok = check_celery()
    if not celery_ok:
        all_ok = False
    print()
    
    print("[3/4] 检查 Redis 连接...")
    redis_ok = check_redis()
    if not redis_ok:
        all_ok = False
    print()
    
    print("[4/4] 检查 Celery Workers...")
    workers_ok = check_workers()
    if not workers_ok:
        all_ok = False
    print()
    
    print("=" * 50)
    if all_ok:
        print("✅ 系统状态正常，可以启动 Streamlit")
        print("   运行: streamlit run src/gui/app.py")
    else:
        print("❌ 系统检查未通过，请根据上述提示修复问题")
    print("=" * 50)

if __name__ == "__main__":
    main()
