"""Trajectory analysis for metrics and insights"""

import json
import statistics
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict, Counter
from datetime import datetime
import re

from ..database import get_session, Trajectory, Assessment, Result


class TrajectoryAnalyzer:
    """Analyzes trajectories to compute metrics and insights"""
    
    def __init__(self):
        self.patterns = self._load_patterns()
    
    def _load_patterns(self) -> Dict[str, Any]:
        """Load analysis patterns"""
        return {
            "exploration_patterns": [
                {"name": "blind_search", "regex": r"search.*without.*context"},
                {"name": "targeted_search", "regex": r"search.*specific.*function"},
                {"name": "breadth_first", "regex": r"explore.*directory"},
                {"name": "depth_first", "regex": r"trace.*call.*stack"}
            ],
            "error_patterns": [
                {"name": "retry", "regex": r"retry|again|repeat"},
                {"name": "backtrack", "regex": r"revert|undo|back"},
                {"name": "stuck", "regex": r"same.*action.*multiple"}
            ],
            "efficiency_indicators": [
                {"name": "direct_fix", "min_actions": 1, "max_actions": 5},
                {"name": "exploratory", "min_actions": 6, "max_actions": 15},
                {"name": "struggling", "min_actions": 16, "max_actions": None}
            ]
        }
    
    async def analyze_trajectory(
        self,
        task_id: str
    ) -> Dict[str, Any]:
        """
        Comprehensive analysis of a task trajectory.
        
        Args:
            task_id: Task ID to analyze
            
        Returns:
            Analysis results with metrics
        """
        with get_session() as session:
            trajectories = session.query(Trajectory).filter_by(
                task_id=task_id
            ).order_by(Trajectory.sequence_number).all()
            
            if not trajectories:
                return {"error": "No trajectory found"}
            
            # Basic metrics
            metrics = self._compute_basic_metrics(trajectories)
            
            # Action analysis
            action_analysis = self._analyze_actions(trajectories)
            
            # Efficiency analysis
            efficiency = self._analyze_efficiency(trajectories)
            
            # Error analysis
            error_analysis = self._analyze_errors(trajectories)
            
            # Pattern detection
            patterns = self._detect_patterns(trajectories)
            
            # File access analysis
            file_analysis = self._analyze_file_access(trajectories)
            
            # Token usage analysis
            token_analysis = self._analyze_token_usage(trajectories)
            
            # Compute overall score
            overall_score = self._compute_overall_score({
                "metrics": metrics,
                "efficiency": efficiency,
                "errors": error_analysis,
                "patterns": patterns
            })
            
            return {
                "task_id": task_id,
                "metrics": metrics,
                "action_analysis": action_analysis,
                "efficiency": efficiency,
                "error_analysis": error_analysis,
                "patterns": patterns,
                "file_analysis": file_analysis,
                "token_analysis": token_analysis,
                "overall_score": overall_score,
                "summary": self._generate_summary(trajectories)
            }
    
    def _compute_basic_metrics(
        self,
        trajectories: List[Trajectory]
    ) -> Dict[str, Any]:
        """Compute basic trajectory metrics"""
        total_actions = len(trajectories)
        successful_actions = sum(1 for t in trajectories if t.success)
        failed_actions = total_actions - successful_actions
        
        # Time metrics
        if trajectories:
            start_time = trajectories[0].timestamp
            end_time = trajectories[-1].timestamp
            total_duration = (end_time - start_time).total_seconds()
        else:
            total_duration = 0
        
        # Duration statistics
        durations = [t.duration_ms for t in trajectories if t.duration_ms]
        avg_duration = statistics.mean(durations) if durations else 0
        
        return {
            "total_actions": total_actions,
            "successful_actions": successful_actions,
            "failed_actions": failed_actions,
            "success_rate": successful_actions / total_actions if total_actions > 0 else 0,
            "total_duration_seconds": total_duration,
            "average_action_duration_ms": avg_duration,
            "actions_per_minute": (total_actions / total_duration * 60) if total_duration > 0 else 0
        }
    
    def _analyze_actions(
        self,
        trajectories: List[Trajectory]
    ) -> Dict[str, Any]:
        """Analyze action types and distribution"""
        action_counts = Counter(t.action_type for t in trajectories)
        
        # Action sequences
        action_sequence = [t.action_type for t in trajectories]
        transitions = defaultdict(Counter)
        for i in range(len(action_sequence) - 1):
            transitions[action_sequence[i]][action_sequence[i + 1]] += 1
        
        # Most common patterns
        common_patterns = []
        for length in [2, 3, 4]:
            patterns = []
            for i in range(len(action_sequence) - length + 1):
                pattern = tuple(action_sequence[i:i + length])
                patterns.append(pattern)
            
            if patterns:
                pattern_counts = Counter(patterns)
                most_common = pattern_counts.most_common(3)
                common_patterns.extend([
                    {"pattern": list(p), "count": c}
                    for p, c in most_common
                ])
        
        return {
            "action_distribution": dict(action_counts),
            "most_common_action": action_counts.most_common(1)[0] if action_counts else None,
            "action_diversity": len(action_counts) / len(trajectories) if trajectories else 0,
            "transitions": {k: dict(v) for k, v in transitions.items()},
            "common_patterns": common_patterns
        }
    
    def _analyze_efficiency(
        self,
        trajectories: List[Trajectory]
    ) -> Dict[str, Any]:
        """Analyze trajectory efficiency"""
        total_actions = len(trajectories)
        
        # Detect redundant actions (same action on same target)
        seen_actions = set()
        redundant_count = 0
        
        for t in trajectories:
            action_key = (t.action_type, t.action_target)
            if action_key in seen_actions:
                redundant_count += 1
            seen_actions.add(action_key)
        
        # Detect backtracking
        backtrack_count = 0
        file_history = []
        
        for t in trajectories:
            if t.action_type in ["read", "write"] and t.action_target:
                if t.action_target in file_history[-3:]:  # Recently visited
                    backtrack_count += 1
                file_history.append(t.action_target)
        
        # Efficiency category
        efficiency_category = "unknown"
        for indicator in self.patterns["efficiency_indicators"]:
            min_actions = indicator.get("min_actions", 0)
            max_actions = indicator.get("max_actions", float('inf'))
            
            if min_actions <= total_actions <= max_actions:
                efficiency_category = indicator["name"]
                break
        
        # Calculate efficiency score (0-100)
        base_score = 100
        redundancy_penalty = min(30, redundant_count * 5)
        backtrack_penalty = min(20, backtrack_count * 3)
        length_penalty = min(30, max(0, (total_actions - 10) * 2))
        
        efficiency_score = max(0, base_score - redundancy_penalty - backtrack_penalty - length_penalty)
        
        return {
            "efficiency_score": efficiency_score,
            "efficiency_category": efficiency_category,
            "redundant_actions": redundant_count,
            "redundancy_rate": redundant_count / total_actions if total_actions > 0 else 0,
            "backtrack_count": backtrack_count,
            "unique_action_ratio": len(seen_actions) / total_actions if total_actions > 0 else 0
        }
    
    def _analyze_errors(
        self,
        trajectories: List[Trajectory]
    ) -> Dict[str, Any]:
        """Analyze errors and recovery patterns"""
        error_trajectories = [t for t in trajectories if not t.success]
        error_count = len(error_trajectories)
        
        # Error types
        error_types = Counter(t.error_message[:50] if t.error_message else "Unknown" 
                            for t in error_trajectories)
        
        # Recovery analysis
        recovery_attempts = 0
        recovered_errors = 0
        
        for i, t in enumerate(trajectories):
            if not t.success and i < len(trajectories) - 1:
                # Check if next action is similar (recovery attempt)
                next_action = trajectories[i + 1]
                if (next_action.action_type == t.action_type and 
                    next_action.action_target == t.action_target):
                    recovery_attempts += 1
                    if next_action.success:
                        recovered_errors += 1
        
        return {
            "total_errors": error_count,
            "error_rate": error_count / len(trajectories) if trajectories else 0,
            "error_types": dict(error_types),
            "recovery_attempts": recovery_attempts,
            "recovery_success_rate": recovered_errors / recovery_attempts if recovery_attempts > 0 else 0,
            "most_common_error": error_types.most_common(1)[0] if error_types else None
        }
    
    def _detect_patterns(
        self,
        trajectories: List[Trajectory]
    ) -> Dict[str, Any]:
        """Detect behavioral patterns in trajectory"""
        detected_patterns = []
        
        # Check exploration patterns
        action_text = " ".join(t.action_type + " " + (t.action_target or "") 
                              for t in trajectories)
        
        for pattern in self.patterns["exploration_patterns"]:
            if re.search(pattern["regex"], action_text, re.IGNORECASE):
                detected_patterns.append(pattern["name"])
        
        # Detect memorization indicators
        memorization_score = 0
        
        # Check for direct navigation to solution
        if len(trajectories) < 5:
            memorization_score += 30
        
        # Check for no exploration actions
        exploration_actions = [t for t in trajectories if t.action_type == "search"]
        if len(exploration_actions) == 0:
            memorization_score += 40
        
        # Check for perfect first attempt
        first_write = next((t for t in trajectories if t.action_type == "write"), None)
        if first_write and trajectories.index(first_write) < 3:
            memorization_score += 30
        
        return {
            "detected_patterns": detected_patterns,
            "memorization_score": min(100, memorization_score),
            "exploration_breadth": len(set(t.action_target for t in trajectories if t.action_target)),
            "shows_reasoning": len(detected_patterns) > 0 and memorization_score < 50
        }
    
    def _analyze_file_access(
        self,
        trajectories: List[Trajectory]
    ) -> Dict[str, Any]:
        """Analyze file access patterns"""
        file_actions = [t for t in trajectories if t.action_target and 
                       t.action_type in ["read", "write", "search"]]
        
        accessed_files = [t.action_target for t in file_actions]
        unique_files = set(accessed_files)
        
        # File access frequency
        file_frequency = Counter(accessed_files)
        
        # Directory coverage
        directories = set()
        for file_path in unique_files:
            if "/" in file_path:
                dir_path = "/".join(file_path.split("/")[:-1])
                directories.add(dir_path)
        
        return {
            "total_files_accessed": len(unique_files),
            "file_access_count": len(accessed_files),
            "most_accessed_files": file_frequency.most_common(5),
            "directory_coverage": len(directories),
            "average_accesses_per_file": len(accessed_files) / len(unique_files) if unique_files else 0
        }
    
    def _analyze_token_usage(
        self,
        trajectories: List[Trajectory]
    ) -> Dict[str, Any]:
        """Analyze token usage patterns"""
        token_counts = [t.tokens_used for t in trajectories if t.tokens_used]
        
        if not token_counts:
            return {
                "total_tokens": 0,
                "average_tokens_per_action": 0,
                "token_efficiency": 0
            }
        
        total_tokens = sum(token_counts)
        avg_tokens = statistics.mean(token_counts)
        
        # Token efficiency (tokens per successful action)
        successful_with_tokens = [t.tokens_used for t in trajectories 
                                 if t.success and t.tokens_used]
        
        token_efficiency = (len(successful_with_tokens) / total_tokens * 1000 
                          if total_tokens > 0 else 0)
        
        return {
            "total_tokens": total_tokens,
            "average_tokens_per_action": avg_tokens,
            "max_tokens_single_action": max(token_counts),
            "min_tokens_single_action": min(token_counts),
            "token_efficiency": token_efficiency,
            "high_token_actions": [
                {"action": t.action_type, "tokens": t.tokens_used}
                for t in trajectories
                if t.tokens_used and t.tokens_used > avg_tokens * 2
            ]
        }
    
    def _compute_overall_score(
        self,
        analysis_results: Dict[str, Any]
    ) -> float:
        """
        Compute overall trajectory score (0-100).
        
        Weighted scoring based on multiple factors.
        """
        score_components = []
        
        # Efficiency score (weight: 30%)
        efficiency_score = analysis_results["efficiency"].get("efficiency_score", 50)
        score_components.append(("efficiency", efficiency_score, 0.3))
        
        # Success rate (weight: 25%)
        success_rate = analysis_results["metrics"].get("success_rate", 0.5) * 100
        score_components.append(("success_rate", success_rate, 0.25))
        
        # Error handling (weight: 15%)
        error_rate = analysis_results["errors"].get("error_rate", 0.5)
        error_score = (1 - error_rate) * 100
        score_components.append(("error_handling", error_score, 0.15))
        
        # Non-memorization (weight: 20%)
        memorization_score = analysis_results["patterns"].get("memorization_score", 50)
        non_memo_score = 100 - memorization_score
        score_components.append(("reasoning", non_memo_score, 0.2))
        
        # Speed (weight: 10%)
        actions_per_minute = analysis_results["metrics"].get("actions_per_minute", 10)
        speed_score = min(100, actions_per_minute * 5)  # Cap at 20 actions/min
        score_components.append(("speed", speed_score, 0.1))
        
        # Calculate weighted score
        overall_score = sum(score * weight for _, score, weight in score_components)
        
        return {
            "overall_score": round(overall_score, 2),
            "score_breakdown": [
                {"component": name, "score": round(score, 2), "weight": weight}
                for name, score, weight in score_components
            ]
        }
    
    def _generate_summary(
        self,
        trajectories: List[Trajectory]
    ) -> str:
        """Generate human-readable summary of trajectory"""
        if not trajectories:
            return "No trajectory data available."
        
        total_actions = len(trajectories)
        success_rate = sum(1 for t in trajectories if t.success) / total_actions
        
        action_types = Counter(t.action_type for t in trajectories)
        most_common = action_types.most_common(1)[0][0] if action_types else "unknown"
        
        summary = f"""Trajectory Summary:
- Total Actions: {total_actions}
- Success Rate: {success_rate:.1%}
- Most Common Action: {most_common}
- Unique Files Accessed: {len(set(t.action_target for t in trajectories if t.action_target))}
- Total Duration: {(trajectories[-1].timestamp - trajectories[0].timestamp).total_seconds():.1f}s
"""
        
        return summary
    
    async def compare_trajectories(
        self,
        task_id1: str,
        task_id2: str
    ) -> Dict[str, Any]:
        """
        Compare two trajectories for the same scenario.
        
        Args:
            task_id1: First task ID
            task_id2: Second task ID
            
        Returns:
            Comparison results
        """
        analysis1 = await self.analyze_trajectory(task_id1)
        analysis2 = await self.analyze_trajectory(task_id2)
        
        if "error" in analysis1 or "error" in analysis2:
            return {"error": "Failed to analyze one or both trajectories"}
        
        comparison = {
            "task_ids": [task_id1, task_id2],
            "metrics_comparison": {
                "total_actions": [
                    analysis1["metrics"]["total_actions"],
                    analysis2["metrics"]["total_actions"]
                ],
                "success_rate": [
                    analysis1["metrics"]["success_rate"],
                    analysis2["metrics"]["success_rate"]
                ],
                "duration": [
                    analysis1["metrics"]["total_duration_seconds"],
                    analysis2["metrics"]["total_duration_seconds"]
                ]
            },
            "efficiency_comparison": {
                "scores": [
                    analysis1["efficiency"]["efficiency_score"],
                    analysis2["efficiency"]["efficiency_score"]
                ],
                "redundancy": [
                    analysis1["efficiency"]["redundant_actions"],
                    analysis2["efficiency"]["redundant_actions"]
                ]
            },
            "overall_scores": [
                analysis1["overall_score"]["overall_score"],
                analysis2["overall_score"]["overall_score"]
            ],
            "winner": task_id1 if analysis1["overall_score"]["overall_score"] > 
                                 analysis2["overall_score"]["overall_score"] else task_id2
        }
        
        return comparison