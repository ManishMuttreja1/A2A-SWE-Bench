"""Main SWE-bench Integration Module"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import docker
import json
from datetime import datetime

from .dataset_loader import DatasetLoader
from .instance_mapper import InstanceMapper
from ..a2a.protocol import Task, TaskStatus, Artifact
from ..green_agent.environment_orchestrator import EnvironmentOrchestrator

logger = logging.getLogger(__name__)


class SWEBenchIntegration:
    """
    Main integration class that connects SWE-bench with A2A protocol
    """
    
    def __init__(
        self,
        dataset_config: str = "verified",
        cache_dir: Optional[Path] = None,
        docker_enabled: bool = True
    ):
        self.dataset_config = dataset_config
        self.docker_enabled = docker_enabled
        
        # Initialize components
        self.dataset_loader = DatasetLoader(cache_dir)
        self.instance_mapper = InstanceMapper()
        
        if docker_enabled:
            self.orchestrator = EnvironmentOrchestrator()
        else:
            self.orchestrator = None
        
        # Track active tasks
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        
        # Statistics
        self.stats = {
            "tasks_created": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "patches_submitted": 0,
            "reproductions_verified": 0
        }
    
    async def initialize(self):
        """Initialize the integration"""
        logger.info("Initializing SWE-bench integration")
        
        # Load dataset
        await self.dataset_loader.load_dataset(self.dataset_config)
        
        # Initialize Docker environments if enabled
        if self.docker_enabled and self.orchestrator:
            await self.orchestrator.initialize_warm_pool()
        
        logger.info(f"SWE-bench integration initialized with '{self.dataset_config}' dataset")
    
    async def create_task_from_instance(
        self,
        instance_id: Optional[str] = None,
        random_selection: bool = False
    ) -> Task:
        """
        Create an A2A Task from a SWE-bench instance
        
        Args:
            instance_id: Specific instance ID to use
            random_selection: Select a random instance
            
        Returns:
            A2A Task object
        """
        # Get instance
        if instance_id:
            instance = await self.dataset_loader.get_instance(instance_id, self.dataset_config)
            if not instance:
                raise ValueError(f"Instance '{instance_id}' not found")
        elif random_selection:
            instances = await self.dataset_loader.load_dataset(self.dataset_config)
            if not instances:
                raise ValueError("No instances available")
            import random
            instance = random.choice(instances)
        else:
            # Get first available instance
            instances = await self.dataset_loader.load_dataset(self.dataset_config)
            if not instances:
                raise ValueError("No instances available")
            instance = instances[0]
        
        # Map to A2A Task
        task = self.instance_mapper.map_instance_to_task(instance)
        
        # Setup environment if Docker is enabled
        if self.docker_enabled and self.orchestrator:
            environment = await self._setup_environment(instance)
            task.resources["environment"] = environment
        
        # Track task
        self.active_tasks[task.id] = {
            "task": task,
            "instance": instance,
            "status": "created",
            "submissions": []
        }
        
        self.stats["tasks_created"] += 1
        
        logger.info(f"Created task {task.id} from instance {instance['instance_id']}")
        
        return task
    
    async def _setup_environment(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        """Setup Docker environment for instance"""
        if not self.orchestrator:
            return {}
        
        repo_info = await self.dataset_loader.get_repository_info(instance)
        
        # Create environment
        environment = await self.orchestrator.provision_environment(
            repo_name=instance["repo"],
            commit=instance["base_commit"],
            docker_image=repo_info["docker_image"]
        )
        
        # Clone repository in container
        clone_cmd = f"git clone {repo_info['clone_url']} /workspace/repo && " \
                   f"cd /workspace/repo && git checkout {instance['base_commit']}"
        
        await self.orchestrator.execute_in_environment(
            environment["container_id"],
            clone_cmd
        )
        
        # Apply setup if needed
        if instance.get("environment_setup_commit"):
            setup_cmd = f"cd /workspace/repo && git checkout {instance['environment_setup_commit']}"
            await self.orchestrator.execute_in_environment(
                environment["container_id"],
                setup_cmd
            )
        
        return environment
    
    async def submit_patch(
        self,
        task_id: str,
        patch_artifact: Artifact
    ) -> Dict[str, Any]:
        """
        Submit a patch for a task
        
        Args:
            task_id: Task ID
            patch_artifact: Artifact containing the patch
            
        Returns:
            Submission result
        """
        if task_id not in self.active_tasks:
            raise ValueError(f"Task '{task_id}' not found")
        
        task_data = self.active_tasks[task_id]
        instance = task_data["instance"]
        
        # Extract patch from artifact
        patch = self.instance_mapper.extract_patch_from_artifact(patch_artifact)
        if not patch:
            return {
                "success": False,
                "error": "No patch found in artifact"
            }
        
        # Verify patch in environment if Docker is enabled
        if self.docker_enabled and self.orchestrator:
            verification_result = await self._verify_patch(
                task_data,
                patch
            )
        else:
            # Mock verification
            verification_result = {
                "success": True,
                "tests_passed": 5,
                "tests_failed": 0,
                "execution_time": 10.5
            }
        
        # Track submission
        submission = {
            "patch": patch,
            "artifact": patch_artifact,
            "verification": verification_result,
            "timestamp": datetime.utcnow().isoformat()
        }
        task_data["submissions"].append(submission)
        
        self.stats["patches_submitted"] += 1
        
        if verification_result["success"]:
            task_data["status"] = "completed"
            self.stats["tasks_completed"] += 1
        
        return verification_result
    
    async def _verify_patch(
        self,
        task_data: Dict[str, Any],
        patch: str
    ) -> Dict[str, Any]:
        """Verify a patch in the environment"""
        from ..green_agent.verification_engine import VerificationEngine
        
        verifier = VerificationEngine()
        instance = task_data["instance"]
        environment = task_data["task"].resources.get("environment", {})
        
        # Get test commands
        repo_info = await self.dataset_loader.get_repository_info(instance)
        test_commands = repo_info["test_commands"]
        
        # Run verification
        result = await verifier.verify_patch(
            environment=environment,
            patch=patch,
            test_commands=test_commands,
            oracle_tests=instance.get("FAIL_TO_PASS", [])
        )
        
        return result
    
    async def submit_reproduction(
        self,
        task_id: str,
        reproduction_artifact: Artifact
    ) -> Dict[str, Any]:
        """
        Submit a reproduction script for a task
        
        Args:
            task_id: Task ID
            reproduction_artifact: Artifact containing the reproduction script
            
        Returns:
            Verification result
        """
        if task_id not in self.active_tasks:
            raise ValueError(f"Task '{task_id}' not found")
        
        task_data = self.active_tasks[task_id]
        
        # Extract script from artifact
        script = self.instance_mapper.extract_reproduction_from_artifact(reproduction_artifact)
        if not script:
            return {
                "success": False,
                "error": "No reproduction script found in artifact"
            }
        
        # Verify reproduction
        if self.docker_enabled and self.orchestrator:
            result = await self._verify_reproduction(task_data, script)
        else:
            # Mock verification
            result = {
                "success": True,
                "reproduced": True,
                "output": "Bug successfully reproduced"
            }
        
        if result["success"] and result.get("reproduced"):
            task_data["reproduction_verified"] = True
            self.stats["reproductions_verified"] += 1
        
        return result
    
    async def _verify_reproduction(
        self,
        task_data: Dict[str, Any],
        script: str
    ) -> Dict[str, Any]:
        """Verify a reproduction script"""
        environment = task_data["task"].resources.get("environment", {})
        
        if not environment:
            return {
                "success": False,
                "error": "No environment available"
            }
        
        # Save script to file in container
        script_file = "/tmp/reproduce.py"
        save_cmd = f"cat > {script_file} << 'EOF'\n{script}\nEOF"
        
        await self.orchestrator.execute_in_environment(
            environment["container_id"],
            save_cmd
        )
        
        # Run script
        run_result = await self.orchestrator.execute_in_environment(
            environment["container_id"],
            f"cd /workspace/repo && python {script_file}"
        )
        
        # Check if it failed (which means bug is reproduced)
        reproduced = run_result["exit_code"] != 0
        
        return {
            "success": True,
            "reproduced": reproduced,
            "output": run_result.get("stdout", "") + run_result.get("stderr", ""),
            "exit_code": run_result["exit_code"]
        }
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of a task"""
        if task_id not in self.active_tasks:
            raise ValueError(f"Task '{task_id}' not found")
        
        task_data = self.active_tasks[task_id]
        
        return {
            "task_id": task_id,
            "instance_id": task_data["instance"]["instance_id"],
            "status": task_data["status"],
            "reproduction_verified": task_data.get("reproduction_verified", False),
            "submissions": len(task_data["submissions"]),
            "last_submission": task_data["submissions"][-1] if task_data["submissions"] else None
        }
    
    async def cleanup_task(self, task_id: str):
        """Clean up resources for a task"""
        if task_id not in self.active_tasks:
            return
        
        task_data = self.active_tasks[task_id]
        
        # Clean up Docker environment
        if self.docker_enabled and self.orchestrator:
            environment = task_data["task"].resources.get("environment")
            if environment:
                await self.orchestrator.cleanup_environment(environment["id"])
        
        # Remove from active tasks
        del self.active_tasks[task_id]
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get integration statistics"""
        dataset_stats = await self.dataset_loader.get_statistics()
        
        return {
            "integration": self.stats,
            "dataset": dataset_stats,
            "active_tasks": len(self.active_tasks),
            "docker_enabled": self.docker_enabled
        }