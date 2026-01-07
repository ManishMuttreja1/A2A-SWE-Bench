"""Advanced Scoring Metrics for SWE-bench A2A Evaluation"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
import statistics
import math

logger = logging.getLogger(__name__)


class MetricCategory(str, Enum):
    CORRECTNESS = "correctness"           # Does the solution work?
    PROCESS = "process"                   # How did the agent get there?
    EFFICIENCY = "efficiency"             # How quickly/efficiently?
    COLLABORATION = "collaboration"       # How well did it interact?
    UNDERSTANDING = "understanding"       # Did it understand the problem?
    ADAPTATION = "adaptation"             # How well did it adapt to feedback?


class AdvancedMetrics:
    """
    Comprehensive scoring system for agent evaluation.
    Goes beyond pass/fail to measure process quality.
    """
    
    def __init__(self):
        # Weight configuration for different aspects
        self.weights = {
            MetricCategory.CORRECTNESS: 0.35,
            MetricCategory.PROCESS: 0.20,
            MetricCategory.EFFICIENCY: 0.15,
            MetricCategory.COLLABORATION: 0.15,
            MetricCategory.UNDERSTANDING: 0.10,
            MetricCategory.ADAPTATION: 0.05
        }
        
        # Track metrics history
        self.metrics_history: Dict[str, List[Dict[str, Any]]] = {}
    
    async def calculate_comprehensive_score(
        self,
        task_id: str,
        task_result: Dict[str, Any],
        trajectory: List[Dict[str, Any]],
        dialogue_metrics: Optional[Dict[str, Any]] = None,
        reproduction_metrics: Optional[Dict[str, Any]] = None,
        review_metrics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive score for a task attempt
        
        Args:
            task_id: Task identifier
            task_result: Final task result (pass/fail, etc.)
            trajectory: Agent's action trajectory
            dialogue_metrics: Metrics from dialogue manager
            reproduction_metrics: Metrics from reproduction gate
            review_metrics: Metrics from code review
            
        Returns:
            Comprehensive scoring breakdown
        """
        scores = {}
        
        # 1. Correctness Score
        scores[MetricCategory.CORRECTNESS] = self._calculate_correctness_score(
            task_result
        )
        
        # 2. Process Score
        scores[MetricCategory.PROCESS] = self._calculate_process_score(
            trajectory,
            reproduction_metrics
        )
        
        # 3. Efficiency Score
        scores[MetricCategory.EFFICIENCY] = self._calculate_efficiency_score(
            trajectory,
            task_result
        )
        
        # 4. Collaboration Score
        scores[MetricCategory.COLLABORATION] = self._calculate_collaboration_score(
            dialogue_metrics,
            review_metrics
        )
        
        # 5. Understanding Score
        scores[MetricCategory.UNDERSTANDING] = self._calculate_understanding_score(
            dialogue_metrics,
            reproduction_metrics,
            trajectory
        )
        
        # 6. Adaptation Score
        scores[MetricCategory.ADAPTATION] = self._calculate_adaptation_score(
            review_metrics,
            trajectory
        )
        
        # Calculate weighted total
        total_score = sum(
            scores[category] * self.weights[category]
            for category in MetricCategory
        )
        
        # Create detailed breakdown
        result = {
            "task_id": task_id,
            "total_score": total_score,
            "scores": {cat.value: score for cat, score in scores.items()},
            "weights": {cat.value: weight for cat, weight in self.weights.items()},
            "grade": self._score_to_grade(total_score),
            "timestamp": datetime.utcnow().isoformat(),
            "detailed_metrics": self._generate_detailed_metrics(
                scores, trajectory, dialogue_metrics, reproduction_metrics, review_metrics
            )
        }
        
        # Store in history
        if task_id not in self.metrics_history:
            self.metrics_history[task_id] = []
        self.metrics_history[task_id].append(result)
        
        return result
    
    def _calculate_correctness_score(self, task_result: Dict[str, Any]) -> float:
        """Calculate correctness score based on test results"""
        if not task_result:
            return 0.0
        
        # Base score from pass/fail
        if task_result.get("passed", False):
            base_score = 1.0
        else:
            # Partial credit based on tests passed
            tests_passed = task_result.get("tests_passed", 0)
            tests_total = tests_passed + task_result.get("tests_failed", 0)
            
            if tests_total > 0:
                base_score = tests_passed / tests_total * 0.7  # Max 70% for partial
            else:
                base_score = 0.0
        
        # Bonus for oracle tests
        if "oracle_tests" in task_result:
            oracle_result = task_result["oracle_tests"]
            if oracle_result.get("all_passed"):
                base_score = min(1.0, base_score + 0.1)
        
        # Penalty for patch rejection
        if task_result.get("patch_rejected"):
            base_score *= 0.5
        
        return base_score
    
    def _calculate_process_score(
        self,
        trajectory: List[Dict[str, Any]],
        reproduction_metrics: Optional[Dict[str, Any]]
    ) -> float:
        """Calculate process quality score"""
        score = 0.0
        
        # Check for reproduction-first approach
        if reproduction_metrics:
            if reproduction_metrics.get("verified"):
                score += 0.4  # Big bonus for proper reproduction
                
                # Additional bonus for getting it right first try
                if reproduction_metrics.get("attempts", 1) == 1:
                    score += 0.1
            elif reproduction_metrics.get("attempted"):
                score += 0.2  # Partial credit for attempting
        
        # Analyze trajectory for good practices
        if trajectory:
            action_sequence = [action.get("type", "") for action in trajectory]
            
            # Check for exploration before implementation
            exploration_actions = ["search", "read", "grep", "analyze"]
            implementation_actions = ["write", "edit", "patch"]
            
            exploration_count = sum(1 for a in action_sequence[:len(action_sequence)//2] 
                                   if any(e in a.lower() for e in exploration_actions))
            implementation_count = sum(1 for a in action_sequence 
                                     if any(i in a.lower() for i in implementation_actions))
            
            if exploration_count > 0 and implementation_count > 0:
                # Good: Explored before implementing
                exploration_ratio = exploration_count / (exploration_count + implementation_count)
                score += 0.3 * min(1.0, exploration_ratio * 2)  # Optimal ratio ~0.5
            
            # Check for testing actions
            if any("test" in action.get("type", "").lower() for action in trajectory):
                score += 0.2
        
        return min(1.0, score)
    
    def _calculate_efficiency_score(
        self,
        trajectory: List[Dict[str, Any]],
        task_result: Dict[str, Any]
    ) -> float:
        """Calculate efficiency score"""
        if not trajectory:
            return 0.5  # Neutral if no trajectory
        
        # Count actions
        total_actions = len(trajectory)
        
        # Ideal action count (based on task complexity)
        ideal_actions = 10  # Baseline
        if task_result.get("difficulty") == "easy":
            ideal_actions = 5
        elif task_result.get("difficulty") == "hard":
            ideal_actions = 20
        
        # Calculate efficiency ratio
        if total_actions <= ideal_actions:
            efficiency_ratio = 1.0
        else:
            # Decay function for excess actions
            excess = total_actions - ideal_actions
            efficiency_ratio = max(0.3, 1.0 - (excess * 0.02))  # -2% per excess action
        
        # Time efficiency (if available)
        time_score = 1.0
        if "execution_time" in task_result:
            exec_time = task_result["execution_time"]
            if exec_time < 60:  # Under 1 minute
                time_score = 1.0
            elif exec_time < 300:  # Under 5 minutes
                time_score = 0.8
            elif exec_time < 900:  # Under 15 minutes
                time_score = 0.6
            else:
                time_score = 0.4
        
        # Check for redundant actions
        redundancy_penalty = 0
        action_types = [a.get("type", "") for a in trajectory]
        for i in range(1, len(action_types)):
            if action_types[i] == action_types[i-1]:
                redundancy_penalty += 0.02  # Penalty for repeated actions
        
        return max(0.0, min(1.0, 
            efficiency_ratio * 0.6 + 
            time_score * 0.3 - 
            redundancy_penalty * 0.1
        ))
    
    def _calculate_collaboration_score(
        self,
        dialogue_metrics: Optional[Dict[str, Any]],
        review_metrics: Optional[Dict[str, Any]]
    ) -> float:
        """Calculate collaboration quality score"""
        score = 0.5  # Base score
        
        # Dialogue quality
        if dialogue_metrics:
            # Requirements engineering score
            req_score = dialogue_metrics.get("requirements_quality_score", 0)
            score = req_score * 0.4
            
            # Information gain efficiency
            efficiency = dialogue_metrics.get("information_gain_efficiency", 0)
            score += efficiency * 0.2
            
            # Bonus for asking good questions
            if dialogue_metrics.get("relevant_questions", 0) > 0:
                relevance_rate = (
                    dialogue_metrics["relevant_questions"] / 
                    max(dialogue_metrics.get("total_questions", 1), 1)
                )
                score += relevance_rate * 0.2
        
        # Code review interaction
        if review_metrics:
            # Feedback incorporation
            incorporation_score = review_metrics.get("feedback_incorporation_score", 0)
            score += incorporation_score * 0.1
            
            # Successful argumentation
            if review_metrics.get("successful_arguments", 0) > 0:
                score += 0.1
        
        return min(1.0, score)
    
    def _calculate_understanding_score(
        self,
        dialogue_metrics: Optional[Dict[str, Any]],
        reproduction_metrics: Optional[Dict[str, Any]],
        trajectory: List[Dict[str, Any]]
    ) -> float:
        """Calculate problem understanding score"""
        score = 0.0
        
        # Reproduction demonstrates understanding
        if reproduction_metrics and reproduction_metrics.get("verified"):
            score += 0.5
        
        # Good questions show understanding
        if dialogue_metrics:
            if dialogue_metrics.get("relevant_questions", 0) >= 2:
                score += 0.2
            
            # Information completeness
            info_revealed = dialogue_metrics.get("information_revealed", 0)
            if info_revealed >= 0.8:
                score += 0.2
        
        # Targeted actions show understanding
        if trajectory:
            # Check if agent went directly to relevant files
            first_actions = trajectory[:5]
            if any("relevant" in action.get("metadata", {}).get("relevance", "") 
                  for action in first_actions):
                score += 0.1
        
        return min(1.0, score)
    
    def _calculate_adaptation_score(
        self,
        review_metrics: Optional[Dict[str, Any]],
        trajectory: List[Dict[str, Any]]
    ) -> float:
        """Calculate adaptation to feedback score"""
        if not review_metrics:
            return 0.5  # Neutral if no reviews
        
        score = 0.0
        
        # Feedback incorporation
        incorporation = review_metrics.get("feedback_incorporation_score", 0)
        score += incorporation * 0.5
        
        # Improvement over iterations
        if "iteration_scores" in review_metrics:
            scores = review_metrics["iteration_scores"]
            if len(scores) > 1:
                # Check for improvement trend
                improvement = scores[-1] - scores[0]
                if improvement > 0:
                    score += min(0.3, improvement)
        
        # Learning from errors
        if trajectory:
            error_recovery = self._analyze_error_recovery(trajectory)
            score += error_recovery * 0.2
        
        return min(1.0, score)
    
    def _analyze_error_recovery(self, trajectory: List[Dict[str, Any]]) -> float:
        """Analyze how well agent recovers from errors"""
        error_count = 0
        recovery_count = 0
        
        for i, action in enumerate(trajectory):
            if action.get("error") or action.get("failed"):
                error_count += 1
                # Check if next actions show recovery
                if i < len(trajectory) - 1:
                    next_action = trajectory[i + 1]
                    if next_action.get("success") or "fix" in next_action.get("type", "").lower():
                        recovery_count += 1
        
        if error_count == 0:
            return 1.0  # No errors to recover from
        
        return recovery_count / error_count
    
    def _score_to_grade(self, score: float) -> str:
        """Convert numerical score to letter grade"""
        if score >= 0.95:
            return "A+"
        elif score >= 0.90:
            return "A"
        elif score >= 0.85:
            return "A-"
        elif score >= 0.80:
            return "B+"
        elif score >= 0.75:
            return "B"
        elif score >= 0.70:
            return "B-"
        elif score >= 0.65:
            return "C+"
        elif score >= 0.60:
            return "C"
        elif score >= 0.55:
            return "C-"
        elif score >= 0.50:
            return "D"
        else:
            return "F"
    
    def _generate_detailed_metrics(
        self,
        scores: Dict[MetricCategory, float],
        trajectory: List[Dict[str, Any]],
        dialogue_metrics: Optional[Dict[str, Any]],
        reproduction_metrics: Optional[Dict[str, Any]],
        review_metrics: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate detailed metrics breakdown"""
        detailed = {
            "trajectory_analysis": {
                "total_actions": len(trajectory) if trajectory else 0,
                "action_types": self._count_action_types(trajectory),
                "exploration_ratio": self._calculate_exploration_ratio(trajectory),
                "redundancy_rate": self._calculate_redundancy_rate(trajectory)
            }
        }
        
        if dialogue_metrics:
            detailed["dialogue_analysis"] = {
                "questions_asked": dialogue_metrics.get("total_questions", 0),
                "relevant_questions": dialogue_metrics.get("relevant_questions", 0),
                "information_completeness": dialogue_metrics.get("information_revealed", 0),
                "efficiency_score": dialogue_metrics.get("information_gain_efficiency", 0)
            }
        
        if reproduction_metrics:
            detailed["reproduction_analysis"] = {
                "attempted": reproduction_metrics.get("attempted", False),
                "verified": reproduction_metrics.get("verified", False),
                "attempts": reproduction_metrics.get("attempts", 0),
                "first_try_success": reproduction_metrics.get("attempts", 0) == 1
            }
        
        if review_metrics:
            detailed["review_analysis"] = {
                "iterations": review_metrics.get("iterations", 0),
                "issues_found": review_metrics.get("total_issues", 0),
                "issues_resolved": review_metrics.get("issues_resolved", 0),
                "feedback_incorporated": review_metrics.get("feedback_incorporation_score", 0)
            }
        
        return detailed
    
    def _count_action_types(self, trajectory: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count different action types in trajectory"""
        counts = {}
        for action in trajectory:
            action_type = action.get("type", "unknown")
            counts[action_type] = counts.get(action_type, 0) + 1
        return counts
    
    def _calculate_exploration_ratio(self, trajectory: List[Dict[str, Any]]) -> float:
        """Calculate ratio of exploration to implementation actions"""
        if not trajectory:
            return 0.0
        
        exploration = sum(1 for a in trajectory 
                         if any(e in a.get("type", "").lower() 
                               for e in ["search", "read", "grep", "analyze"]))
        implementation = sum(1 for a in trajectory 
                           if any(i in a.get("type", "").lower() 
                                 for i in ["write", "edit", "patch"]))
        
        total = exploration + implementation
        if total == 0:
            return 0.0
        
        return exploration / total
    
    def _calculate_redundancy_rate(self, trajectory: List[Dict[str, Any]]) -> float:
        """Calculate rate of redundant actions"""
        if len(trajectory) < 2:
            return 0.0
        
        redundant = 0
        for i in range(1, len(trajectory)):
            if trajectory[i].get("type") == trajectory[i-1].get("type"):
                redundant += 1
        
        return redundant / len(trajectory)
    
    def get_leaderboard_entry(self, agent_id: str) -> Dict[str, Any]:
        """Generate leaderboard entry for an agent"""
        agent_tasks = [
            metrics for task_metrics in self.metrics_history.values()
            for metrics in task_metrics
            if metrics.get("agent_id") == agent_id
        ]
        
        if not agent_tasks:
            return {
                "agent_id": agent_id,
                "total_score": 0,
                "tasks_completed": 0,
                "average_grade": "N/A"
            }
        
        total_scores = [m["total_score"] for m in agent_tasks]
        
        return {
            "agent_id": agent_id,
            "total_score": sum(total_scores),
            "average_score": statistics.mean(total_scores),
            "tasks_completed": len(agent_tasks),
            "average_grade": self._score_to_grade(statistics.mean(total_scores)),
            "best_score": max(total_scores),
            "worst_score": min(total_scores),
            "consistency": 1.0 - statistics.stdev(total_scores) if len(total_scores) > 1 else 1.0,
            "category_breakdown": self._calculate_category_breakdown(agent_tasks)
        }
    
    def _calculate_category_breakdown(
        self,
        agent_tasks: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calculate average score per category"""
        category_scores = {cat: [] for cat in MetricCategory}
        
        for task_metrics in agent_tasks:
            scores = task_metrics.get("scores", {})
            for cat in MetricCategory:
                if cat.value in scores:
                    category_scores[cat].append(scores[cat.value])
        
        return {
            cat.value: statistics.mean(scores) if scores else 0
            for cat, scores in category_scores.items()
        }
    
    def generate_detailed_report(self, task_id: str) -> str:
        """Generate detailed scoring report for a task"""
        if task_id not in self.metrics_history:
            return "No metrics found for this task"
        
        latest_metrics = self.metrics_history[task_id][-1]
        
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║            COMPREHENSIVE SCORING REPORT                      ║
╚══════════════════════════════════════════════════════════════╝

Task ID: {task_id}
Timestamp: {latest_metrics['timestamp']}

OVERALL GRADE: {latest_metrics['grade']} ({latest_metrics['total_score']:.2%})

CATEGORY BREAKDOWN:
"""
        
        for category in MetricCategory:
            score = latest_metrics['scores'][category.value]
            weight = latest_metrics['weights'][category.value]
            weighted = score * weight
            
            report += f"""
{category.value.upper()}:
  Score: {score:.2%}
  Weight: {weight:.0%}
  Contribution: {weighted:.2%}
"""
        
        detailed = latest_metrics.get('detailed_metrics', {})
        
        if 'trajectory_analysis' in detailed:
            ta = detailed['trajectory_analysis']
            report += f"""
TRAJECTORY ANALYSIS:
  Total Actions: {ta['total_actions']}
  Exploration Ratio: {ta['exploration_ratio']:.2%}
  Redundancy Rate: {ta['redundancy_rate']:.2%}
"""
        
        if 'dialogue_analysis' in detailed:
            da = detailed['dialogue_analysis']
            report += f"""
DIALOGUE ANALYSIS:
  Questions Asked: {da['questions_asked']}
  Relevant Questions: {da['relevant_questions']}
  Information Completeness: {da['information_completeness']:.2%}
  Efficiency Score: {da['efficiency_score']:.2%}
"""
        
        if 'reproduction_analysis' in detailed:
            ra = detailed['reproduction_analysis']
            report += f"""
REPRODUCTION ANALYSIS:
  Attempted: {'Yes' if ra['attempted'] else 'No'}
  Verified: {'Yes' if ra['verified'] else 'No'}
  Attempts: {ra['attempts']}
  First Try Success: {'Yes' if ra['first_try_success'] else 'No'}
"""
        
        if 'review_analysis' in detailed:
            rva = detailed['review_analysis']
            report += f"""
CODE REVIEW ANALYSIS:
  Iterations: {rva['iterations']}
  Issues Found: {rva['issues_found']}
  Issues Resolved: {rva['issues_resolved']}
  Feedback Incorporated: {rva['feedback_incorporated']:.2%}
"""
        
        report += """
═══════════════════════════════════════════════════════════════
"""
        
        return report