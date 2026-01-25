import sys
from pathlib import Path
import requests
import time
import json
from typing import Dict, Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

API_BASE = "http://localhost:8000"

def test_api_health():
    print("\n=== 测试 API 健康检查 ===")
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=5)
        print(f"状态码: {resp.status_code}")
        print(f"响应: {resp.json()}")
        assert resp.status_code == 200
        print("✅ API 健康检查通过")
        return True
    except Exception as e:
        print(f"❌ API 健康检查失败: {e}")
        return False

def test_database():
    print("\n=== 测试数据库连接 ===")
    try:
        from sqlalchemy import create_engine, text
        from pathlib import Path
        project_root = Path(__file__).parent.parent
        db_path = project_root / "data" / "novel_content_db" / "prometheus_forge.db"
        if not db_path.exists():
            print("⚠️  数据库文件不存在，将创建")
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.fetchone()[0] == 1
        print("✅ 数据库连接正常")
        return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_redis():
    print("\n=== 测试 Redis 连接 ===")
    try:
        import redis
        from src.core.app_settings import get_settings
        settings = get_settings()
        r = redis.Redis(host=settings.redis_host, port=settings.redis_port, db=settings.redis_db)
        r.ping()
        print("✅ Redis 连接正常")
        return True
    except Exception as e:
        print(f"❌ Redis 连接失败: {e}")
        return False

def test_workflow_start():
    print("\n=== 测试工作流启动 ===")
    try:
        resp = requests.post(
            f"{API_BASE}/workflow/start",
            json={"novel_name": "测试小说", "chapter_num": 1},
            timeout=5
        )
        assert resp.status_code == 200
        data = resp.json()
        workflow_id = data["workflow_id"]
        print(f"✅ 工作流启动成功: {workflow_id}")
        return workflow_id
    except Exception as e:
        print(f"❌ 工作流启动失败: {e}")
        return None

