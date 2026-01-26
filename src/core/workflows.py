"""
工作流注册表：为每个工作流定义唯一标识与路由规则，供中控按 workflow_type 选用。
扩展时在此注册新 id 与对应的 _build_*_rules() 即可。
"""
from typing import Dict, List, Any, Optional

from src.core.routing import RoutingRule

# 工作流唯一标识，中控凭此选择路由
WORKFLOW_GENERATE_CHAPTER = "generate_chapter"   # 生成新章节（现有完整流程）
WORKFLOW_OUTLINE_ONLY = "outline_only"           # 仅生成大纲
WORKFLOW_CONTENT_ONLY = "content_only"           # 仅生成正文（需已有大纲，从 DB 拉取后跑 writer）
WORKFLOW_APPROVAL_ONLY = "approval_only"         # 仅进行审批（architect -> 产出走审批，不入库）
WORKFLOW_MEDIA_ONLY = "media_only"               # 仅生成媒体（从 DB 拉取正文后跑 media）

# 默认工作流（未指定或旧数据无 workflow_type 时使用）
DEFAULT_WORKFLOW_ID = WORKFLOW_GENERATE_CHAPTER


def _build_generate_chapter_rules() -> Dict[str, RoutingRule]:
    """生成新章节：start -> architect -> writer -> censor -> critic -> (media | writer)。knowledge 已脱离工作流，仅支持手动调用。"""
    return {
        "architect": RoutingRule("architect", ["writer"], condition=lambda d: True),
        "writer": RoutingRule("writer", ["censor"], condition=lambda d: True),
        "censor": RoutingRule(
            "censor", ["critic"],
            condition=lambda d: not d.get("is_sensitive", True),
            else_agents=[],
        ),
        "critic": RoutingRule(
            "critic", ["media"],
            condition=lambda d: d.get("score", 0) >= 75,
            else_agents=["writer"],
        ),
        "media": RoutingRule("media", [], condition=lambda d: True),
    }


def _build_outline_only_rules() -> Dict[str, RoutingRule]:
    """仅生成大纲：start -> architect -> end"""
    return {
        "architect": RoutingRule("architect", [], condition=lambda d: True),
    }


def _build_content_only_rules() -> Dict[str, RoutingRule]:
    """仅生成正文：start -> writer -> end（由 start 预填 outline 后发 writer）"""
    return {
        "writer": RoutingRule("writer", [], condition=lambda d: True),
    }


def _build_approval_only_rules() -> Dict[str, RoutingRule]:
    """仅进行审批：architect 产出走审批，不入库；与 outline_only 同拓扑，由 handler 区分写 PendingWrite"""
    return {
        "architect": RoutingRule("architect", [], condition=lambda d: True),
    }


def _build_media_only_rules() -> Dict[str, RoutingRule]:
    """仅生成媒体：start -> media -> end（由 start 预填正文/场景后发 media）"""
    return {
        "media": RoutingRule("media", [], condition=lambda d: True),
    }


_REGISTRY: Dict[str, Dict[str, RoutingRule]] = {
    WORKFLOW_GENERATE_CHAPTER: _build_generate_chapter_rules(),
    WORKFLOW_OUTLINE_ONLY: _build_outline_only_rules(),
    WORKFLOW_CONTENT_ONLY: _build_content_only_rules(),
    WORKFLOW_APPROVAL_ONLY: _build_approval_only_rules(),
    WORKFLOW_MEDIA_ONLY: _build_media_only_rules(),
}


def get_routing_rules(workflow_type: str) -> Dict[str, RoutingRule]:
    """按工作流唯一标识返回该工作流的路由规则（source_agent -> RoutingRule）。"""
    if not workflow_type:
        workflow_type = DEFAULT_WORKFLOW_ID
    return _REGISTRY.get(workflow_type, _REGISTRY[DEFAULT_WORKFLOW_ID])


def list_workflow_ids() -> List[str]:
    """返回所有已注册的工作流 id，便于前端/API 展示。"""
    return list(_REGISTRY.keys())


# 工作流显示名称（id -> 名称）
WORKFLOW_NAMES: Dict[str, str] = {
    WORKFLOW_GENERATE_CHAPTER: "生成新章节",
    WORKFLOW_OUTLINE_ONLY: "仅生成大纲",
    WORKFLOW_CONTENT_ONLY: "仅生成正文",
    WORKFLOW_APPROVAL_ONLY: "仅进行审批",
    WORKFLOW_MEDIA_ONLY: "仅生成媒体",
}


def list_workflows() -> List[Dict[str, str]]:
    """返回所有工作流的 id 与 name，供前端工作流切换使用。"""
    return [
        {"id": wid, "name": WORKFLOW_NAMES.get(wid, wid)}
        for wid in list_workflow_ids()
    ]
