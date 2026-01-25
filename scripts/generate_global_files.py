from pathlib import Path
import sys
from dotenv import load_dotenv
import json

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / ".env")

from src.core.config import Settings
from src.core.llm import LLMClient
from src.utils.file_manager import ProjectManager
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


FICTION_SYSTEM_PROMPT = """
你是一位专业的文学编辑和小说创作助手。

【合规要求，必须遵守】
1. 所有产出必须符合中华人民共和国法律法规及内容安全与出版规范，禁止任何非法、政治敏感、色情、暴力恐怖、违法犯罪或违背公序良俗的内容。
2. 内容健康向上，适合全年龄或合规分级受众；不涉及真实政党、敏感历史事件或违法犯罪细节。
3. 在合规前提下进行客观分析与文学润色，严格遵循用户指令（如 JSON 格式），并**使用简体中文**回复。
"""


def _estimate_tokens(text: str) -> int:
    """估算token数量"""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


def generate_direct(llm_client: LLMClient, system_prompt: str, user_content: str, max_retries: int = 10):
    """直接输入所有内容，不分块（模型支持262k上下文），重试10次保证得到有效答案"""
    estimated_tokens = _estimate_tokens(user_content)
    logger.info(f"输入内容估算token: {estimated_tokens}，直接输入（模型支持262k上下文）")
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"尝试生成（第 {attempt}/{max_retries} 次）...")
            response = llm_client.chat(messages, temperature=0.7, max_tokens=8192)
            if response and len(response.strip()) > 100:
                logger.info(f"✅ 获得有效响应，长度: {len(response)} 字符")
                return response
            else:
                logger.warning(f"响应内容过短或为空（{len(response) if response else 0} 字符），重试...")
        except Exception as e:
            logger.warning(f"请求失败: {e}")
        
        if attempt < max_retries:
            import time
            time.sleep(2)
    
    logger.error(f"❌ 已重试 {max_retries} 次，仍未获得有效响应")
    return None


def collect_all_extractions(file_manager: ProjectManager, novel_name: str):
    """收集所有章节的提取信息"""
    chapters = file_manager.list_chapters(novel_name)
    all_extractions = []
    all_outlines = []
    
    for chapter_num in sorted(chapters):
        chapter_path = file_manager.get_chapter_path(novel_name, chapter_num)
        extraction_path = chapter_path / "extraction.json"
        outline_path = chapter_path / "outline.md"
        
        if extraction_path.exists():
            extraction = file_manager.load_content(extraction_path)
            all_extractions.append({
                "chapter_num": chapter_num,
                "extraction": extraction
            })
            logger.info(f"收集章节 {chapter_num} 的提取信息")
        
        if outline_path.exists():
            outline = file_manager.load_content(outline_path)
            all_outlines.append({
                "chapter_num": chapter_num,
                "outline": outline
            })
    
    return all_extractions, all_outlines