def test_architect_agent(workflow_id: str):
    print("\n=== 测试 Architect Agent ===")
    try:
        from src.workers.tasks_new import task_generate_outline
        from src.core.state_manager import StateManager
        from src.core.dispatcher import Dispatcher
        from src.core.llm import LLMClient
        from src.utils.file_manager import ProjectManager
        from src.workers.handlers.architect import ArchitectHandler
        from src.core.config import Settings
        from pathlib import Path
        import os
        
        state_manager = StateManager()
        dispatcher = Dispatcher(state_manager)
        
        project_root = Path(__file__).parent.parent
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        file_manager = ProjectManager(Path(config.paths.workspace))
        
        api_key = os.getenv("OPENROUTER_API_KEY")
        llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            api_key=api_key,
            base_url=config.model.base_url,
            temperature=0.7,
            max_tokens=500
        )
        
        handler = ArchitectHandler(state_manager, dispatcher, llm_client, file_manager)
        
        state_manager.init_workflow(workflow_id, {
            "novel_name": "测试小说",
            "chapter_num": 1,
            "status": "started"
        })
        
        result = handler.execute(workflow_id, {
            "novel_name": "测试小说",
            "chapter_num": 1
        })
        
        print(f"✅ Architect Agent 执行成功")
        print(f"   大纲长度: {len(result.get('outline', ''))}")
        return True
    except Exception as e:
        print(f"❌ Architect Agent 失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_writer_agent(workflow_id: str):
    print("\n=== 测试 Writer Agent ===")
    try:
        from src.workers.tasks_new import task_write_content
        from src.core.state_manager import StateManager
        from src.core.dispatcher import Dispatcher
        from src.core.llm import LLMClient
        from src.utils.file_manager import ProjectManager
        from src.workers.handlers.writer import WriterHandler
        from src.core.config import Settings
        from pathlib import Path
        import os
        
        state_manager = StateManager()
        dispatcher = Dispatcher(state_manager)
        
        project_root = Path(__file__).parent.parent
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        file_manager = ProjectManager(Path(config.paths.workspace))
        
        api_key = os.getenv("OPENROUTER_API_KEY")
        llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            api_key=api_key,
            base_url=config.model.base_url,
            temperature=0.7,
            max_tokens=300
        )
        
        handler = WriterHandler(state_manager, dispatcher, llm_client, file_manager)
        
        state = state_manager.get_state(workflow_id)
        if not state.get("outline"):
            state["outline"] = "测试大纲：主角在森林中遇到神秘生物。"
        
        result = handler.execute(workflow_id, {})
        
        print(f"✅ Writer Agent 执行成功")
        print(f"   内容长度: {len(result.get('content', ''))}")
        return True
    except Exception as e:
        print(f"❌ Writer Agent 失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_critic_agent(workflow_id: str):
    print("\n=== 测试 Critic Agent ===")
    try:
        from src.core.state_manager import StateManager
        from src.core.dispatcher import Dispatcher
        from src.core.llm import LLMClient
        from src.utils.file_manager import ProjectManager
        from src.workers.handlers.critic import CriticHandler
        from src.core.config import Settings
        from pathlib import Path
        import os
        
        state_manager = StateManager()
        dispatcher = Dispatcher(state_manager)
        
        project_root = Path(__file__).parent.parent
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        file_manager = ProjectManager(Path(config.paths.workspace))
        
        api_key = os.getenv("OPENROUTER_API_KEY")
        llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            api_key=api_key,
            base_url=config.model.base_url,
            temperature=0.3,
            max_tokens=200
        )
        
        handler = CriticHandler(state_manager, dispatcher, llm_client, file_manager)
        
        state = state_manager.get_state(workflow_id)
        if not state.get("draft_content"):
            state["draft_content"] = "测试内容：主角在森林中漫步，突然听到奇怪的声音。"
        
        result = handler.execute(workflow_id, {})
        
        print(f"✅ Critic Agent 执行成功")
        print(f"   评分: {result.get('score', 0)}")
        print(f"   通过: {result.get('passed', False)}")
        return True
    except Exception as e:
        print(f"❌ Critic Agent 失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_censor_agent(workflow_id: str):
    print("\n=== 测试 Censor Agent ===")
    try:
        from src.core.state_manager import StateManager
        from src.core.dispatcher import Dispatcher
        from src.core.llm import LLMClient
        from src.workers.handlers.censor import CensorHandler
        from src.core.config import Settings
        from pathlib import Path
        import os
        
        state_manager = StateManager()
        dispatcher = Dispatcher(state_manager)
        
        project_root = Path(__file__).parent.parent
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        
        api_key = os.getenv("OPENROUTER_API_KEY")
        llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            api_key=api_key,
            base_url=config.model.base_url,
            temperature=0.1,
            max_tokens=200
        )
        
        handler = CensorHandler(state_manager, dispatcher, llm_client)
        
        result = handler.execute(workflow_id, {
            "content": "这是一段正常的测试内容，没有任何敏感信息。"
        })
        
        print(f"✅ Censor Agent 执行成功")
        print(f"   敏感: {result.get('is_sensitive', False)}")
        print(f"   检查方式: {result.get('checked_by', 'unknown')}")
        return True
    except Exception as e:
        print(f"❌ Censor Agent 失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_knowledge_agent(workflow_id: str):
    print("\n=== 测试 Knowledge Agent ===")
    try:
        from src.core.state_manager import StateManager
        from src.core.dispatcher import Dispatcher
        from src.core.llm import LLMClient
        from src.utils.file_manager import ProjectManager
        from src.workers.handlers.knowledge import KnowledgeHandler
        from src.core.config import Settings
        from pathlib import Path
        import os
        
        state_manager = StateManager()
        dispatcher = Dispatcher(state_manager)
        
        project_root = Path(__file__).parent.parent
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
        file_manager = ProjectManager(Path(config.paths.workspace))
        
        api_key = os.getenv("OPENROUTER_API_KEY")
        llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            api_key=api_key,
            base_url=config.model.base_url,
            temperature=0.3,
            max_tokens=300
        )
        
        handler = KnowledgeHandler(state_manager, dispatcher, llm_client, file_manager)
        
        result = handler.execute(workflow_id, {
            "chapter_content": "测试章节内容：主角在森林中遇到了一只神秘的生物，它拥有强大的魔法力量。"
        })
        
        print(f"✅ Knowledge Agent 执行成功")
        print(f"   提取实体数: {result.get('entities_extracted', 0)}")
        return True
    except Exception as e:
        print(f"❌ Knowledge Agent 失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("Prometheus Forge 系统测试")
    print("=" * 60)
    
    results = {}
    
    results["api"] = test_api_health()
    results["database"] = test_database()
    results["redis"] = test_redis()
    
    if not all([results["api"], results["database"], results["redis"]]):
        print("\n❌ 基础服务检查失败，请先启动服务")
        return
    
    workflow_id = test_workflow_start()
    if not workflow_id:
        print("\n❌ 无法启动工作流")
        return
    
    results["architect"] = test_architect_agent(workflow_id)
    results["writer"] = test_writer_agent(workflow_id)
    results["critic"] = test_critic_agent(workflow_id)
    results["censor"] = test_censor_agent(workflow_id)
    results["knowledge"] = test_knowledge_agent(workflow_id)
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name:15} {status}")
    
    all_passed = all(results.values())
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查日志")
    print("=" * 60)

if __name__ == "__main__":
    main()
