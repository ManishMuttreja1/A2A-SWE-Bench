"""GitHub Harvester for collecting fresh issues"""

import asyncio
import httpx
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import os
import json

from ..database import get_session, Scenario
from .issue_classifier import IssueClassifier
from .scenario_converter import ScenarioConverter

logger = logging.getLogger(__name__)


class GitHubHarvester:
    """
    Harvests fresh issues from GitHub repositories.
    Identifies suitable candidates for SWE-bench scenarios.
    """
    
    def __init__(
        self,
        github_token: Optional[str] = None,
        max_age_hours: int = 24,
        min_stars: int = 100
    ):
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.max_age_hours = max_age_hours
        self.min_stars = min_stars
        
        # Initialize components
        self.classifier = IssueClassifier()
        self.converter = ScenarioConverter()
        
        # HTTP client
        self.client = httpx.AsyncClient(
            headers={
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {self.github_token}" if self.github_token else None
            },
            timeout=30.0
        )
        
        # Tracked repositories
        self.repositories = self._get_tracked_repositories()
        
        # Statistics
        self.stats = {
            "issues_fetched": 0,
            "issues_classified": 0,
            "scenarios_created": 0,
            "errors": 0
        }
    
    def _get_tracked_repositories(self) -> List[Dict[str, Any]]:
        """Get list of repositories to track"""
        return [
            {"owner": "django", "repo": "django", "language": "python"},
            {"owner": "scikit-learn", "repo": "scikit-learn", "language": "python"},
            {"owner": "flask", "repo": "flask", "language": "python"},
            {"owner": "pandas-dev", "repo": "pandas", "language": "python"},
            {"owner": "numpy", "repo": "numpy", "language": "python"},
            {"owner": "pytest-dev", "repo": "pytest", "language": "python"},
            {"owner": "requests", "repo": "requests", "language": "python"},
            {"owner": "matplotlib", "repo": "matplotlib", "language": "python"},
            {"owner": "sympy", "repo": "sympy", "language": "python"},
            {"owner": "astropy", "repo": "astropy", "language": "python"},
        ]
    
    async def harvest_all(self) -> List[Dict[str, Any]]:
        """
        Harvest fresh issues from all tracked repositories.
        
        Returns:
            List of created scenarios
        """
        all_scenarios = []
        
        for repo_info in self.repositories:
            try:
                scenarios = await self.harvest_repository(
                    repo_info["owner"],
                    repo_info["repo"]
                )
                all_scenarios.extend(scenarios)
                
            except Exception as e:
                logger.error(f"Failed to harvest {repo_info['owner']}/{repo_info['repo']}: {e}")
                self.stats["errors"] += 1
        
        logger.info(f"Harvested {len(all_scenarios)} total scenarios")
        return all_scenarios
    
    async def harvest_repository(
        self,
        owner: str,
        repo: str
    ) -> List[Dict[str, Any]]:
        """
        Harvest fresh issues from a specific repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            List of created scenarios
        """
        logger.info(f"Harvesting issues from {owner}/{repo}")
        
        # Fetch recent closed issues with pull requests
        issues = await self._fetch_recent_issues(owner, repo)
        self.stats["issues_fetched"] += len(issues)
        
        scenarios = []
        
        for issue in issues:
            try:
                # Check if issue is suitable
                if not await self._is_suitable_issue(issue):
                    continue
                
                # Classify the issue
                classification = await self.classifier.classify_issue(issue)
                self.stats["issues_classified"] += 1
                
                if not classification["suitable"]:
                    continue
                
                # Get associated pull request
                pr = await self._get_associated_pr(owner, repo, issue)
                
                if not pr:
                    continue
                
                # Convert to scenario
                scenario = await self.converter.convert_to_scenario(
                    issue,
                    pr,
                    owner,
                    repo,
                    classification
                )
                
                if scenario:
                    # Save scenario to database
                    await self._save_scenario(scenario)
                    scenarios.append(scenario)
                    self.stats["scenarios_created"] += 1
                    
                    logger.info(f"Created scenario from issue #{issue['number']}")
                
            except Exception as e:
                logger.error(f"Failed to process issue #{issue['number']}: {e}")
                self.stats["errors"] += 1
        
        return scenarios
    
    async def _fetch_recent_issues(
        self,
        owner: str,
        repo: str
    ) -> List[Dict[str, Any]]:
        """Fetch recent closed issues from GitHub"""
        since = datetime.utcnow() - timedelta(hours=self.max_age_hours)
        
        url = f"https://api.github.com/repos/{owner}/{repo}/issues"
        params = {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "since": since.isoformat(),
            "per_page": 100
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            issues = response.json()
            
            # Filter to only issues (not PRs) closed recently
            recent_issues = []
            for issue in issues:
                if "pull_request" not in issue:
                    closed_at = datetime.fromisoformat(issue["closed_at"].replace("Z", "+00:00"))
                    if (datetime.utcnow() - closed_at.replace(tzinfo=None)).total_seconds() < self.max_age_hours * 3600:
                        recent_issues.append(issue)
            
            return recent_issues
            
        except Exception as e:
            logger.error(f"Failed to fetch issues: {e}")
            return []
    
    async def _is_suitable_issue(self, issue: Dict[str, Any]) -> bool:
        """Check if an issue is suitable for SWE-bench"""
        # Must have labels
        if not issue.get("labels"):
            return False
        
        # Check for bug or feature labels
        label_names = [label["name"].lower() for label in issue["labels"]]
        
        suitable_labels = ["bug", "bugfix", "fix", "feature", "enhancement", "improvement"]
        if not any(label in label_name for label in suitable_labels for label_name in label_names):
            return False
        
        # Must have meaningful description
        if not issue.get("body") or len(issue["body"]) < 50:
            return False
        
        # Should not be a documentation-only issue
        doc_keywords = ["docs", "documentation", "readme", "typo"]
        if any(keyword in issue["title"].lower() for keyword in doc_keywords):
            return False
        
        return True
    
    async def _get_associated_pr(
        self,
        owner: str,
        repo: str,
        issue: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get pull request that fixes the issue"""
        issue_number = issue["number"]
        
        # Search for PRs that reference this issue
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        params = {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": 100
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            prs = response.json()
            
            for pr in prs:
                # Check if PR references the issue
                if pr.get("body"):
                    # Look for issue references like #123, fixes #123, closes #123
                    import re
                    patterns = [
                        f"#{ issue_number}\\b",
                        f"fixes #{ issue_number}\\b",
                        f"closes #{ issue_number}\\b",
                        f"resolves #{ issue_number}\\b"
                    ]
                    
                    for pattern in patterns:
                        if re.search(pattern, pr["body"], re.IGNORECASE):
                            # Get PR details including diff
                            pr_details = await self._get_pr_details(owner, repo, pr["number"])
                            return pr_details
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get associated PR: {e}")
            return None
    
    async def _get_pr_details(
        self,
        owner: str,
        repo: str,
        pr_number: int
    ) -> Optional[Dict[str, Any]]:
        """Get detailed PR information including diff"""
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        
        try:
            # Get PR metadata
            response = await self.client.get(url)
            response.raise_for_status()
            pr = response.json()
            
            # Get PR files/diff
            files_url = f"{url}/files"
            files_response = await self.client.get(files_url)
            files_response.raise_for_status()
            pr["files"] = files_response.json()
            
            # Get PR commits
            commits_url = f"{url}/commits"
            commits_response = await self.client.get(commits_url)
            commits_response.raise_for_status()
            pr["commits"] = commits_response.json()
            
            return pr
            
        except Exception as e:
            logger.error(f"Failed to get PR details: {e}")
            return None
    
    async def _save_scenario(self, scenario: Dict[str, Any]):
        """Save scenario to database"""
        try:
            with get_session() as session:
                # Check if scenario already exists
                existing = session.query(Scenario).filter_by(
                    instance_id=scenario["instance_id"]
                ).first()
                
                if existing:
                    logger.info(f"Scenario {scenario['instance_id']} already exists")
                    return
                
                # Create new scenario
                db_scenario = Scenario(
                    instance_id=scenario["instance_id"],
                    repo=scenario["repo"],
                    base_commit=scenario["base_commit"],
                    problem_statement=scenario["problem_statement"],
                    difficulty=scenario.get("difficulty", "medium"),
                    category=scenario.get("category", "bug_fix"),
                    is_fresh=True,
                    source="harvested",
                    harvested_at=datetime.utcnow(),
                    github_issue_url=scenario.get("github_issue_url")
                )
                
                session.add(db_scenario)
                session.commit()
                
                logger.info(f"Saved scenario {scenario['instance_id']} to database")
                
        except Exception as e:
            logger.error(f"Failed to save scenario: {e}")
    
    async def run_continuous(
        self,
        interval_minutes: int = 60
    ):
        """
        Run harvester continuously.
        
        Args:
            interval_minutes: Minutes between harvest runs
        """
        logger.info(f"Starting continuous harvester (interval: {interval_minutes} minutes)")
        
        while True:
            try:
                # Run harvest
                scenarios = await self.harvest_all()
                
                # Log statistics
                logger.info(f"Harvest complete: {self.stats}")
                
                # Reset statistics
                self.stats = {
                    "issues_fetched": 0,
                    "issues_classified": 0,
                    "scenarios_created": 0,
                    "errors": 0
                }
                
                # Wait for next run
                await asyncio.sleep(interval_minutes * 60)
                
            except Exception as e:
                logger.error(f"Harvester error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    def get_stats(self) -> Dict[str, Any]:
        """Get harvester statistics"""
        return {
            **self.stats,
            "tracked_repositories": len(self.repositories),
            "max_age_hours": self.max_age_hours
        }
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()