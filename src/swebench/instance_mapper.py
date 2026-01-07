"""Instance Mapper - Maps SWE-bench instances to A2A Tasks"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import json

from ..a2a.protocol import Task, TaskRequest, Artifact, Part, PartType, A2AProtocol

logger = logging.getLogger(__name__)


class InstanceMapper:
    """
    Maps SWE-bench instances to A2A protocol Tasks
    """
    
    def __init__(self):
        self.mapping_cache: Dict[str, Task] = {}
    
    def map_instance_to_task(self, instance: Dict[str, Any]) -> Task:
        """
        Convert a SWE-bench instance to an A2A Task
        
        Args:
            instance: SWE-bench instance dict
            
        Returns:
            A2A Task object
        """
        instance_id = instance["instance_id"]
        
        # Check cache
        if instance_id in self.mapping_cache:
            return self.mapping_cache[instance_id]
        
        # Create task request
        task_request = TaskRequest(
            title=f"Fix issue: {instance_id}",
            description=instance["problem_statement"],
            resources={
                "repository": {
                    "name": instance["repo"],
                    "commit": instance["base_commit"],
                    "url": f"https://github.com/{instance['repo']}",
                    "setup_commit": instance.get("environment_setup_commit")
                },
                "tests": {
                    "fail_to_pass": instance.get("FAIL_TO_PASS", []),
                    "pass_to_pass": instance.get("PASS_TO_PASS", [])
                },
                "docker_image": self._get_docker_image(instance["repo"])
            },
            constraints={
                "time_limit": 1800,  # 30 minutes
                "memory_limit": "4GB",
                "language": "python",
                "version": instance.get("version", "3.9")
            },
            metadata={
                "instance_id": instance_id,
                "created_at": instance.get("created_at"),
                "hints": instance.get("hints_text", ""),
                "difficulty": self._estimate_difficulty(instance),
                "oracle_patch": instance.get("patch", ""),
                "oracle_test_patch": instance.get("test_patch", "")
            }
        )
        
        # Create task
        task = A2AProtocol.create_task(task_request)
        
        # Add to cache
        self.mapping_cache[instance_id] = task
        
        return task
    
    def map_task_to_instance(self, task: Task) -> Dict[str, Any]:
        """
        Convert an A2A Task back to SWE-bench instance format
        
        Args:
            task: A2A Task object
            
        Returns:
            SWE-bench instance dict
        """
        metadata = task.metadata or {}
        resources = task.resources or {}
        
        instance = {
            "instance_id": metadata.get("instance_id", task.id),
            "repo": resources.get("repository", {}).get("name", ""),
            "base_commit": resources.get("repository", {}).get("commit", ""),
            "problem_statement": task.description,
            "hints_text": metadata.get("hints", ""),
            "created_at": metadata.get("created_at", task.created_at.isoformat()),
            "patch": metadata.get("oracle_patch", ""),
            "test_patch": metadata.get("oracle_test_patch", ""),
            "version": task.constraints.get("version", "3.9") if task.constraints else "3.9",
            "FAIL_TO_PASS": resources.get("tests", {}).get("fail_to_pass", []),
            "PASS_TO_PASS": resources.get("tests", {}).get("pass_to_pass", []),
            "environment_setup_commit": resources.get("repository", {}).get("setup_commit", "")
        }
        
        return instance
    
    def create_patch_artifact(self, patch_content: str, commit_message: str = "") -> Artifact:
        """
        Create an Artifact for a patch submission
        
        Args:
            patch_content: Git diff content
            commit_message: Optional commit message
            
        Returns:
            A2A Artifact containing the patch
        """
        parts = []
        
        # Add patch as file diff part
        parts.append(Part(
            type=PartType.FILE_DIFF,
            content=patch_content,
            metadata={
                "format": "git-diff",
                "applied": False
            }
        ))
        
        # Add commit message if provided
        if commit_message:
            parts.append(Part(
                type=PartType.TEXT,
                content=commit_message,
                metadata={"type": "commit_message"}
            ))
        
        artifact = A2AProtocol.create_artifact(
            parts=parts,
            metadata={
                "type": "patch_submission",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        return artifact
    
    def create_reproduction_artifact(self, script: str, expected_failure: bool = True) -> Artifact:
        """
        Create an Artifact for a reproduction script
        
        Args:
            script: Python script that reproduces the issue
            expected_failure: Whether script should fail (True) or pass (False)
            
        Returns:
            A2A Artifact containing the reproduction script
        """
        parts = [
            Part(
                type=PartType.CODE,
                content=script,
                metadata={
                    "language": "python",
                    "purpose": "reproduction",
                    "expected_failure": expected_failure
                }
            )
        ]
        
        artifact = A2AProtocol.create_artifact(
            parts=parts,
            metadata={
                "type": "reproduction_script",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        return artifact
    
    def extract_patch_from_artifact(self, artifact: Artifact) -> Optional[str]:
        """
        Extract patch content from an Artifact
        
        Args:
            artifact: A2A Artifact
            
        Returns:
            Patch content or None
        """
        for part in artifact.parts:
            if part.type == PartType.FILE_DIFF:
                return part.content
        
        return None
    
    def extract_reproduction_from_artifact(self, artifact: Artifact) -> Optional[str]:
        """
        Extract reproduction script from an Artifact
        
        Args:
            artifact: A2A Artifact
            
        Returns:
            Script content or None
        """
        for part in artifact.parts:
            if part.type == PartType.CODE and \
               part.metadata and part.metadata.get("purpose") == "reproduction":
                return part.content
        
        return None
    
    def _get_docker_image(self, repo_name: str) -> str:
        """Get Docker image for repository"""
        repo_images = {
            "django/django": "swebench/django:latest",
            "scikit-learn/scikit-learn": "swebench/scikit-learn:latest",
            "flask/flask": "swebench/flask:latest",
            "sympy/sympy": "swebench/sympy:latest",
            "requests/requests": "swebench/requests:latest",
            "pytest-dev/pytest": "swebench/pytest:latest",
        }
        
        return repo_images.get(repo_name, "python:3.9-slim")
    
    def _estimate_difficulty(self, instance: Dict[str, Any]) -> str:
        """Estimate difficulty of instance"""
        # Simple heuristic based on patch size and test count
        patch = instance.get("patch", "")
        patch_lines = len(patch.split('\n'))
        test_count = len(instance.get("FAIL_TO_PASS", []))
        
        if patch_lines < 20 and test_count <= 2:
            return "easy"
        elif patch_lines < 50 and test_count <= 5:
            return "medium"
        else:
            return "hard"
    
    def create_test_result_artifact(
        self,
        test_results: Dict[str, Any],
        execution_time: float
    ) -> Artifact:
        """
        Create an Artifact for test results
        
        Args:
            test_results: Test execution results
            execution_time: Time taken to run tests
            
        Returns:
            A2A Artifact containing test results
        """
        parts = [
            Part(
                type=PartType.JSON,
                content=json.dumps(test_results, indent=2),
                metadata={
                    "type": "test_results",
                    "execution_time": execution_time
                }
            )
        ]
        
        # Add test output if available
        if "output" in test_results:
            parts.append(Part(
                type=PartType.TEXT,
                content=test_results["output"],
                metadata={"type": "test_output"}
            ))
        
        artifact = A2AProtocol.create_artifact(
            parts=parts,
            metadata={
                "type": "test_results",
                "timestamp": datetime.utcnow().isoformat(),
                "passed": test_results.get("passed", False),
                "tests_passed": test_results.get("tests_passed", 0),
                "tests_failed": test_results.get("tests_failed", 0)
            }
        )
        
        return artifact