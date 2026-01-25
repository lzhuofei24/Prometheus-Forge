from pathlib import Path
import os
import json
import logging
import sys
import requests
import asyncio
import re
import time
import yaml
from typing import Optional, Dict, Any, List
from celery import group, chord
from src.core.celery_config import celery_app
from src.core.llm import LLMClient
from src.core.prompt_manager import PromptRouter
from src.core.prompt_loader import get_fiction_system_prompt, resolve_prompt, format_prompt_template
from src.core.config import Settings
from src.core.db_service import DatabaseService
from src.utils.file_manager import ProjectManager
from src.utils.json_utils import parse_json_from_response

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    celery_app.start()

router = None
llm_client = None
file_manager = None
config = None

def _init_components():
    """延迟初始化组件，避免模块导入时失败"""
    global router, llm_client, file_manager, config
    
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent.parent
    load_dotenv(project_root / ".env")
    
    if router is None:
        router = PromptRouter()
    
    if config is None:
        config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    
    if file_manager is None:
        file_manager = ProjectManager(Path(config.paths.workspace))
    
    if llm_client is None:
        api_key = None
        if hasattr(config.model, 'api_key_env') and config.model.api_key_env:
            api_key = os.getenv(config.model.api_key_env)
        elif config.model.provider == "siliconflow":
            api_key = os.getenv("SILICONFLOW_API_KEY")
        elif config.model.provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
        else:
            api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            api_key_env_name = getattr(config.model, 'api_key_env', None) or "SILICONFLOW_API_KEY"
            raise ValueError(
                f"API Key 未设置！请在 .env 文件中设置：\n"
                f"  {api_key_env_name}=your_key"
            )
        
        base_url = getattr(config.model, 'base_url', None)
        
        site_url = None
        app_name = None
        if hasattr(config, 'llm') and config.llm:
            site_url = config.llm.get('site_url')
            app_name = config.llm.get('app_name')
        
        llm_client = LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            api_key=api_key,
            base_url=base_url,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens,
            api_key_env=getattr(config.model, 'api_key_env', None),
            site_url=site_url,
            app_name=app_name
        )
    
    return router, llm_client, file_manager, config


def _build_context(novel_name: str, chapter_num: int) -> str:
    global file_manager
    if file_manager is None:
        _, _, file_manager, _ = _init_components()
    
    global_dir = file_manager.get_global_settings_path(novel_name)
    bios_path = global_dir / "bios.json"
    world_path = global_dir / "world.md"
    story_summary_path = global_dir / "story_summary.md"
    
    bios = file_manager.load_content(bios_path) if bios_path.exists() else []
    world = file_manager.load_content(world_path) if world_path.exists() else ""
    story_summary = file_manager.load_content(story_summary_path) if story_summary_path.exists() else ""
    
    character_bios_text = _format_bios(bios)
    world_setting_text = world if world else ""
    
    existing_chapters = file_manager.list_chapters(novel_name)
    previous_chapters = sorted([ch for ch in existing_chapters if ch < chapter_num], reverse=True)[:5]
    recent_chapters_content = []
    
    for ch_num in reversed(previous_chapters):
        try:
            ch_path = file_manager.get_chapter_path(novel_name, ch_num)
            content_path = ch_path / "content.md"
            if content_path.exists():
                content = file_manager.load_content(content_path)
                recent_chapters_content.append(f"## 第{ch_num}章完整正文\n\n{content}\n\n")
        except Exception as e:
            logger.warning(f"加载第{ch_num}章失败: {e}")
            continue
    
    recent_content_text = "\n\n---\n\n".join(recent_chapters_content)
    
    reference_context = f"# 核心指令\n{get_fiction_system_prompt()}\n\n"
    reference_context += f"# 世界观与人物\n## 人物设定：\n{character_bios_text}\n\n## 世界观设定：\n{world_setting_text}\n\n"
    
    if story_summary:
        reference_context += f"# 全书剧情梗概 (The Story So Far)\n{story_summary}\n\n"
    
    if recent_content_text:
        reference_context += f"# 最近剧情 (Context Window)\n{recent_content_text}\n\n"
    
    return reference_context


def _format_bios(bios: List[Dict[str, Any]]) -> str:
    if not bios:
        return "（暂无人物设定）"
    
    formatted = []
    for bio in bios:
        if isinstance(bio, dict):
            name = bio.get("name", "未知")
            personality = bio.get("personality", "")
            appearance = bio.get("appearance", "")
            background = bio.get("background", "")
            
            bio_text = f"- **{name}**"
            if personality:
                bio_text += f"\n  - 性格：{personality}"
            if appearance:
                bio_text += f"\n  - 外貌：{appearance}"
            if background:
                bio_text += f"\n  - 背景：{background}"
            
            formatted.append(bio_text)
    
    return "\n".join(formatted)


