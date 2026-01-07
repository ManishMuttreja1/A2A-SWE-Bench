"""Scoring algorithm for agent performance"""

import math
import statistics
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class ScoreWeights:
    """Weights for different scoring components"""
    success_rate: float = 0.25
    efficiency: float = 0.20
    quality: float = 0.20
    speed: float = 0.15
    exploration: float = 0.10
    memorization_penalty: float = 0.10


class ScoringAlgorithm:
    """
    Multi-dimensional scoring algorithm for agent performance.
    """
    
    def __init__(self, weights: Optional[ScoreWeights] = None):
        self.weights = weights or ScoreWeights()
    
    def calculate_scores(
        self,
        assessment: Any,
        trajectory_analysis: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Calculate all scores for an assessment.
        
        Args:
            assessment: Assessment object
            trajectory_analysis: Trajectory analysis results
            
        Returns:
            Dictionary of scores
        """
        # Success rate score (0-100)
        success_rate = self._calculate_success_rate(assessment)
        
        # Efficiency score (0-100)
        efficiency_score = self._calculate_efficiency_score(
            trajectory_analysis.get("efficiency", {})
        )
        
        # Quality score (0-100)
        quality_score = self._calculate_quality_score(
            assessment,
            trajectory_analysis
        )
        
        # Speed score (0-100)
        speed_score = self._calculate_speed_score(
            assessment,
            trajectory_analysis.get("metrics", {})
        )
        
        # Exploration score (0-100)
        exploration_score = self._calculate_exploration_score(
            trajectory_analysis.get("patterns", {}),
            trajectory_analysis.get("file_analysis", {})
        )
        
        # Memorization penalty (0-100, lower is better)
        memorization_penalty = self._calculate_memorization_penalty(
            trajectory_analysis.get("patterns", {})
        )
        
        # Calculate overall score
        overall_score = self._calculate_overall_score({
            "success_rate": success_rate,
            "efficiency": efficiency_score,
            "quality": quality_score,
            "speed": speed_score,
            "exploration": exploration_score,
            "memorization_penalty": memorization_penalty
        })
        
        return {
            "success_rate": success_rate,
            "efficiency_score": efficiency_score,
            "quality_score": quality_score,
            "speed_score": speed_score,
            "exploration_score": exploration_score,
            "memorization_penalty": memorization_penalty,
            "overall_score": overall_score
        }
    
    def _calculate_success_rate(self, assessment: Any) -> float:
        """Calculate success rate score"""
        if assessment.passed:
            # Full pass gets base score
            base_score = 70
            
            # Bonus for test coverage
            if assessment.tests_passed > 0:
                test_bonus = min(30, (assessment.tests_passed / 
                                     (assessment.tests_passed + assessment.tests_failed)) * 30)
            else:
                test_bonus = 0
            
            return base_score + test_bonus
        else:
            # Partial credit for partial success
            if assessment.patch_applied:
                base_score = 30
            else:
                base_score = 0
            
            # Partial credit for passing some tests
            if assessment.tests_passed > 0 and (assessment.tests_passed + assessment.tests_failed) > 0:
                test_score = (assessment.tests_passed / 
                            (assessment.tests_passed + assessment.tests_failed)) * 30
            else:
                test_score = 0
            
            return base_score + test_score
    
    def _calculate_efficiency_score(
        self,
        efficiency_data: Dict[str, Any]
    ) -> float:
        """Calculate efficiency score"""
        # Start with efficiency score from analyzer
        base_score = efficiency_data.get("efficiency_score", 50)
        
        # Adjust based on redundancy
        redundancy_rate = efficiency_data.get("redundancy_rate", 0)
        redundancy_penalty = min(20, redundancy_rate * 100)
        
        # Adjust based on backtracking
        backtrack_count = efficiency_data.get("backtrack_count", 0)
        backtrack_penalty = min(15, backtrack_count * 3)
        
        # Bonus for high unique action ratio
        unique_ratio = efficiency_data.get("unique_action_ratio", 0.5)
        unique_bonus = unique_ratio * 10
        
        final_score = base_score - redundancy_penalty - backtrack_penalty + unique_bonus
        
        return max(0, min(100, final_score))
    
    def _calculate_quality_score(
        self,
        assessment: Any,
        trajectory_analysis: Dict[str, Any]
    ) -> float:
        """Calculate code quality score"""
        base_score = 50
        
        # Patch size consideration
        if assessment.patch_size:
            if assessment.patch_size < 10:
                size_score = 20  # Very concise
            elif assessment.patch_size < 50:
                size_score = 15  # Good size
            elif assessment.patch_size < 100:
                size_score = 10  # Acceptable
            else:
                size_score = 5   # Large patch
        else:
            size_score = 0
        
        # Error handling
        error_rate = trajectory_analysis.get("error_analysis", {}).get("error_rate", 0.5)
        error_score = (1 - error_rate) * 20
        
        # Confidence score from assessment
        confidence_score = (assessment.confidence_score or 0.5) * 10
        
        return base_score + size_score + error_score + confidence_score
    
    def _calculate_speed_score(
        self,
        assessment: Any,
        metrics: Dict[str, Any]
    ) -> float:
        """Calculate speed score"""
        # Execution time scoring
        if assessment.execution_time:
            if assessment.execution_time < 30:
                time_score = 40  # Very fast
            elif assessment.execution_time < 60:
                time_score = 35  # Fast
            elif assessment.execution_time < 120:
                time_score = 30  # Good
            elif assessment.execution_time < 300:
                time_score = 20  # Acceptable
            else:
                time_score = 10  # Slow
        else:
            time_score = 20
        
        # Actions per minute scoring
        apm = metrics.get("actions_per_minute", 10)
        if apm > 20:
            apm_score = 30  # Very active
        elif apm > 10:
            apm_score = 25  # Active
        elif apm > 5:
            apm_score = 20  # Moderate
        else:
            apm_score = 10  # Slow
        
        # Token efficiency
        if assessment.token_usage:
            if assessment.token_usage < 1000:
                token_score = 30  # Very efficient
            elif assessment.token_usage < 5000:
                token_score = 25  # Efficient
            elif assessment.token_usage < 10000:
                token_score = 20  # Moderate
            else:
                token_score = 10  # Token heavy
        else:
            token_score = 15
        
        return (time_score + apm_score + token_score) * (100/100)
    
    def _calculate_exploration_score(
        self,
        patterns: Dict[str, Any],
        file_analysis: Dict[str, Any]
    ) -> float:
        """Calculate exploration score"""
        # Exploration breadth
        breadth = patterns.get("exploration_breadth", 0)
        breadth_score = min(40, breadth * 2)
        
        # Shows reasoning
        shows_reasoning = patterns.get("shows_reasoning", False)
        reasoning_score = 30 if shows_reasoning else 0
        
        # File coverage
        files_accessed = file_analysis.get("total_files_accessed", 0)
        if files_accessed > 10:
            coverage_score = 30
        elif files_accessed > 5:
            coverage_score = 20
        elif files_accessed > 2:
            coverage_score = 10
        else:
            coverage_score = 5
        
        return breadth_score + reasoning_score + coverage_score
    
    def _calculate_memorization_penalty(
        self,
        patterns: Dict[str, Any]
    ) -> float:
        """
        Calculate memorization penalty (lower is better).
        High scores indicate likely memorization.
        """
        memorization_score = patterns.get("memorization_score", 0)
        
        # Additional indicators
        detected_patterns = patterns.get("detected_patterns", [])
        
        # Penalty for no exploration patterns
        if not detected_patterns:
            memorization_score += 20
        
        # Check for direct solution indicators
        if "blind_search" not in detected_patterns:
            memorization_score += 10
        
        return min(100, memorization_score)
    
    def _calculate_overall_score(
        self,
        scores: Dict[str, float]
    ) -> float:
        """Calculate weighted overall score"""
        overall = (
            scores["success_rate"] * self.weights.success_rate +
            scores["efficiency"] * self.weights.efficiency +
            scores["quality"] * self.weights.quality +
            scores["speed"] * self.weights.speed +
            scores["exploration"] * self.weights.exploration +
            (100 - scores["memorization_penalty"]) * self.weights.memorization_penalty
        )
        
        return round(overall, 2)
    
    def calculate_team_score(
        self,
        team_results: List[Dict[str, float]]
    ) -> Dict[str, float]:
        """
        Calculate score for a multi-agent team.
        
        Args:
            team_results: List of individual agent scores
            
        Returns:
            Team score dictionary
        """
        if not team_results:
            return {"overall_score": 0}
        
        # Calculate average scores
        avg_scores = {}
        score_keys = team_results[0].keys()
        
        for key in score_keys:
            values = [r[key] for r in team_results if key in r]
            avg_scores[key] = statistics.mean(values) if values else 0
        
        # Bonus for coordination (if all agents succeeded)
        coordination_bonus = 0
        if all(r.get("success_rate", 0) > 50 for r in team_results):
            coordination_bonus = 10
        
        # Calculate team overall score
        team_overall = avg_scores.get("overall_score", 0) + coordination_bonus
        
        return {
            **avg_scores,
            "team_overall_score": min(100, team_overall),
            "coordination_bonus": coordination_bonus,
            "team_size": len(team_results)
        }
    
    def calculate_improvement(
        self,
        old_scores: Dict[str, float],
        new_scores: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate improvement between two assessments.
        
        Args:
            old_scores: Previous assessment scores
            new_scores: Current assessment scores
            
        Returns:
            Improvement metrics
        """
        improvements = {}
        
        for key in new_scores:
            if key in old_scores:
                improvement = new_scores[key] - old_scores[key]
                improvements[f"{key}_improvement"] = improvement
                improvements[f"{key}_improvement_pct"] = (
                    (improvement / old_scores[key] * 100) 
                    if old_scores[key] > 0 else 0
                )
        
        # Overall improvement
        old_overall = old_scores.get("overall_score", 0)
        new_overall = new_scores.get("overall_score", 0)
        
        improvements["overall_improvement"] = new_overall - old_overall
        improvements["overall_improvement_pct"] = (
            ((new_overall - old_overall) / old_overall * 100)
            if old_overall > 0 else 0
        )
        
        return improvements
    
    def normalize_scores(
        self,
        scores: List[Dict[str, float]]
    ) -> List[Dict[str, float]]:
        """
        Normalize scores relative to population.
        
        Args:
            scores: List of score dictionaries
            
        Returns:
            Normalized scores
        """
        if len(scores) < 2:
            return scores
        
        normalized = []
        
        # Calculate statistics for each metric
        metrics = {}
        for key in scores[0].keys():
            values = [s[key] for s in scores if key in s]
            if values:
                metrics[key] = {
                    "mean": statistics.mean(values),
                    "stdev": statistics.stdev(values) if len(values) > 1 else 1
                }
        
        # Normalize each score
        for score in scores:
            norm_score = {}
            for key, value in score.items():
                if key in metrics and metrics[key]["stdev"] > 0:
                    # Z-score normalization
                    z_score = (value - metrics[key]["mean"]) / metrics[key]["stdev"]
                    # Convert to 0-100 scale
                    norm_score[f"{key}_normalized"] = 50 + (z_score * 10)
                    norm_score[f"{key}_normalized"] = max(0, min(100, norm_score[f"{key}_normalized"]))
                norm_score[key] = value
            
            normalized.append(norm_score)
        
        return normalized