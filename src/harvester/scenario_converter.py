"""Convert GitHub issues to SWE-bench scenarios"""

import re
import json
import hashlib
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ScenarioConverter:
    """
    Converts GitHub issues and PRs to SWE-bench scenarios.
    """
    
    def __init__(self):
        self.test_extractors = self._load_test_extractors()
    
    def _load_test_extractors(self) -> Dict[str, Any]:
        """Load test extraction patterns"""
        return {
            "pytest_patterns": [
                re.compile(r"pytest\s+([\w/\.]+)"),
                re.compile(r"python\s+-m\s+pytest\s+([\w/\.]+)"),
                re.compile(r"def\s+test_(\w+)"),
            ],
            "unittest_patterns": [
                re.compile(r"python\s+(test_\w+\.py)"),
                re.compile(r"python\s+-m\s+unittest\s+([\w\.]+)"),
                re.compile(r"class\s+Test(\w+)"),
            ],
            "test_file_patterns": [
                re.compile(r"(test_\w+\.py)"),
                re.compile(r"(\w+_test\.py)"),
                re.compile(r"tests?/([\w/]+\.py)"),
            ]
        }
    
    async def convert_to_scenario(
        self,
        issue: Dict[str, Any],
        pr: Dict[str, Any],
        owner: str,
        repo: str,
        classification: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Convert GitHub issue and PR to SWE-bench scenario.
        
        Args:
            issue: GitHub issue data
            pr: Pull request data
            owner: Repository owner
            repo: Repository name
            classification: Issue classification result
            
        Returns:
            SWE-bench scenario or None if conversion fails
        """
        try:
            # Generate unique instance ID
            instance_id = self._generate_instance_id(owner, repo, issue["number"])
            
            # Extract problem statement
            problem_statement = self._create_problem_statement(issue)
            
            # Get base commit (commit before PR merge)
            base_commit = self._get_base_commit(pr)
            
            if not base_commit:
                logger.warning(f"Could not determine base commit for issue #{issue['number']}")
                return None
            
            # Extract test information
            test_info = self._extract_test_info(pr)
            
            # Extract patch
            patch = self._extract_patch(pr)
            
            if not patch:
                logger.warning(f"Could not extract patch for issue #{issue['number']}")
                return None
            
            # Create scenario
            scenario = {
                "instance_id": instance_id,
                "repo": f"{owner}/{repo}",
                "base_commit": base_commit,
                "problem_statement": problem_statement,
                "hints_text": "",  # No hints for harvested issues
                
                # Test information
                "test_commands": test_info.get("commands", []),
                "oracle_tests": test_info.get("oracle_tests", []),
                "test_patch": test_info.get("test_patch", ""),
                
                # Patch information
                "patch": patch,
                "patch_files": self._get_patch_files(pr),
                
                # Metadata
                "created_at": datetime.utcnow().isoformat(),
                "version": "1.0",
                "source": "harvested",
                "github_issue_url": issue["html_url"],
                "github_pr_url": pr["html_url"],
                
                # Classification
                "category": classification.get("category", "unknown"),
                "difficulty": classification.get("difficulty", "medium"),
                "tags": classification.get("tags", []),
                
                # Statistics
                "issue_created_at": issue["created_at"],
                "issue_closed_at": issue["closed_at"],
                "pr_merged_at": pr.get("merged_at"),
                "files_changed": len(pr.get("files", [])),
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0)
            }
            
            # Validate scenario
            if self._validate_scenario(scenario):
                return scenario
            else:
                logger.warning(f"Scenario validation failed for issue #{issue['number']}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to convert issue #{issue['number']}: {e}")
            return None
    
    def _generate_instance_id(
        self,
        owner: str,
        repo: str,
        issue_number: int
    ) -> str:
        """Generate unique instance ID"""
        # Format: owner__repo-issue_number-timestamp_hash
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        hash_input = f"{owner}/{repo}#{issue_number}#{timestamp}"
        hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        
        return f"{owner}__{repo}-{issue_number}-{hash_suffix}"
    
    def _create_problem_statement(
        self,
        issue: Dict[str, Any]
    ) -> str:
        """Create problem statement from issue"""
        title = issue.get("title", "")
        body = issue.get("body", "")
        
        # Clean up body
        body = self._clean_markdown(body)
        
        # Combine title and body
        problem_statement = f"# {title}\n\n{body}"
        
        # Add issue metadata
        problem_statement += f"\n\n---\n"
        problem_statement += f"Issue #{issue['number']} reported by @{issue['user']['login']}\n"
        
        # Add labels
        if issue.get("labels"):
            labels = [label["name"] for label in issue["labels"]]
            problem_statement += f"Labels: {', '.join(labels)}\n"
        
        return problem_statement
    
    def _clean_markdown(self, text: str) -> str:
        """Clean up markdown text"""
        if not text:
            return ""
        
        # Remove images
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        
        # Remove HTML comments
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        
        # Limit code block size
        def limit_code_block(match):
            code = match.group(0)
            lines = code.split("\n")
            if len(lines) > 50:
                return "\n".join(lines[:25] + ["... (truncated) ..."] + lines[-25:])
            return code
        
        text = re.sub(r"```.*?```", limit_code_block, text, flags=re.DOTALL)
        
        # Limit total length
        if len(text) > 5000:
            text = text[:5000] + "\n... (truncated)"
        
        return text.strip()
    
    def _get_base_commit(self, pr: Dict[str, Any]) -> Optional[str]:
        """Get base commit for the PR"""
        # Get the parent of the first commit in the PR
        if pr.get("commits") and len(pr["commits"]) > 0:
            first_commit = pr["commits"][0]
            
            # The parent of the first commit is our base
            if first_commit.get("parents") and len(first_commit["parents"]) > 0:
                return first_commit["parents"][0]["sha"]
        
        # Fallback to base branch SHA
        if pr.get("base") and pr["base"].get("sha"):
            return pr["base"]["sha"]
        
        return None
    
    def _extract_test_info(self, pr: Dict[str, Any]) -> Dict[str, Any]:
        """Extract test information from PR"""
        test_info = {
            "commands": [],
            "oracle_tests": [],
            "test_patch": ""
        }
        
        # Look for test files in PR files
        test_files = []
        
        for file in pr.get("files", []):
            filename = file.get("filename", "")
            
            # Check if it's a test file
            for pattern in self.test_extractors["test_file_patterns"]:
                if pattern.search(filename):
                    test_files.append(filename)
                    break
        
        # Extract test commands from PR body
        pr_body = pr.get("body", "")
        
        # Look for pytest commands
        for pattern in self.test_extractors["pytest_patterns"]:
            matches = pattern.findall(pr_body)
            for match in matches:
                test_info["commands"].append(f"pytest {match}")
        
        # Look for unittest commands
        for pattern in self.test_extractors["unittest_patterns"]:
            matches = pattern.findall(pr_body)
            for match in matches:
                test_info["commands"].append(f"python -m unittest {match}")
        
        # If no commands found, create default ones for test files
        if not test_info["commands"] and test_files:
            for test_file in test_files:
                if test_file.endswith(".py"):
                    test_info["commands"].append(f"pytest {test_file}")
                    test_info["oracle_tests"].append(test_file)
        
        # Extract test patch from test file changes
        test_patches = []
        for file in pr.get("files", []):
            if file.get("filename") in test_files and file.get("patch"):
                test_patches.append(file["patch"])
        
        test_info["test_patch"] = "\n".join(test_patches)
        
        return test_info
    
    def _extract_patch(self, pr: Dict[str, Any]) -> Optional[str]:
        """Extract patch from PR"""
        patches = []
        
        for file in pr.get("files", []):
            if file.get("patch"):
                # Create unified diff format
                filename = file.get("filename", "unknown")
                patch = f"--- a/{filename}\n+++ b/{filename}\n{file['patch']}"
                patches.append(patch)
        
        if patches:
            return "\n".join(patches)
        
        return None
    
    def _get_patch_files(self, pr: Dict[str, Any]) -> List[str]:
        """Get list of files modified in PR"""
        files = []
        
        for file in pr.get("files", []):
            filename = file.get("filename")
            if filename:
                files.append(filename)
        
        return files
    
    def _validate_scenario(self, scenario: Dict[str, Any]) -> bool:
        """Validate scenario has required fields"""
        required_fields = [
            "instance_id",
            "repo",
            "base_commit",
            "problem_statement",
            "patch"
        ]
        
        for field in required_fields:
            if not scenario.get(field):
                logger.warning(f"Scenario missing required field: {field}")
                return False
        
        # Check patch is not too small or too large
        patch_lines = scenario["patch"].split("\n")
        if len(patch_lines) < 3:
            logger.warning("Patch too small")
            return False
        
        if len(patch_lines) > 1000:
            logger.warning("Patch too large")
            return False
        
        # Check problem statement is meaningful
        if len(scenario["problem_statement"]) < 50:
            logger.warning("Problem statement too short")
            return False
        
        return True
    
    def export_scenario(
        self,
        scenario: Dict[str, Any],
        format: str = "json"
    ) -> str:
        """
        Export scenario in different formats.
        
        Args:
            scenario: Scenario data
            format: Export format (json, yaml)
            
        Returns:
            Exported scenario string
        """
        if format == "json":
            return json.dumps(scenario, indent=2, default=str)
        
        elif format == "yaml":
            # Simple YAML export
            lines = []
            for key, value in scenario.items():
                if isinstance(value, (list, dict)):
                    lines.append(f"{key}: {json.dumps(value)}")
                elif isinstance(value, str) and "\n" in value:
                    lines.append(f"{key}: |")
                    for line in value.split("\n"):
                        lines.append(f"  {line}")
                else:
                    lines.append(f"{key}: {value}")
            
            return "\n".join(lines)
        
        else:
            raise ValueError(f"Unsupported format: {format}")