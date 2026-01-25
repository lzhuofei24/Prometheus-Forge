import logging
from typing import Dict, Any
from pathlib import Path
import yaml
from src.core.state import AgentState
from .style_checker import StyleChecker
from .character_checker import CharacterChecker
from .plot_checker import PlotChecker

logger = logging.getLogger(__name__)


class ReviewerTeam:
    def __init__(self, llm_client, file_manager):
        self.style_checker = StyleChecker(llm_client, file_manager)
        self.character_checker = CharacterChecker(llm_client, file_manager)
        self.plot_checker = PlotChecker(llm_client, file_manager)
        self.file_manager = file_manager
        
        project_root = Path(__file__).parent.parent.parent.parent
        config_path = project_root / "config" / "settings.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        
        reviewer_config = config_data.get("reviewers", {})
        self.weights = {
            "style": reviewer_config.get("style", {}).get("weight", 0.33),
            "character": reviewer_config.get("character", {}).get("weight", 0.33),
            "plot": reviewer_config.get("plot", {}).get("weight", 0.34)
        }
        self.overall_threshold = reviewer_config.get("overall_pass_threshold", 70)
    
    def review_parallel(self, state: AgentState) -> AgentState:
        """并行执行3个Checker（目前为串行，后续可接入Celery）"""
        logger.info(f"[ReviewerTeam] 开始并行审稿第 {state['chapter_num']} 章")
        
        # TODO: 后续改为Celery group并行执行
        # from celery import group
        # job = group([
        #     check_style_task.si(state["novel_name"], state["chapter_num"]),
        #     check_character_task.si(state["novel_name"], state["chapter_num"]),
        #     check_plot_task.si(state["novel_name"], state["chapter_num"])
        # ])
        # results = job.apply_async().get()
        
        # 当前串行执行
        style_result = self.style_checker.check(state)
        character_result = self.character_checker.check(state)
        plot_result = self.plot_checker.check(state)
        
        review_results = {
            "style": style_result,
            "character": character_result,
            "plot": plot_result
        }
        
        state["review_results"] = review_results
        
        overall_score = self._calculate_overall_score(review_results)
        state["critique_score"] = overall_score
        
        combined_comments = self._combine_comments(review_results)
        state["critique_comments"] = combined_comments
        
        low_score_scenes = self._identify_low_score_scenes(review_results)
        state["target_scenes"] = low_score_scenes
        
        scene_feedback = self._build_scene_feedback(review_results)
        state["scene_feedback"] = scene_feedback
        
        logger.info(f"[ReviewerTeam] 审稿完成，综合评分: {overall_score}, 低分场景: {low_score_scenes}")
        
        novel_name = state["novel_name"]
        chapter_num = state["chapter_num"]
        chapter_path = self.file_manager.get_chapter_path(novel_name, chapter_num)
        review_path = chapter_path / "review.json"
        
        import json
        review_data = {
            "overall_score": overall_score,
            "review_results": review_results,
            "scene_feedback": scene_feedback,
            "low_score_scenes": low_score_scenes
        }
        self.file_manager.save_content(review_path, review_data)
        
        return state
    
    def _calculate_overall_score(self, results: Dict[str, Any]) -> int:
        """加权平均计算综合分"""
        total = 0
        for checker_name, weight in self.weights.items():
            score = results.get(checker_name, {}).get("score", 0)
            total += score * weight
        return int(total)
    
    def _combine_comments(self, results: Dict[str, Any]) -> str:
        """合并所有Checker的意见"""
        comments = []
        for checker_name, result in results.items():
            score = result.get("score", 0)
            comments.append(f"\n### {checker_name.capitalize()} 评分: {score}/100\n")
            
            issues = result.get("issues", [])
            if issues:
                comments.append("**问题：**")
                for issue in issues:
                    scene_id = issue.get("scene_id", 0)
                    issue_type = issue.get("type", "")
                    desc = issue.get("description", "")
                    comments.append(f"- [场景{scene_id}] {issue_type}: {desc}")
            
            suggestions = result.get("suggestions", [])
            if suggestions:
                comments.append("\n**建议：**")
                for sugg in suggestions:
                    comments.append(f"- {sugg}")
            
            strengths = result.get("strengths", [])
            if strengths:
                comments.append("\n**优点：**")
                for strength in strengths:
                    comments.append(f"- {strength}")
        
        return "\n".join(comments)
    
    def _identify_low_score_scenes(self, results: Dict[str, Any], threshold: int = 60) -> list:
        """识别低分场景"""
        scene_scores = {}
        
        for checker_name, result in results.items():
            issues = result.get("issues", [])
            for issue in issues:
                scene_id = issue.get("scene_id", 0)
                if scene_id > 0:
                    if scene_id not in scene_scores:
                        scene_scores[scene_id] = []
                    scene_scores[scene_id].append(checker_name)
        
        low_scenes = [scene_id for scene_id, checkers in scene_scores.items() 
                     if len(checkers) >= 2]
        
        return sorted(low_scenes)
    
    def _build_scene_feedback(self, results: Dict[str, Any]) -> Dict[int, Dict]:
        """构建按场景组织的反馈"""
        scene_feedback = {}
        
        for checker_name, result in results.items():
            issues = result.get("issues", [])
            for issue in issues:
                scene_id = issue.get("scene_id", 0)
                if scene_id > 0:
                    if scene_id not in scene_feedback:
                        scene_feedback[scene_id] = {"issues": [], "checkers": []}
                    scene_feedback[scene_id]["issues"].append({
                        "checker": checker_name,
                        "type": issue.get("type", ""),
                        "description": issue.get("description", "")
                    })
                    if checker_name not in scene_feedback[scene_id]["checkers"]:
                        scene_feedback[scene_id]["checkers"].append(checker_name)
        
        return scene_feedback
