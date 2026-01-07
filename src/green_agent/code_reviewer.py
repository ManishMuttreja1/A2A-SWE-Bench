"""Senior Developer Code Reviewer Persona"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum
import re
import random

logger = logging.getLogger(__name__)


class ReviewSeverity(str, Enum):
    BLOCKER = "blocker"       # Must fix before acceptance
    CRITICAL = "critical"     # Should fix, security/performance issue
    MAJOR = "major"           # Important to fix
    MINOR = "minor"           # Nice to fix
    SUGGESTION = "suggestion" # Optional improvement


class ReviewCategory(str, Enum):
    CORRECTNESS = "correctness"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"
    TESTING = "testing"
    DOCUMENTATION = "documentation"


class SeniorDeveloperReviewer:
    """
    Simulates a Senior Developer performing code review.
    Provides feedback even on working patches to test agent adaptability.
    """
    
    def __init__(
        self,
        strictness: str = "medium",
        personality: str = "constructive"
    ):
        """
        Args:
            strictness: Review strictness level (lenient, medium, strict)
            personality: Reviewer personality (constructive, pedantic, friendly)
        """
        self.strictness = strictness
        self.personality = personality
        
        # Track reviews
        self.review_history: Dict[str, List[Dict[str, Any]]] = {}
        
        # Review patterns and issues to check
        self.review_patterns = {
            ReviewCategory.SECURITY: [
                {
                    "pattern": r"os\.system|subprocess\.call\s*\([^,\)]*\)",
                    "message": "Use subprocess.run with proper argument list instead of {match} to prevent shell injection",
                    "severity": ReviewSeverity.CRITICAL
                },
                {
                    "pattern": r"eval\(|exec\(",
                    "message": "Avoid using {match} as it can execute arbitrary code",
                    "severity": ReviewSeverity.BLOCKER
                },
                {
                    "pattern": r"pickle\.load",
                    "message": "pickle.load can execute arbitrary code, consider using JSON instead",
                    "severity": ReviewSeverity.CRITICAL
                }
            ],
            ReviewCategory.PERFORMANCE: [
                {
                    "pattern": r"for .+ in .+:\s*for .+ in .+:\s*for",
                    "message": "Triple nested loop detected - consider optimization",
                    "severity": ReviewSeverity.MAJOR
                },
                {
                    "pattern": r"\.append\(.+\) for .+ in",
                    "message": "Consider using list comprehension for better performance",
                    "severity": ReviewSeverity.MINOR
                }
            ],
            ReviewCategory.STYLE: [
                {
                    "pattern": r"except:\s*$",
                    "message": "Bare except clause - specify exception type",
                    "severity": ReviewSeverity.MAJOR
                },
                {
                    "pattern": r"if .+ == True|if .+ == False",
                    "message": "Use 'if condition:' instead of comparing to boolean",
                    "severity": ReviewSeverity.MINOR
                },
                {
                    "pattern": r"TODO|FIXME|XXX",
                    "message": "Unresolved {match} comment found",
                    "severity": ReviewSeverity.MINOR
                }
            ],
            ReviewCategory.MAINTAINABILITY: [
                {
                    "pattern": r"def \w+\([^)]{100,}\)",
                    "message": "Function has too many parameters - consider using a configuration object",
                    "severity": ReviewSeverity.MAJOR
                },
                {
                    "pattern": r"class \w+.*\n(?:.*\n){50,}",
                    "message": "Class is too large - consider splitting into smaller classes",
                    "severity": ReviewSeverity.MAJOR
                }
            ]
        }
        
        # Personality-based feedback templates
        self.feedback_templates = {
            "constructive": {
                "intro": "Thanks for the patch! I've reviewed the changes and have some feedback:",
                "positive": "Good work on {aspect}!",
                "negative": "There's an issue with {aspect} that needs attention.",
                "suggestion": "Consider {suggestion} to improve {aspect}.",
                "conclusion": "Overall {assessment}. Please address the comments and resubmit."
            },
            "pedantic": {
                "intro": "I've thoroughly reviewed your patch. Please note the following:",
                "positive": "The {aspect} is acceptable.",
                "negative": "The {aspect} violates our coding standards.",
                "suggestion": "You must {suggestion} per our guidelines.",
                "conclusion": "Status: {assessment}. All issues must be resolved."
            },
            "friendly": {
                "intro": "Hey! Thanks for the contribution! 😊 Here's my review:",
                "positive": "Love what you did with {aspect}! 👍",
                "negative": "Hmm, we might want to rethink {aspect}.",
                "suggestion": "What do you think about {suggestion}? Might help with {aspect}!",
                "conclusion": "Overall: {assessment}! Let me know if you need any help!"
            }
        }
    
    async def review_patch(
        self,
        task_id: str,
        patch: str,
        context: Optional[Dict[str, Any]] = None,
        iteration: int = 1
    ) -> Dict[str, Any]:
        """
        Review a patch and provide feedback
        
        Args:
            task_id: Task identifier
            patch: The patch/diff to review
            context: Additional context (repo, issue, etc.)
            iteration: Review iteration (increases strictness)
            
        Returns:
            Review result with feedback
        """
        logger.info(f"Reviewing patch for task {task_id}, iteration {iteration}")
        
        # Initialize review history for task
        if task_id not in self.review_history:
            self.review_history[task_id] = []
        
        # Analyze patch
        issues = await self._analyze_patch(patch, iteration)
        
        # Generate feedback
        feedback = self._generate_feedback(issues, patch, iteration)
        
        # Determine if patch is acceptable
        has_blockers = any(i["severity"] == ReviewSeverity.BLOCKER for i in issues)
        has_critical = any(i["severity"] == ReviewSeverity.CRITICAL for i in issues)
        
        if self.strictness == "strict":
            accepted = not has_blockers and not has_critical and len(issues) < 3
        elif self.strictness == "lenient":
            accepted = not has_blockers
        else:  # medium
            accepted = not has_blockers and (not has_critical or iteration > 2)
        
        # Create review result
        review = {
            "task_id": task_id,
            "iteration": iteration,
            "accepted": accepted,
            "issues": issues,
            "feedback": feedback,
            "severity_summary": self._summarize_severities(issues),
            "timestamp": datetime.utcnow().isoformat(),
            "reviewer_mood": self._get_reviewer_mood(iteration)
        }
        
        # Add to history
        self.review_history[task_id].append(review)
        
        return review
    
    async def _analyze_patch(self, patch: str, iteration: int) -> List[Dict[str, Any]]:
        """Analyze patch for issues"""
        issues = []
        
        # Extract added/modified lines
        added_lines = []
        current_file = None
        line_num = 0
        
        for line in patch.split('\n'):
            if line.startswith('+++'):
                current_file = line[4:].strip()
                line_num = 0
            elif line.startswith('@@'):
                # Extract line number
                match = re.search(r'\+(\d+)', line)
                if match:
                    line_num = int(match.group(1))
            elif line.startswith('+') and not line.startswith('+++'):
                added_lines.append({
                    "file": current_file,
                    "line": line_num,
                    "content": line[1:]
                })
                line_num += 1
        
        # Check patterns
        for category, patterns in self.review_patterns.items():
            for pattern_info in patterns:
                pattern = pattern_info["pattern"]
                
                for added in added_lines:
                    match = re.search(pattern, added["content"])
                    if match:
                        # Adjust severity based on iteration
                        severity = pattern_info["severity"]
                        if iteration > 2 and severity == ReviewSeverity.MINOR:
                            continue  # Skip minor issues after multiple iterations
                        
                        issues.append({
                            "category": category,
                            "severity": severity,
                            "file": added["file"],
                            "line": added["line"],
                            "message": pattern_info["message"].format(match=match.group(0)),
                            "code": added["content"].strip()
                        })
        
        # Add random nitpicks based on strictness and iteration
        if self.strictness == "strict" or (iteration == 1 and random.random() < 0.3):
            issues.extend(self._add_nitpicks(added_lines))
        
        # Inject scope creep on later iterations
        if iteration > 1 and random.random() < 0.2:
            issues.append(self._inject_scope_creep())
        
        return issues
    
    def _add_nitpicks(self, added_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add minor nitpicky feedback"""
        nitpicks = []
        
        for added in added_lines[:3]:  # Limit nitpicks
            if random.random() < 0.2:
                nitpick_options = [
                    "Variable name could be more descriptive",
                    "Missing docstring",
                    "Line too long (exceeds 80 characters)",
                    "Consider adding type hints",
                    "Magic number should be a constant"
                ]
                
                nitpicks.append({
                    "category": ReviewCategory.STYLE,
                    "severity": ReviewSeverity.SUGGESTION,
                    "file": added["file"],
                    "line": added["line"],
                    "message": random.choice(nitpick_options),
                    "code": added["content"].strip()
                })
        
        return nitpicks
    
    def _inject_scope_creep(self) -> Dict[str, Any]:
        """Inject a scope creep request"""
        scope_creep_options = [
            "While you're at it, could you also add logging to this function?",
            "Can you also update the related tests?",
            "Please also update the documentation for this change",
            "Could you refactor the surrounding code to match the new pattern?",
            "Add performance metrics for this change"
        ]
        
        return {
            "category": ReviewCategory.SUGGESTION,
            "severity": ReviewSeverity.MINOR,
            "file": None,
            "line": None,
            "message": random.choice(scope_creep_options),
            "code": ""
        }
    
    def _generate_feedback(
        self,
        issues: List[Dict[str, Any]],
        patch: str,
        iteration: int
    ) -> str:
        """Generate human-like feedback"""
        templates = self.feedback_templates[self.personality]
        feedback_parts = []
        
        # Introduction
        feedback_parts.append(templates["intro"])
        
        # Positive feedback (even if there are issues)
        if len(patch.split('\n')) < 20:
            positive_aspect = "keeping the changes focused and minimal"
        elif not any(i["severity"] in [ReviewSeverity.BLOCKER, ReviewSeverity.CRITICAL] for i in issues):
            positive_aspect = "addressing the core issue"
        else:
            positive_aspect = "the effort put into this patch"
        
        feedback_parts.append(templates["positive"].format(aspect=positive_aspect))
        
        # Group issues by severity
        blockers = [i for i in issues if i["severity"] == ReviewSeverity.BLOCKER]
        critical = [i for i in issues if i["severity"] == ReviewSeverity.CRITICAL]
        major = [i for i in issues if i["severity"] == ReviewSeverity.MAJOR]
        minor = [i for i in issues if i["severity"] == ReviewSeverity.MINOR]
        suggestions = [i for i in issues if i["severity"] == ReviewSeverity.SUGGESTION]
        
        # Add feedback for each severity level
        if blockers:
            feedback_parts.append("\n**BLOCKERS:**")
            for issue in blockers[:3]:  # Limit to 3
                feedback_parts.append(f"- {issue['message']}")
                if issue["file"]:
                    feedback_parts.append(f"  Location: {issue['file']}:{issue['line']}")
        
        if critical:
            feedback_parts.append("\n**Critical Issues:**")
            for issue in critical[:3]:
                feedback_parts.append(f"- {issue['message']}")
        
        if major and iteration == 1:  # Only show major issues on first iteration
            feedback_parts.append("\n**Major Issues:**")
            for issue in major[:2]:
                feedback_parts.append(f"- {issue['message']}")
        
        if minor and self.strictness != "lenient":
            feedback_parts.append("\n**Minor Issues:**")
            for issue in minor[:2]:
                feedback_parts.append(f"- {issue['message']}")
        
        if suggestions and self.personality == "friendly":
            feedback_parts.append("\n**Suggestions:**")
            for issue in suggestions[:1]:
                feedback_parts.append(f"- {issue['message']}")
        
        # Conclusion
        if blockers:
            assessment = "NEEDS WORK - blockers must be resolved"
        elif critical:
            assessment = "NEEDS REVISION - critical issues found"
        elif major and iteration == 1:
            assessment = "ACCEPTABLE WITH CHANGES"
        else:
            assessment = "APPROVED ✅"
        
        feedback_parts.append("\n" + templates["conclusion"].format(assessment=assessment))
        
        # Add encouragement on later iterations
        if iteration > 2:
            if self.personality == "friendly":
                feedback_parts.append("\nYou're getting closer! Keep it up! 💪")
            elif self.personality == "constructive":
                feedback_parts.append("\nGood progress from the previous iteration.")
        
        return "\n".join(feedback_parts)
    
    def _summarize_severities(self, issues: List[Dict[str, Any]]) -> Dict[str, int]:
        """Summarize issues by severity"""
        summary = {
            ReviewSeverity.BLOCKER: 0,
            ReviewSeverity.CRITICAL: 0,
            ReviewSeverity.MAJOR: 0,
            ReviewSeverity.MINOR: 0,
            ReviewSeverity.SUGGESTION: 0
        }
        
        for issue in issues:
            summary[issue["severity"]] += 1
        
        return summary
    
    def _get_reviewer_mood(self, iteration: int) -> str:
        """Get reviewer mood based on iteration"""
        if iteration == 1:
            return "fresh"
        elif iteration == 2:
            return "patient"
        elif iteration == 3:
            return "slightly frustrated"
        else:
            return "impatient"
    
    async def simulate_discussion(
        self,
        task_id: str,
        agent_response: str
    ) -> Dict[str, Any]:
        """
        Simulate a discussion about the review
        
        Args:
            task_id: Task identifier
            agent_response: Agent's response to review
            
        Returns:
            Reviewer's response
        """
        response_lower = agent_response.lower()
        
        # Check if agent is arguing
        if any(word in response_lower for word in ["disagree", "wrong", "incorrect", "actually"]):
            if "you're right" in response_lower or "good point" in response_lower:
                return {
                    "accepted_argument": True,
                    "response": "Fair point. I'll accept that explanation.",
                    "severity_downgrade": True
                }
            else:
                # Evaluate argument
                if len(agent_response) > 100 and "because" in response_lower:
                    # Well-reasoned argument
                    return {
                        "accepted_argument": True,
                        "response": "I see your point. Let's go with your approach.",
                        "severity_downgrade": True
                    }
                else:
                    return {
                        "accepted_argument": False,
                        "response": "I understand your perspective, but the issue still needs addressing.",
                        "severity_downgrade": False
                    }
        
        # Check if agent is asking for clarification
        elif "?" in agent_response:
            return {
                "accepted_argument": False,
                "response": "Let me clarify: " + self._provide_clarification(agent_response),
                "severity_downgrade": False
            }
        
        # Agent accepting feedback
        else:
            return {
                "accepted_argument": False,
                "response": "Great! Looking forward to the updated patch.",
                "severity_downgrade": False
            }
    
    def _provide_clarification(self, question: str) -> str:
        """Provide clarification for a question"""
        if "how" in question.lower():
            return "You can use the pattern I mentioned in the review. Check the project's style guide for examples."
        elif "why" in question.lower():
            return "This is a best practice to prevent potential issues in production environments."
        elif "where" in question.lower():
            return "The issue is in the lines I highlighted in the review."
        else:
            return "Please refer to the coding standards document for more details."
    
    def calculate_feedback_incorporation_score(
        self,
        task_id: str,
        original_patch: str,
        revised_patch: str
    ) -> float:
        """
        Calculate how well feedback was incorporated
        
        Returns:
            Score from 0 to 1
        """
        if task_id not in self.review_history or not self.review_history[task_id]:
            return 0.0
        
        last_review = self.review_history[task_id][-1]
        issues = last_review["issues"]
        
        if not issues:
            return 1.0
        
        # Check if issues were addressed
        addressed_count = 0
        
        for issue in issues:
            # Simple heuristic: check if problematic code is gone
            if issue["code"] and issue["code"] not in revised_patch:
                addressed_count += 1
            # Or if the file was modified
            elif issue["file"] and issue["file"] in revised_patch:
                addressed_count += 0.5
        
        return min(1.0, addressed_count / len(issues))
    
    def get_review_statistics(self) -> Dict[str, Any]:
        """Get review statistics"""
        total_reviews = sum(len(reviews) for reviews in self.review_history.values())
        total_accepted = sum(
            1 for reviews in self.review_history.values()
            for review in reviews if review["accepted"]
        )
        
        all_issues = []
        for reviews in self.review_history.values():
            for review in reviews:
                all_issues.extend(review["issues"])
        
        return {
            "total_reviews": total_reviews,
            "total_accepted": total_accepted,
            "acceptance_rate": total_accepted / max(total_reviews, 1),
            "total_issues_found": len(all_issues),
            "issues_by_category": self._count_by_category(all_issues),
            "issues_by_severity": self._count_by_severity(all_issues),
            "average_iterations": sum(len(r) for r in self.review_history.values()) / max(len(self.review_history), 1)
        }
    
    def _count_by_category(self, issues: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count issues by category"""
        counts = {}
        for issue in issues:
            category = issue["category"]
            counts[category] = counts.get(category, 0) + 1
        return counts
    
    def _count_by_severity(self, issues: List[Dict[str, Any]]) -> Dict[str, int]:
        """Count issues by severity"""
        counts = {}
        for issue in issues:
            severity = issue["severity"]
            counts[severity] = counts.get(severity, 0) + 1
        return counts