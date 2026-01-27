"""校验三元组多行 JSON 解析修复：LLM 返回多行独立对象时的解析."""
import pytest
from src.utils.json_utils import parse_json_from_response


def test_parse_multiple_json_objects_as_array():
    # 模拟 LLM 返回「多行独立 JSON 对象」而非 [ {...}, {...} ]
    raw = """{"subject": "林未", "relation": "拥有", "object": "基础心法"},
  {"subject": "基础心法", "relation": "记载", "object": "心随意动，意随脉走"},
  {"subject": "林未", "relation": "尝试", "object": "吐纳方式"},
  {"subject": "林未", "relation": "感受到", "object": "小腹热气"},
  {"subject": "阿福", "relation": "邀请", "object": "林未"}"""
    out = parse_json_from_response(raw)
    assert isinstance(out, list)
    assert len(out) == 5
    assert out[0]["subject"] == "林未" and out[0]["object"] == "基础心法"
    assert out[4]["subject"] == "阿福" and out[4]["relation"] == "邀请"
