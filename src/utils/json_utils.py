import json
import re
import logging

logger = logging.getLogger(__name__)


def parse_json_from_response(response: str) -> dict:
    """
    从 LLM 响应中解析 JSON，支持多种格式
    """
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
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}，尝试修复...")
        
        try:
            json_match = re.search(r'\{.*\}', json_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
                return json.loads(json_text)
        except Exception as e2:
            logger.warning(f"正则提取也失败: {e2}")
        
        try:
            lines = json_text.split('\n')
            fixed_lines = []
            for line in lines:
                if line.strip() and not line.strip().startswith('//'):
                    fixed_lines.append(line)
            fixed_json = '\n'.join(fixed_lines)
            return json.loads(fixed_json)
        except Exception as e3:
            logger.error(f"修复JSON失败: {e3}")
            logger.error(f"JSON文本前1000字符: {json_text[:1000]}")
            raise ValueError(f"无法解析JSON响应: {e3}")