@celery_app.task(name="text.run_workflow_task")
def run_workflow_task(novel_name: str, chapter_num: int, user_feedback: Optional[str] = None):
    """执行完整工作流（支持新旧架构）"""
    global router, llm_client, file_manager
    router, llm_client, file_manager, retriever = _init_components()
    
    logger.info(f"[工作流] 开始执行第 {chapter_num} 章工作流")
    
    # 读取配置判断使用哪个架构
    from pathlib import Path
    import yaml
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)
    use_new_arch = config_data.get("workflow", {}).get("use_new_architecture", False)
    
    logger.info(f"[工作流] 使用{'新' if use_new_arch else '旧'}架构")
    
    # 初始化工作流
    from src.agents.builder import WorldBuilder
    from src.agents.novelist import Novelist
    from src.agents.editor import ChiefEditor, Critic
    from src.workflow.graph import NovelWorkflow
    
    world_builder = WorldBuilder(llm_client, retriever, file_manager)
    novelist = Novelist(llm_client, file_manager)
    chief_editor = ChiefEditor(llm_client, file_manager)
    critic = Critic(llm_client, file_manager)
    
    workflow = NovelWorkflow(
        world_builder=world_builder,
        novelist=novelist,
        chief_editor=chief_editor,
        critic=critic,
        file_manager=file_manager,
        llm_client=llm_client,
        use_new_architecture=use_new_arch
    )
    
    # 准备初始状态
    initial_state = {
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
        "previous_context": None,
        "status": "init",
        "current_node": None
    }
    
    # 执行工作流
    try:
        final_state = workflow.run(initial_state)
        logger.info(f"[工作流] 第 {chapter_num} 章工作流执行完成")
        return {
            "status": "success",
            "final_state": {
                "critique_score": final_state.get("critique_score"),
                "status": final_state.get("status"),
                "current_stage": final_state.get("current_stage") if use_new_arch else None
            }
        }
    except Exception as e:
        logger.error(f"[工作流] 执行失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"status": "error", "error": str(e)}


@celery_app.task(name="text.generate_outline_task")
def generate_outline_task(novel_name: str, chapter_num: int):
    global router, llm_client, file_manager
    router, llm_client, file_manager, _ = _init_components()
    
    logger.info(f"开始生成第 {chapter_num} 章大纲")
    
    reference_context = _build_context(novel_name, chapter_num)
    
    outline_prompt = (
        f"请为小说《{novel_name}》的第{chapter_num}章生成详细大纲。\n\n"
        f"{reference_context}\n\n"
        "请生成一个详细的大纲，包括：\n"
        "1. 章节标题（格式要求：只输出标题本身，不要包含'第X章'、'《小说名》'等前缀，例如：'神秘的灵能之旅'）\n"
        "2. 主要情节点（3-5个）\n"
        "3. 涉及的主要人物\n"
        "4. 关键场景描述\n"
        "\n请以 Markdown 格式输出，标题使用 # 开头。"
    )
    
    system_prompt = (
        get_fiction_system_prompt() + "\n\n" +
        "你是一位专业的小说创作助手，擅长创作符合原著风格的小说章节。\n\n"
        "**重要格式要求**：\n"
        "- 章节标题必须使用 `# 标题名称` 格式\n"
        "- 标题只包含标题本身，不要包含'第X章'、'《小说名》'等前缀\n"
        "- 例如：`# 神秘的灵能之旅`，而不是 `# 《测试小说》第3章：神秘的灵能之旅`"
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": outline_prompt}
    ]
    
    outline = llm_client.chat(messages)
    
    chapter_path = file_manager.init_chapter(novel_name, chapter_num)
    outline_path = chapter_path / "outline.md"
    file_manager.save_content(outline_path, outline)
    try:
        novel = DatabaseService.get_or_create_novel(novel_name)
        DatabaseService.save_outline(novel.id, chapter_num, outline)
    except Exception as e:
        logger.warning("大纲写入数据库失败（已写入文件）: %s", e)
    
    logger.info(f"大纲生成完成，触发写作任务")
    write_chapter_task.delay(novel_name, chapter_num, None)
    
    return {"status": "success", "outline": outline}


@celery_app.task(name="text.write_chapter_task")
def write_chapter_task(novel_name: str, chapter_num: int, feedback: Optional[str] = None):
    global router, llm_client, file_manager
    router, llm_client, file_manager, _ = _init_components()
    
    logger.info(f"开始撰写第 {chapter_num} 章")
    
    reference_context = _build_context(novel_name, chapter_num)
    
    chapter_path = file_manager.get_chapter_path(novel_name, chapter_num)
    outline_path = chapter_path / "outline.md"
    outline = file_manager.load_content(outline_path) if outline_path.exists() else ""
    
    outline_summary = outline[:500] if outline else "章节大纲"
    dynamic_style_prompt = router.get_best_prompt(outline_summary) if router else None
    if not dynamic_style_prompt:
        dynamic_style_prompt = "请按照小说风格进行创作。"
    
    system_prompt = get_fiction_system_prompt() + "\n\n" + dynamic_style_prompt
    
    feedback_section = (
        f"\n\n【重要】请根据以下审稿意见调整场景规划：\n{feedback}\n" if feedback else ""
    )
    arch_raw = resolve_prompt("architect")
    arch_data = yaml.safe_load(arch_raw)
    arch_system = arch_data.get("system", "")
    arch_user_tpl = arch_data.get("user", "")
    architect_prompt = format_prompt_template(
        arch_user_tpl,
        reference_context=reference_context,
        chapter_num=chapter_num,
        feedback_section=feedback_section,
    )
    messages = [
        {"role": "system", "content": system_prompt + "\n\n" + arch_system},
        {"role": "user", "content": architect_prompt}
    ]
    
    response = llm_client.chat(messages, temperature=0.7, max_tokens=4096)
    
    try:
        outline_json = parse_json_from_response(response)
        if not outline_json or "scenes" not in outline_json:
            raise ValueError("大纲生成失败，模型未返回有效的 JSON Scenes")
    except Exception as e:
        logger.error(f"解析场景大纲失败: {e}")
        raise ValueError(f"场景大纲解析失败: {e}")
    
    scenes = outline_json["scenes"]
    
    chapter_path = file_manager.init_chapter(novel_name, chapter_num)
    content_path = chapter_path / "content.md"
    
    full_content = []
    previous_text = "（章节开始）"
    
    for i, scene in enumerate(scenes):
        logger.info(f"正在撰写场景 {i+1}/{len(scenes)}")
        
        feedback_section = (
            f"\n\n【重要】请根据以下审稿意见调整写作：\n{feedback}\n"
            if (feedback and i == 0) else ""
        )
        wb_raw = resolve_prompt("writer_builder")
        wb_data = yaml.safe_load(wb_raw)
        wb_user_tpl = wb_data.get("user", "")
        builder_prompt = wb_user_tpl.format(
            reference_context=reference_context,
            chapter_num=chapter_num,
            scene_id=scene["id"],
            scene_summary=scene["summary"],
            key_characters=", ".join(scene.get("key_characters", [])),
            expected_words=scene.get("expected_words", 2000),
            previous_text=previous_text[-2000:],
            feedback_section=feedback_section,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": builder_prompt}
        ]
        
        scene_content = None
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                scene_content = llm_client.chat(messages, max_tokens=4096, temperature=0.8)
                if scene_content and len(scene_content.strip()) > 100:
                    break
            except Exception as e:
                logger.warning(f"场景 {i+1} 请求失败（第 {attempt} 次）: {e}")
                if attempt < max_retries:
                    import time
                    time.sleep(2)
                else:
                    raise ValueError(f"场景 {i+1} 生成失败，已重试 {max_retries} 次")
        
        if not scene_content:
            raise ValueError(f"场景 {i+1} 生成失败，未获得有效内容")
        
        full_content.append(scene_content)
        previous_text = scene_content
        
        current_draft = "\n\n***\n\n".join(full_content)
        file_manager.save_content(content_path, current_draft)
    
    final_draft = "\n\n***\n\n".join(full_content)
    file_manager.save_content(content_path, final_draft)
    
    meta_path = chapter_path / "meta.json"
    if meta_path.exists():
        meta = file_manager.load_content(meta_path)
    else:
        meta = {}
    meta["word_count"] = len(final_draft)
    meta["status"] = "draft"
    from datetime import datetime
    meta["updated_at"] = datetime.now().isoformat()
    if not meta.get("created_at"):
        meta["created_at"] = meta["updated_at"]
    file_manager.save_content(meta_path, meta)
    
    logger.info(f"第 {chapter_num} 章撰写完成，触发后续任务")
    update_character_card_task.delay(novel_name, chapter_num)
    review_chapter_task.delay(novel_name, chapter_num)
    
    return {"status": "success", "word_count": len(final_draft)}


@celery_app.task(name="text.update_character_card_task")
def update_character_card_task(novel_name: str, chapter_num: int):
    global router, llm_client, file_manager
    router, llm_client, file_manager, _ = _init_components()
    
    logger.info(f"开始更新第 {chapter_num} 章人物卡")
    
    chapter_path = file_manager.get_chapter_path(novel_name, chapter_num)
    content_path = chapter_path / "content.md"
    if not content_path.exists():
        logger.warning(f"第 {chapter_num} 章正文不存在，跳过人物卡更新")
        return {"status": "skipped"}
    
    content = file_manager.load_content(content_path)
    
    global_dir = file_manager.get_global_settings_path(novel_name)
    bios_path = global_dir / "bios.json"
    bios = file_manager.load_content(bios_path) if bios_path.exists() else []
    if not isinstance(bios, list):
        bios = []
    
    extraction_prompt = f"""
请从以下章节正文中提取人物状态、物品、外貌变化等信息，并更新人物档案。

章节正文：
{content[:5000]}

请返回 JSON 格式，包含以下字段：
{{
    "character_updates": [
        {{
            "name": "人物姓名",
            "personality": "性格描述（如有变化）",
            "appearance": "外貌描述（如有变化）",
            "background": "背景信息（如有变化）",
            "new_items": ["物品1", "物品2"],
            "state_changes": "状态变化描述"
        }}
    ]
}}
"""
    
    system_prompt = get_fiction_system_prompt() + "\n\n你是一位专业的小说分析助手，擅长从文本中提取人物信息。"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": extraction_prompt}
    ]
    
    response = llm_client.chat(messages, temperature=0.3, max_tokens=2048)
    
    try:
        updates_data = parse_json_from_response(response)
        character_updates = updates_data.get("character_updates", [])
        
        for update in character_updates:
            if isinstance(update, dict) and "name" in update:
                existing = next((b for b in bios if isinstance(b, dict) and b.get("name") == update["name"]), None)
                if existing:
                    existing.update(update)
                else:
                    bios.append(update)
        
        file_manager.save_content(bios_path, bios)
        logger.info(f"人物卡更新完成，共更新 {len(character_updates)} 个人物")
    except Exception as e:
        logger.error(f"人物卡更新失败: {e}")
    
    return {"status": "success"}