def generate_bios(llm_client: LLMClient, all_extractions: list) -> dict:
    """生成人物档案"""
    logger.info("开始生成人物档案...")
    
    characters_summary = []
    for item in all_extractions:
        extraction = item.get("extraction", {})
        chars = extraction.get("characters", [])
        if chars:
            characters_summary.append(f"第{item['chapter_num']}章: {json.dumps(chars, ensure_ascii=False, indent=2)}")
    
    if not characters_summary:
        logger.warning("未找到任何人物信息")
        return {}
    
    characters_text = "\n\n".join(characters_summary)
    
    system_prompt = (
        FICTION_SYSTEM_PROMPT + "\n\n" +
        "你是一位专业的小说设定架构师。请根据所有章节中提取的人物信息，生成一份完整、详细的人物档案。\n\n"
        "要求：\n"
        "1. 合并重复人物，整合不同章节中的信息\n"
        "2. 为每个人物提供完整的描述：姓名、别名、角色定位、性格特点、外貌、能力、背景、当前状态等\n"
        "3. 确保信息详细且准确\n"
        "4. 以 JSON 格式输出，格式如下：\n"
        '{"人物姓名": {"name": "姓名", "aliases": ["别名1", "别名2"], "role": "主角/配角/反派", '
        '"personality": "性格描述", "appearance": "外貌描述", "abilities": ["能力1", "能力2"], '
        '"background": "背景信息", "status": "当前状态", "description": "综合描述"}}'
    )
    
    user_prompt = (
        f"以下是所有章节中提取的人物信息：\n\n{characters_text}\n\n"
        f"请生成一份完整、详细的人物档案，合并重复人物并整合信息。"
    )
    
    response = generate_direct(llm_client, system_prompt, user_prompt, max_retries=10)
    
    if not response:
        logger.error("生成失败")
        return {}
    
    json_text = response.strip()
    if "```json" in json_text:
        start = json_text.find("```json") + 7
        end = json_text.find("```", start)
        if end == -1:
            end = len(json_text)
        json_text = json_text[start:end].strip()
    elif "```" in json_text:
        start = json_text.find("```") + 3
        end = json_text.find("```", start)
        if end == -1:
            end = len(json_text)
        json_text = json_text[start:end].strip()
    
    if not json_text.startswith("{"):
        if "{" in json_text:
            start = json_text.find("{")
            end = json_text.rfind("}") + 1
            json_text = json_text[start:end]
    
    try:
        bios = json.loads(json_text)
        return bios
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}，尝试修复...")
        try:
            import re
            json_match = re.search(r'\{.*\}', json_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
                bios = json.loads(json_text)
                logger.info("通过正则表达式提取JSON成功")
                return bios
        except Exception as e2:
            logger.warning(f"正则提取也失败: {e2}")
        
        try:
            lines = json_text.split('\n')
            fixed_lines = []
            for line in lines:
                if line.strip() and not line.strip().startswith('//'):
                    fixed_lines.append(line)
            fixed_json = '\n'.join(fixed_lines)
            bios = json.loads(fixed_json)
            logger.info("通过移除注释修复JSON成功")
            return bios
        except Exception as e3:
            logger.error(f"修复JSON失败: {e3}")
            logger.error(f"JSON文本前1000字符: {json_text[:1000]}")
            return {}


def generate_world_setting(llm_client: LLMClient, all_extractions: list, all_outlines: list) -> str:
    """生成世界观设定"""
    logger.info("开始生成世界观设定...")
    
    world_summary = []
    for item in all_extractions:
        extraction = item.get("extraction", {})
        world_items = extraction.get("world_setting", [])
        if world_items:
            world_summary.append(f"第{item['chapter_num']}章: {json.dumps(world_items, ensure_ascii=False, indent=2)}")
    
    outlines_summary = []
    for item in all_outlines:
        outlines_summary.append(f"第{item['chapter_num']}章大纲:\n{item['outline']}")
    
    world_text = "\n\n".join(world_summary) if world_summary else "暂无世界观信息"
    outlines_text = "\n\n---\n\n".join(outlines_summary) if outlines_summary else "暂无大纲信息"
    
    system_prompt = (
        FICTION_SYSTEM_PROMPT + "\n\n" +
        "你是一位专业的小说设定架构师。请根据所有章节中提取的世界观信息和章节大纲，生成一份完整、详细的世界观设定文档。\n\n"
        "要求：\n"
        "1. 整合所有世界观要素（地理位置、势力组织、规则体系、关键物品等）\n"
        "2. 根据章节大纲补充世界观细节\n"
        "3. 使用 Markdown 格式，结构清晰，分类明确\n"
        "4. 内容要详细且完整，至少包含以下部分：\n"
        "   - 世界背景概述\n"
        "   - 主要地理位置\n"
        "   - 势力组织\n"
        "   - 规则体系（如虚拟系统规则、价格体系等）\n"
        "   - 关键物品和道具\n"
        "   - 特殊设定\n"
        "5. 如果信息不足，可以根据章节大纲合理推断和补充\n"
        "6. 必须输出完整的 Markdown 文档，不要只输出标题或简短内容"
    )
    
    user_prompt = (
        f"以下是所有章节中提取的世界观信息（共{len(world_summary)}章有世界观信息）：\n\n{world_text}\n\n"
        f"以下是所有章节的大纲（共{len(all_outlines)}章）：\n\n{outlines_text}\n\n"
        f"请根据以上信息，生成一份完整、详细的世界观设定文档。要求：\n"
        f"1. 内容详细，每个部分都要有具体描述\n"
        f"2. 结构清晰，使用 Markdown 标题和列表\n"
        f"3. 分类明确，按照要求的部分组织内容\n"
        f"4. 至少 2000 字以上，确保内容充实"
    )
    
    response = generate_direct(llm_client, system_prompt, user_prompt, max_retries=10)
    
    if not response:
        logger.error("世界观设定生成失败")
        return ""
    
    if len(response.strip()) > 500:
        logger.info(f"生成成功，内容长度: {len(response)} 字符")
        return response
    else:
        logger.warning(f"响应内容过短（{len(response)} 字符），重试...")
        user_prompt_enhanced = user_prompt + "\n\n请确保输出详细内容，不要只输出标题。每个部分都要有具体描述。至少2000字以上。"
        response = generate_direct(llm_client, system_prompt, user_prompt_enhanced, max_retries=10)
        if response and len(response.strip()) > 500:
            return response
        else:
            logger.error("世界观设定生成失败：内容过短")
            return ""


def generate_relation_graph(llm_client: LLMClient, all_extractions: list) -> dict:
    """生成关系图"""
    logger.info("开始生成关系图...")
    
    relations_summary = []
    for item in all_extractions:
        extraction = item.get("extraction", {})
        relations = extraction.get("relationships", [])
        if relations:
            relations_summary.append(f"第{item['chapter_num']}章: {json.dumps(relations, ensure_ascii=False, indent=2)}")
    
    if not relations_summary:
        logger.warning("未找到任何关系信息")
        return {}
    
    relations_text = "\n\n".join(relations_summary)
    
    system_prompt = (
        FICTION_SYSTEM_PROMPT + "\n\n" +
        "你是一位专业的小说设定架构师。请根据所有章节中提取的人物关系信息，生成一份完整的关系图。\n\n"
        "要求：\n"
        "1. 合并重复关系，整合不同章节中的信息\n"
        "2. 以人物为中心，建立关系网络\n"
        "3. 关系类型包括：师徒、仇敌、盟友、恋人、家族、组织等\n"
        "4. 以 JSON 格式输出，格式如下：\n"
        '{"人物A": {"人物B": "关系类型", "人物C": "关系类型"}, "人物B": {"人物A": "关系类型"}}'
    )
    
    user_prompt = (
        f"以下是所有章节中提取的人物关系信息：\n\n{relations_text}\n\n"
        f"请生成一份完整的关系图，合并重复关系并整合信息。"
    )
    
    response = generate_direct(llm_client, system_prompt, user_prompt, max_retries=10)
    
    if not response:
        logger.error("生成失败")
        return {}
    
    json_text = response.strip()
    if "```json" in json_text:
        start = json_text.find("```json") + 7
        end = json_text.find("```", start)
        if end == -1:
            end = len(json_text)
        json_text = json_text[start:end].strip()
    elif "```" in json_text:
        start = json_text.find("```") + 3
        end = json_text.find("```", start)
        if end == -1:
            end = len(json_text)
        json_text = json_text[start:end].strip()
    
    if json_text.startswith("{"):
        json_text = json_text
    elif "{" in json_text:
        start = json_text.find("{")
        end = json_text.rfind("}") + 1
        json_text = json_text[start:end]
    
    try:
        relations = json.loads(json_text)
        return relations
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        logger.error(f"响应前500字符: {response[:500]}")
        logger.error(f"JSON文本前500字符: {json_text[:500]}")
        try:
            import re
            json_match = re.search(r'\{.*\}', json_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
                relations = json.loads(json_text)
                logger.info("通过正则表达式提取JSON成功")
                return relations
        except:
            pass
        return {}




def main():
    novel_name = "史莱姆契约公主"
    
    logger.info(f"开始为小说《{novel_name}》生成全局设定文件...")
    
    config = Settings.load_from_yaml(project_root / "config" / "settings.yaml")
    workspace_root = Path(config.paths.workspace)
    
    llm_client = LLMClient(
        provider=config.model.provider,
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    
    file_manager = ProjectManager(workspace_root)
    
    logger.info("收集所有章节的提取信息和大纲...")
    all_extractions, all_outlines = collect_all_extractions(file_manager, novel_name)
    
    logger.info(f"共收集到 {len(all_extractions)} 个章节的提取信息，{len(all_outlines)} 个章节的大纲")
    
    global_path = file_manager.get_global_settings_path(novel_name)
    global_path.mkdir(parents=True, exist_ok=True)
    
    logger.info("开始生成人物档案...")
    bios = generate_bios(llm_client, all_extractions)
    if bios and len(bios) > 0:
        bios_path = global_path / "bios.json"
        file_manager.save_content(bios_path, bios)
        logger.info(f"✅ 人物档案已保存到 {bios_path}，包含 {len(bios)} 个人物")
    else:
        logger.error("❌ 人物档案生成失败")
    
    logger.info("开始生成世界观设定...")
    world_setting = generate_world_setting(llm_client, all_extractions, all_outlines)
    if world_setting and len(world_setting.strip()) > 500:
        world_path = global_path / "world.md"
        file_manager.save_content(world_path, world_setting)
        logger.info(f"✅ 世界观设定已保存到 {world_path}，长度: {len(world_setting)} 字符")
    else:
        logger.error("❌ 世界观设定生成失败")
    
    logger.info("开始生成关系图...")
    relation_graph = generate_relation_graph(llm_client, all_extractions)
    if relation_graph and len(relation_graph) > 0:
        relation_path = global_path / "relation_graph.json"
        file_manager.save_content(relation_path, relation_graph)
        logger.info(f"✅ 关系图已保存到 {relation_path}，包含 {len(relation_graph)} 个人物关系")
    else:
        logger.error("❌ 关系图生成失败")
    
    logger.info("\n全局设定文件生成完成！")
    logger.info(f"人物档案: {'✅' if bios else '❌'}")
    logger.info(f"世界观设定: {'✅' if world_setting else '❌'}")
    logger.info(f"关系图: {'✅' if relation_graph else '❌'}")


if __name__ == "__main__":
    main()
