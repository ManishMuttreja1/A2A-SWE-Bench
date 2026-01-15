"""Integration between fresh-issue harvester and anti-contamination pipeline"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from .config import EvaluationSlice, TaskMetadata

logger = logging.getLogger(__name__)


class FreshIssueIntegration:
    """
    Integrates the GitHub harvester with anti-contamination tracking.
    
    Fresh issues provide "secret-in-time" tasks that cannot have been
    memorized by models trained before the issue was created.
    """
    
    def __init__(self, max_age_hours: int = 24):
        self.max_age_hours = max_age_hours
        self.harvested_issues: Dict[str, Dict[str, Any]] = {}
        
    def register_harvested_issue(
        self,
        instance_id: str,
        issue_data: Dict[str, Any],
        harvested_at: Optional[datetime] = None,
    ) -> TaskMetadata:
        """
        Register a freshly harvested issue for tracking.
        
        Args:
            instance_id: Unique identifier for the issue
            issue_data: Issue data from harvester
            harvested_at: When the issue was harvested
            
        Returns:
            TaskMetadata configured for fresh slice
        """
        harvested_at = harvested_at or datetime.utcnow()
        
        self.harvested_issues[instance_id] = {
            "issue_data": issue_data,
            "harvested_at": harvested_at,
            "github_url": issue_data.get("html_url"),
            "created_at": issue_data.get("created_at"),
        }
        
        return TaskMetadata(
            evaluation_slice=EvaluationSlice.FRESH,
            run_mode="llm_only",  # Fresh issues should be LLM-only
            heuristics_allowed=False,
            harvested_at=harvested_at,
            base_commit=issue_data.get("base_commit"),
        )
    
    def is_fresh(self, instance_id: str) -> bool:
        """Check if an instance is a fresh harvested issue"""
        if instance_id not in self.harvested_issues:
            return False
        
        harvested = self.harvested_issues[instance_id]["harvested_at"]
        age = datetime.utcnow() - harvested
        return age < timedelta(hours=self.max_age_hours)
    
    def get_fresh_instances(self) -> List[str]:
        """Get list of currently fresh instance IDs"""
        return [
            iid for iid in self.harvested_issues
            if self.is_fresh(iid)
        ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get harvester integration statistics"""
        now = datetime.utcnow()
        fresh_count = sum(1 for iid in self.harvested_issues if self.is_fresh(iid))
        
        return {
            "total_harvested": len(self.harvested_issues),
            "currently_fresh": fresh_count,
            "expired": len(self.harvested_issues) - fresh_count,
            "max_age_hours": self.max_age_hours,
        }


def convert_harvested_to_scenario(
    issue: Dict[str, Any],
    pr: Dict[str, Any],
    owner: str,
    repo: str,
) -> Dict[str, Any]:
    """
    Convert harvested issue + PR into SWE-bench compatible scenario format.
    
    Args:
        issue: GitHub issue data
        pr: Associated pull request data
        owner: Repository owner
        repo: Repository name
        
    Returns:
        Scenario dict compatible with SWE-bench
    """
    instance_id = f"{owner}__{repo}-{issue['number']}"
    
    # Get base commit from PR
    base_commit = pr.get("base", {}).get("sha", "")
    
    # Build problem statement
    problem_statement = f"{issue['title']}\n\n{issue.get('body', '')}"
    
    # Extract patch from PR files
    patch_lines = []
    for file_info in pr.get("files", []):
        if file_info.get("patch"):
            patch_lines.append(f"--- a/{file_info['filename']}")
            patch_lines.append(f"+++ b/{file_info['filename']}")
            patch_lines.append(file_info["patch"])
    
    return {
        "instance_id": instance_id,
        "repo": f"{owner}/{repo}",
        "repo_url": f"https://github.com/{owner}/{repo}",
        "base_commit": base_commit,
        "problem_statement": problem_statement,
        "patch": "\n".join(patch_lines),
        "test_commands": [],  # Would need to be determined per-repo
        "is_fresh": True,
        "source": "harvested",
        "harvested_at": datetime.utcnow().isoformat(),
        "github_issue_url": issue.get("html_url"),
        "github_pr_url": pr.get("html_url"),
        "created_at": issue.get("created_at"),
        "closed_at": issue.get("closed_at"),
    }
