from typing import TypedDict, Dict, Any, Optional


class AgentState(TypedDict, total=False):
    novel_name: str
    chapter_num: int
    outline: Optional[str]
    draft_content: Optional[str]
    critique_comments: Optional[str]
    critique_score: Optional[int]
    revision_count: int
    reference_context: Optional[str]
    character_bios: Optional[str]
    world_setting: Optional[str]
    reference_style: Optional[str]
    character_updates: Dict[str, Any]
    previous_context: Optional[list]
    status: str
    current_node: Optional[str]
    current_stage: str
    scene_feedback: Dict[int, Dict]
    review_results: Dict[str, Any]
    rewrite_type: str
    target_scenes: list
    attempt_count: int