"""
Agent 功能测试脚本

测试各个 Agent Handler 的核心功能
"""
import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.core.state_manager import StateManager
from src.core.dispatcher import Dispatcher
from src.core.llm import LLMClient
from src.core.config import Settings
from src.utils.file_manager import ProjectManager
from src.workers.handlers.architect import ArchitectHandler
from src.workers.handlers.writer import WriterHandler
from src.workers.handlers.critic import CriticHandler
from src.workers.handlers.media import MediaHandler
from src.workers.handlers.knowledge import KnowledgeHandler
import uuid
import json

def test_architect():
    """测试 ArchitectHandler - 生成大纲"""
    print("\n" + "="*60)
    print("测试 ArchitectHandler - 生成大纲")
    print("="*60)
    
    state_manager = StateManager()
    dispatcher = Dispatcher(state_manager)
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    llm_client = LLMClient(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.7,
        max_tokens=4096
    )
    
    file_manager = ProjectManager(Path(config.paths.workspace))
    
    handler = ArchitectHandler(state_manager, dispatcher, llm_client, file_manager)
    workflow_id = str(uuid.uuid4())
    
    state_manager.init_workflow(workflow_id, {
        "novel_name": "测试小说",
        "chapter_num": 1,
        "status": "started"
    })
    
    try:
        result = handler.execute(workflow_id, {
            "novel_name": "测试小说",
            "chapter_num": 1
        })
        print(f"✅ 大纲生成成功")
        print(f"大纲预览: {result.get('outline', '')[:200]}...")
        return True
    except Exception as e:
        print(f"❌ 大纲生成失败: {e}")
        return False

def test_writer():
    """测试 WriterHandler - 撰写内容"""
    print("\n" + "="*60)
    print("测试 WriterHandler - 撰写内容")
    print("="*60)
    
    state_manager = StateManager()
    dispatcher = Dispatcher(state_manager)
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    llm_client = LLMClient(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.9,
        max_tokens=8192
    )
    
    file_manager = ProjectManager(Path(config.paths.workspace))
    
    handler = WriterHandler(state_manager, dispatcher, llm_client, file_manager)
    workflow_id = str(uuid.uuid4())
    
    mock_outline = json.dumps({
        "scenes": [
            {
                "id": 1,
                "summary": "主角在森林中遇到神秘老人，获得重要线索",
                "expected_words": 500,
                "key_characters": ["主角", "神秘老人"]
            }
        ]
    }, ensure_ascii=False)
    
    state_manager.init_workflow(workflow_id, {
        "novel_name": "测试小说",
        "chapter_num": 1,
        "outline": mock_outline,
        "status": "started"
    })
    
    try:
        result = handler.execute(workflow_id, {})
        print(f"✅ 内容撰写成功")
        print(f"内容预览: {result.get('content', '')[:200]}...")
        return True
    except Exception as e:
        print(f"❌ 内容撰写失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_critic():
    """测试 CriticHandler - 审稿评分"""
    print("\n" + "="*60)
    print("测试 CriticHandler - 审稿评分")
    print("="*60)
    
    state_manager = StateManager()
    dispatcher = Dispatcher(state_manager)
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    llm_client = LLMClient(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.3,
        max_tokens=2048
    )
    
    file_manager = ProjectManager(Path(config.paths.workspace))
    
    handler = CriticHandler(state_manager, dispatcher, llm_client, file_manager)
    workflow_id = str(uuid.uuid4())
    
    mock_outline = json.dumps({
        "scenes": [{"id": 1, "summary": "测试场景", "expected_words": 500}]
    }, ensure_ascii=False)
    
    mock_content = """
# 测试章节

主角走在森林中，突然遇到了一位神秘老人。老人告诉他一个重要的秘密。

"你必须找到那把剑，"老人说，"只有它才能拯救世界。"

主角点了点头，继续前行。
"""
    
    chapter_path = file_manager.init_chapter("测试小说", 1)
    content_path = chapter_path / "content.md"
    file_manager.save_content(content_path, mock_content)
    
    state_manager.init_workflow(workflow_id, {
        "novel_name": "测试小说",
        "chapter_num": 1,
        "outline": mock_outline,
        "status": "started"
    })
    
    try:
        result = handler.execute(workflow_id, {})
        print(f"✅ 审稿完成")
        print(f"评分: {result.get('score', 0)}/100")
        print(f"是否通过: {result.get('passed', False)}")
        print(f"建议: {result.get('advice', '')[:100]}...")
        return True
    except Exception as e:
        print(f"❌ 审稿失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_media():
    """测试 MediaHandler - 生成图片"""
    print("\n" + "="*60)
    print("测试 MediaHandler - 生成图片")
    print("="*60)
    
    state_manager = StateManager()
    dispatcher = Dispatcher(state_manager)
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    llm_client = LLMClient(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.7,
        max_tokens=512
    )
    
    file_manager = ProjectManager(Path(config.paths.workspace))
    
    handler = MediaHandler(state_manager, dispatcher, llm_client, file_manager)
    workflow_id = str(uuid.uuid4())
    
    state_manager.init_workflow(workflow_id, {
        "novel_name": "测试小说",
        "chapter_num": 1,
        "status": "started"
    })
    
    try:
        result = handler.execute(workflow_id, {
            "scene_description": "一个神秘的森林，月光透过树叶洒下，一位老人站在树影中"
        })
        print(f"✅ 图片生成完成")
        print(f"Prompt: {result.get('prompt', '')[:150]}...")
        print(f"图片路径: {result.get('image_url', '')}")
        return True
    except Exception as e:
        print(f"❌ 图片生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_knowledge():
    """测试 KnowledgeHandler - 更新知识库"""
    print("\n" + "="*60)
    print("测试 KnowledgeHandler - 更新知识库")
    print("="*60)
    
    state_manager = StateManager()
    dispatcher = Dispatcher(state_manager)
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    llm_client = LLMClient(
        provider="openrouter",
        model="deepseek/deepseek-chat",
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        temperature=0.3,
        max_tokens=1024
    )
    
    file_manager = ProjectManager(Path(config.paths.workspace))
    
    handler = KnowledgeHandler(state_manager, dispatcher, llm_client, file_manager)
    workflow_id = str(uuid.uuid4())
    
    mock_content = """
# 第一章

主角林风在森林中遇到了一位神秘老人。老人名叫"云游子"，是一位隐世高人。

云游子告诉林风："你体内有特殊的血脉，注定要成为拯救世界的英雄。"

林风获得了【断钢剑】，这是一把传说中的神兵利器。
"""
    
    state_manager.init_workflow(workflow_id, {
        "novel_name": "测试小说",
        "chapter_num": 1,
        "draft_content": mock_content,
        "status": "started"
    })
    
    try:
        result = handler.execute(workflow_id, {
            "chapter_content": mock_content
        })
        print(f"✅ 知识库更新完成")
        print(f"提取实体数: {result.get('entities_extracted', 0)}")
        print(f"章节索引: {result.get('chapter_indexed', 0)}")
        return True
    except Exception as e:
        print(f"❌ 知识库更新失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("开始测试所有 Agent Handler")
    print("="*60)
    
    results = {}
    
    results["Architect"] = test_architect()
    results["Writer"] = test_writer()
    results["Critic"] = test_critic()
    results["Media"] = test_media()
    results["Knowledge"] = test_knowledge()
    
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    for agent, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{agent}: {status}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\n总计: {passed}/{total} 通过")

if __name__ == "__main__":
    main()