@celery_app.task(name="text.review_chapter_task")
def review_chapter_task(novel_name: str, chapter_num: int, retry_count: int = 0):
    global router, llm_client, file_manager
    router, llm_client, file_manager, _ = _init_components()
    
    logger.info(f"开始审阅第 {chapter_num} 章（重试次数: {retry_count}）")
    
    chapter_path = file_manager.get_chapter_path(novel_name, chapter_num)
    content_path = chapter_path / "content.md"
    outline_path = chapter_path / "outline.md"
    
    if not content_path.exists():
        logger.warning(f"第 {chapter_num} 章正文不存在，跳过审阅")
        return {"status": "skipped"}
    
    content = file_manager.load_content(content_path)
    outline = file_manager.load_content(outline_path) if outline_path.exists() else ""
    reference_context = _build_context(novel_name, chapter_num)
    
    import yaml
    prompt_raw = resolve_prompt("critique")
    prompt_data = yaml.safe_load(prompt_raw)
    
    system_prompt = prompt_data.get("system", "")
    user_template = prompt_data.get("user", "")
    
    user_prompt = format_prompt_template(
        user_template,
        novel_name=novel_name,
        chapter_num=chapter_num,
        outline=outline,
        draft_content=content,
        reference_context=reference_context,
    )
    
    messages = [
        {"role": "system", "content": get_fiction_system_prompt() + "\n\n" + system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    response = llm_client.chat(messages)
    
    json_text = response.strip()
    if "```json" in json_text:
        start = json_text.find("```json") + 7
        end = json_text.find("```", start)
        json_text = json_text[start:end].strip()
    elif "```" in json_text:
        start = json_text.find("```") + 3
        end = json_text.find("```", start)
        json_text = json_text[start:end].strip()
    
    try:
        critique_result = json.loads(json_text)
        score = critique_result.get("score", 0)
        comments = critique_result.get("comments", "")
        
        critique_path = chapter_path / "critique.md"
        critique_content = f"# 审稿意见\n\n**评分**: {score}/100\n\n**意见**:\n{comments}\n"
        file_manager.save_content(critique_path, critique_content)
        
        logger.info(f"审阅完成，评分: {score}")
        
        if score < 75 and retry_count < 3:
            logger.info(f"评分低于75，触发重写任务（第 {retry_count + 1} 次）")
            write_chapter_task.delay(novel_name, chapter_num, comments)
        else:
            logger.info(f"评分达标或已达最大重试次数，触发多模态流程")
            generate_media_chain.delay(novel_name, chapter_num)
        
        return {"status": "success", "score": score, "comments": comments}
    except json.JSONDecodeError:
        logger.error("审稿解析失败")
        score = 50
        comments = "审稿解析失败，请检查内容质量。"
        
        if retry_count < 3:
            write_chapter_task.delay(novel_name, chapter_num, comments)
        
        return {"status": "error", "score": score, "comments": comments}


@celery_app.task(name="media.generate_image_task", queue='media_queue')
def generate_image_task(novel_name: str, chapter_num: int):
    global router, llm_client, file_manager
    router, llm_client, file_manager, _ = _init_components()
    
    # Redis 连接（用于统计）
    redis_client = None
    try:
        import redis as redis_module
        redis_client = redis_module.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=0,
            decode_responses=True,
            socket_connect_timeout=2
        )
        redis_client.ping()
    except Exception as e:
        logger.warning(f"Redis 统计连接失败: {e}")
        redis_client = None
    
    logger.info(f"开始生成第 {chapter_num} 章插画")
    
    chapter_path = file_manager.get_chapter_path(novel_name, chapter_num)
    outline_path = chapter_path / "outline.md"
    content_path = chapter_path / "content.md"
    
    if not outline_path.exists() and not content_path.exists():
        logger.warning(f"第 {chapter_num} 章内容不存在，跳过图片生成")
        return {"status": "skipped"}
    
    scene_description = ""
    if outline_path.exists():
        outline = file_manager.load_content(outline_path)
        try:
            outline_json = json.loads(outline)
            if isinstance(outline_json, dict) and "scenes" in outline_json:
                scenes = outline_json["scenes"]
                if scenes and len(scenes) > 0:
                    first_scene = scenes[0]
                    scene_description = first_scene.get("summary", str(first_scene))
        except (json.JSONDecodeError, ValueError):
            lines = outline.split('\n')
            for i, line in enumerate(lines):
                if '场景' in line or 'summary' in line.lower() or '描述' in line:
                    scene_description = line
                    if i + 1 < len(lines):
                        scene_description += " " + lines[i + 1]
                    break
            if not scene_description:
                scene_description = outline[:500]
    elif content_path.exists():
        content = file_manager.load_content(content_path)
        scene_description = content[:500]
    
    if not scene_description:
        scene_description = f"第{chapter_num}章的关键场景"
    
    illustrator_system_prompt = """You are an expert AI Art Prompter for visual novels and book illustrations.
Convert the scene description into a detailed, safe-for-work English image prompt.

CRITICAL SAFETY RULES (MUST FOLLOW):
1. **NO EXPLICIT CONTENT**: Absolutely no gore, blood, weapons in use, nudity, or explicit violence
2. **FOCUS ON ATMOSPHERE**: Use lighting, colors, mood, environment to convey tension
   - Instead of "blood", use: "red dramatic lighting", "crimson glow"
   - Instead of "weapon attacking", use: "dynamic pose", "tense confrontation"
   - Instead of "injury", use: "exhausted character", "dramatic shadows"
3. **POSITIVE FRAMING**: Focus on characters' expressions, environment details, artistic composition
4. **STYLE**: Professional illustration, cinematic lighting, highly detailed, masterpiece quality
5. **SAFE KEYWORDS**: beautiful, elegant, atmospheric, dramatic, mysterious, epic

Output ONLY the English prompt in one paragraph, no explanations or line breaks."""
    
    prompt_translation = f"""Scene to illustrate:
{scene_description}

Create a safe, family-friendly visual prompt focusing on:
- Character poses and expressions (NO weapons or violence)
- Environment and atmosphere (lighting, colors, mood)
- Artistic composition (camera angle, depth, details)
Keep it cinematic and beautiful, avoid any violent or explicit elements."""
    
    system_prompt = illustrator_system_prompt
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt_translation}
    ]
    
    try:
        image_prompt = llm_client.chat(messages, temperature=0.5, max_tokens=200)
        image_prompt = image_prompt.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"提示词生成失败，使用默认提示词: {e}")
        image_prompt = f"Cinematic lighting, hyper-realistic, 8k, a scene from a novel: {scene_description[:100]}"
    
    assets_dir = chapter_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    image_path = assets_dir / "image.png"
    
    generation_success = False
    max_retries = 3
    retry_count = 0
    
    # 使用 OpenRouter 的 Gemini 2.5 Flash Image 模型
    while retry_count < max_retries and not generation_success:
        if retry_count > 0:
            logger.info(f"重试生成图片 (第 {retry_count}/{max_retries-1} 次)...")
            # 降级策略：使用更安全的通用prompt
            if retry_count == 1:
                image_prompt = f"Professional book illustration, cinematic lighting, beautiful atmospheric scene, detailed environment, elegant composition, masterpiece quality"
            elif retry_count == 2:
                image_prompt = f"Beautiful artistic illustration, peaceful scene, elegant style, high quality, detailed artwork"
        
        retry_count += 1
        
        try:
            from openai import OpenAI
            
            openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
            if not openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY 未设置")
            
            # 获取配置的图片模型
            image_model = "google/gemini-2.5-flash-image"
            if hasattr(config, 'media') and config.media:
                image_model = config.media.get('image_model', image_model)
            
            logger.info(f"正在使用 {image_model} 生成图片...")
            
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_api_key,
                default_headers={
                    "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost"),
                    "X-Title": os.getenv("OPENROUTER_APP_NAME", "Novel-Agent")
                }
            )
            
            # 使用 Chat API 调用 Gemini 2.5 Flash Image
            response = client.chat.completions.create(
                model=image_model,
                messages=[
                    {
                        "role": "user",
                        "content": f"Create a beautiful, safe-for-work illustration: {image_prompt}"
                    }
                ],
                extra_body={
                    "image_config": {
                        "aspect_ratio": "1:1"
                    }
                }
            )
            
            message = response.choices[0].message
            logger.info(f"API 调用成功，正在提取图片数据...")
            
            # 提取图片数据（Gemini 2.5 Flash Image 返回 base64 编码）
            image_data = None
            
            # 方法1：从 images 字段提取（Gemini 专用）
            if hasattr(message, 'images') and message.images:
                logger.info(f"发现 images 字段，包含 {len(message.images)} 张图片")
                
                for idx, img_item in enumerate(message.images):
                    try:
                        if isinstance(img_item, dict) and 'image_url' in img_item:
                            url = img_item['image_url'].get('url', '')
                            if url.startswith('data:image/'):
                                import base64
                                # 提取 base64 数据
                                base64_str = url.split(',', 1)[1] if ',' in url else ''
                                if base64_str:
                                    image_data = base64.b64decode(base64_str)
                                    logger.info(f"成功解码第 {idx+1} 张图片 ({len(image_data)} 字节)")
                                    break
                    except Exception as e:
                        logger.warning(f"解码第 {idx+1} 张图片失败: {e}")
            
            # 方法2：从 content 提取 URL（备用）
            if not image_data:
                content = message.content
                if content:
                    urls = re.findall(r'(https?://[^\s\)\"\']+)', content)
                    if urls:
                        image_urls = [u for u in urls if any(ext in u.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp', 'image', 'output'])]
                        image_url = image_urls[0] if image_urls else urls[0]
                        logger.info(f"从 content 提取到 URL: {image_url}")
                        
                        # 下载图片
                        try:
                            img_response = requests.get(image_url, timeout=60)
                            if img_response.status_code == 200 and len(img_response.content) > 1000:
                                image_data = img_response.content
                                logger.info(f"图片下载成功 ({len(image_data)} 字节)")
                        except Exception as e:
                            logger.warning(f"图片下载失败: {e}")
            
            # 保存图片
            if image_data:
                with open(image_path, "wb") as f:
                    f.write(image_data)
                logger.info(f"图片已保存: {image_path}")
                generation_success = True
                
                # 统计图片生成（不影响主业务）
                try:
                    if redis_client:
                        # 从 response.usage 读取实际消耗
                        image_cost = 0.04  # 默认估算（如果无法读取usage）
                        
                        if hasattr(response, 'usage') and response.usage:
                            prompt_tokens = getattr(response.usage, 'prompt_tokens', 0)
                            completion_tokens = getattr(response.usage, 'completion_tokens', 0)
                            
                            # Gemini 2.5 Flash Image 费率（基于实际账单）
                            # Input: $0.30/M, Output: $2.50/M, Image tokens: $30/M
                            # 实际测试: 100 input + 1,303 output ≈ $0.0388
                            image_cost = (prompt_tokens * 0.30 + completion_tokens * 2.50) / 1_000_000
                            
                            logger.info(f"📊 图片Token: input={prompt_tokens}, output={completion_tokens}, cost=${image_cost:.4f}")
                        
                        pipe = redis_client.pipeline()
                        pipe.incr("stats:image_calls")
                        pipe.incrbyfloat("stats:image_cost", image_cost)
                        pipe.execute()
                        logger.info(f"📊 图片生成统计已记录: ${image_cost:.4f}")
                    else:
                        logger.warning("⚠️ 图片统计跳过: Redis 客户端未初始化")
                except Exception as e:
                    logger.warning(f"❌ 图片统计记录失败: {e}")
                
                break  # 成功则退出重试循环
            else:
                logger.warning(f"未能从 API 响应中提取到图片数据 (尝试 {retry_count}/{max_retries})")
                if retry_count < max_retries:
                    import time
                    time.sleep(2)  # 等待2秒后重试
            
        except Exception as e:
            logger.warning(f"图片生成失败 (尝试 {retry_count}/{max_retries}): {e}")
            import traceback
            logger.debug(traceback.format_exc())
            if retry_count < max_retries:
                import time
                time.sleep(2)  # 等待2秒后重试
    
    if not generation_success or not image_path.exists():
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageFilter
            
            # 创建渐变背景
            img = Image.new('RGB', (1024, 1024), color='white')
            draw = ImageDraw.Draw(img)
            
            # 渐变背景（深蓝到浅蓝）
            for i in range(1024):
                r = int(20 + (i / 1024) * 50)
                g = int(30 + (i / 1024) * 80)
                b = int(60 + (i / 1024) * 120)
                draw.rectangle([(0, i), (1024, i+1)], fill=(r, g, b))
            
            # 半透明蒙版
            overlay = Image.new('RGBA', (1024, 1024), (255, 255, 255, 30))
            img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
            
            draw = ImageDraw.Draw(img)
            
            try:
                title_font = ImageFont.truetype("arial.ttf", 60)
                desc_font = ImageFont.truetype("arial.ttf", 30)
            except:
                title_font = ImageFont.load_default()
                desc_font = ImageFont.load_default()
            
            # 标题
            title = f"📷 第 {chapter_num} 章插图"
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            draw.text(((1024 - title_width) // 2, 200), title, fill='white', font=title_font)
            
            # 提示词多行显示
            prompt_text = image_prompt[:150] + "..." if len(image_prompt) > 150 else image_prompt
            words = prompt_text.split()
            lines = []
            current_line = []
            
            for word in words:
                current_line.append(word)
                test_line = " ".join(current_line)
                bbox = draw.textbbox((0, 0), test_line, font=desc_font)
                if bbox[2] - bbox[0] > 900:
                    current_line.pop()
                    lines.append(" ".join(current_line))
                    current_line = [word]
            
            if current_line:
                lines.append(" ".join(current_line))
            
            y_offset = 400
            for line in lines[:5]:
                bbox = draw.textbbox((0, 0), line, font=desc_font)
                line_width = bbox[2] - bbox[0]
                draw.text(((1024 - line_width) // 2, y_offset), line, fill='lightgray', font=desc_font)
                y_offset += 50
            
            # 底部提示
            footer = "🎨 AI 生成插图"
            footer_bbox = draw.textbbox((0, 0), footer, font=desc_font)
            footer_width = footer_bbox[2] - footer_bbox[0]
            draw.text(((1024 - footer_width) // 2, 900), footer, fill='lightblue', font=desc_font)
            
            # 轻微模糊增加质感
            img = img.filter(ImageFilter.SMOOTH)
            
            img.save(image_path)
            logger.info(f"优化 Mock 图片已保存: {image_path}")
        except ImportError:
            logger.warning("PIL (Pillow) 未安装，无法生成 Mock 图片")
            with open(image_path.with_suffix('.txt'), 'w', encoding='utf-8') as f:
                f.write(f"Chapter {chapter_num} Scene Illustration\n\nImage Prompt:\n{image_prompt}")
            return {"status": "skipped", "message": "PIL not installed"}
        except Exception as e:
            logger.error(f"无法生成 Mock 图片: {e}")
            return {"status": "error", "message": str(e)}
    
    if content_path.exists() and image_path.exists():
        try:
            content = file_manager.load_content(content_path)
            
            image_markdown = f"![Illustration](assets/image.png)\n\n"
            
            if not content.strip().startswith("![Illustration]"):
                updated_content = image_markdown + content
                file_manager.save_content(content_path, updated_content)
                logger.info(f"已在 content.md 中插入图片链接")
        except Exception as e:
            logger.warning(f"更新 content.md 失败: {e}")
    
    return {"status": "success", "image_path": str(image_path)}


@celery_app.task(name="media.generate_audio_task", queue='media_queue')
def generate_audio_task(novel_name: str, chapter_num: int, use_full_text: bool = False):
    global router, llm_client, file_manager
    router, llm_client, file_manager, _ = _init_components()
    
    logger.info(f"开始生成第 {chapter_num} 章音频")
    
    chapter_path = file_manager.get_chapter_path(novel_name, chapter_num)
    content_path = chapter_path / "content.md"
    
    if not content_path.exists():
        logger.warning(f"第 {chapter_num} 章正文不存在，跳过音频生成")
        return {"status": "skipped"}
    
    content = file_manager.load_content(content_path)
    
    content_clean = re.sub(r'!\[.*?\]\(.*?\)', '', content)
    content_clean = re.sub(r'#+\s*', '', content_clean)
    content_clean = re.sub(r'\*\*', '', content_clean)
    
    # 最多100分钟音频：按200字/分钟计算 = 20000字
    MAX_AUDIO_CHARS = 20000
    
    if use_full_text:
        if len(content_clean) > MAX_AUDIO_CHARS:
            text_to_speak = content_clean[:MAX_AUDIO_CHARS] + "...（因长度限制，音频已截断）"
            logger.info(f"音频文本超过限制，截取前 {MAX_AUDIO_CHARS} 字")
        else:
            text_to_speak = content_clean
            logger.info(f"生成全文音频，长度: {len(content_clean)} 字")
    else:
        text_to_speak = content_clean[:500] + "...（本章节完整内容请阅读正文）"
    
    assets_dir = chapter_path / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    audio_path = assets_dir / "audio.mp3"
    
    try:
        import edge_tts
        
        async def generate_audio():
            voice = "zh-CN-XiaoxiaoNeural"
            communicate = edge_tts.Communicate(text_to_speak, voice)
            await communicate.save(str(audio_path))
        
        asyncio.run(generate_audio())
        
        logger.info(f"音频生成成功: {audio_path}")
        return {"status": "success", "audio_path": str(audio_path)}
    except ImportError:
        logger.error("edge_tts 未安装，无法生成音频")
        return {"status": "error", "message": "edge_tts not installed"}
    except Exception as e:
        logger.error(f"音频生成失败: {e}")
        return {"status": "error", "message": str(e)}


@celery_app.task(name="media.finalize_media_task", queue='media_queue')
def finalize_media_task(results, novel_name: str, chapter_num: int):
    """多模态任务完成后的回调"""
    logger.info(f"[多模态] ✅ 第 {chapter_num} 章多模态内容生成完成")
    logger.info(f"[多模态] 结果: {results}")
    return {
        "status": "success",
        "message": "多模态内容生成完成",
        "results": results
    }


@celery_app.task(name="media.post_process_chapter_task", queue='media_queue')
def post_process_chapter_task(novel_name: str, chapter_num: int):
    """启动多模态生成任务（使用chord模式）"""
    logger.info(f"[多模态] 开始并行生成第 {chapter_num} 章多模态内容")
    logger.info(f"[多模态] 🖼️ 启动插图生成...")
    logger.info(f"[多模态] 🔊 启动音频生成...")
    
    # 使用chord：所有子任务完成后调用finalize_media_task
    workflow = chord(
        group(
            generate_image_task.s(novel_name, chapter_num),
            generate_audio_task.s(novel_name, chapter_num, use_full_text=True)
        )
    )(finalize_media_task.s(novel_name, chapter_num))
    
    logger.info(f"[多模态] 任务已启动，等待子任务完成...")
    
    return {
        "status": "started",
        "message": "多模态生成任务已启动",
        "workflow_id": workflow.id
    }


@celery_app.task(name="media.generate_media_chain")
def generate_media_chain(novel_name: str, chapter_num: int):
    logger.info(f"开始生成第 {chapter_num} 章多模态内容")
    return post_process_chapter_task.delay(novel_name, chapter_num)


celery_app.autodiscover_tasks(['src.workers'], force=True)
