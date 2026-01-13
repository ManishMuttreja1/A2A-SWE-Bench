"""Environment Orchestrator for dynamic container management"""

import asyncio
import logging
import docker
from typing import Dict, Any, Optional, List
import uuid
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class EnvironmentOrchestrator:
    """
    Manages Docker environments for SWE-bench evaluation.
    Features JIT provisioning and warm pool management.
    """
    
    def __init__(
        self,
        docker_socket: str = "unix://var/run/docker.sock",
        warm_pool_size: int = 5,
        base_image: str = "python:3.10-slim"  # Use 3.10 for compatibility with older Django versions
    ):
        self.docker_client = docker.from_env()
        self.warm_pool_size = warm_pool_size
        self.base_image = base_image
        
        # Track environments
        self.active_environments: Dict[str, Dict[str, Any]] = {}
        self.warm_pool: List[str] = []
        
        # Container configuration
        self.container_config = {
            "detach": True,
            "tty": True,
            "stdin_open": True,
            "working_dir": "/workspace",
            "mem_limit": "4g",
            "cpu_quota": 100000,  # Limit CPU usage
            "network_mode": "bridge",
            "labels": {
                "swe-bench": "true",
                "orchestrator": "green-agent"
            }
        }
    
    async def initialize_warm_pool(self):
        """Initialize a pool of warm containers"""
        logger.info(f"Initializing warm pool with {self.warm_pool_size} containers")
        
        for _ in range(self.warm_pool_size):
            try:
                container = await self._create_base_container()
                if container:
                    self.warm_pool.append(container.id)
            except Exception as e:
                logger.error(f"Error creating warm container: {e}")
    
    async def _create_base_container(self) -> Optional[Any]:
        """Create a base container for the warm pool"""
        try:
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            container = await loop.run_in_executor(
                None,
                lambda: self.docker_client.containers.run(
                    self.base_image,
                    "sleep infinity",
                    **self.container_config
                )
            )
            
            # Install basic dependencies
            await self._setup_base_environment(container)
            
            return container
            
        except Exception as e:
            logger.error(f"Error creating base container: {e}")
            return None
    
    async def _setup_base_environment(self, container):
        """Setup basic environment in container"""
        commands = [
            "apt-get update",
            "apt-get install -y git curl build-essential",
            "pip install --upgrade pip",
            # Include pytest-django so Django test suites initialize apps/settings correctly.
            "pip install pytest pytest-cov coverage pytest-django"
        ]
        
        for cmd in commands:
            try:
                result = container.exec_run(["/bin/sh", "-c", cmd])
                if result.exit_code != 0:
                    logger.warning(f"Command failed: {cmd}")
            except Exception as e:
                logger.error(f"Error executing setup command: {e}")
    
    async def provision_environment(
        self,
        repo_url: str,
        commit_hash: str,
        instance_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Provision an environment for evaluation.
        
        Args:
            repo_url: Repository URL
            commit_hash: Specific commit to checkout
            instance_id: SWE-bench instance ID
            
        Returns:
            Environment dict with container info
        """
        env_id = str(uuid.uuid4())
        logger.info(f"Provisioning environment {env_id} for {instance_id}")
        
        try:
            # Get container from warm pool or create new
            container = await self._get_container()
            
            if not container:
                raise RuntimeError("Failed to get container")
            
            # Clone repository and checkout commit
            await self._setup_repository(container, repo_url, commit_hash)
            
            # Store environment info
            environment = {
                "id": env_id,
                "container_id": container.id,
                "container_name": container.name,
                "repo_url": repo_url,
                "commit_hash": commit_hash,
                "instance_id": instance_id,
                "status": "ready",
                "access_type": "docker",
                "connection_info": {
                    "type": "docker_exec",
                    "container_id": container.id
                }
            }
            
            self.active_environments[env_id] = environment
            
            return environment
            
        except Exception as e:
            logger.error(f"Error provisioning environment: {e}")
            try:
                if 'container' in locals() and container:
                    container.stop(timeout=5)
                    container.remove()
            except Exception:
                pass
            return None
    
    async def _get_container(self) -> Optional[Any]:
        """Get a container from warm pool or create new"""
        if self.warm_pool:
            container_id = self.warm_pool.pop(0)
            try:
                container = self.docker_client.containers.get(container_id)
                
                # Replenish warm pool asynchronously
                asyncio.create_task(self._replenish_warm_pool())
                
                return container
            except Exception as e:
                logger.warning(f"Failed to get warm container: {e}")
        
        # Create new container if warm pool is empty
        return await self._create_base_container()
    
    async def _replenish_warm_pool(self):
        """Replenish the warm pool"""
        try:
            container = await self._create_base_container()
            if container:
                self.warm_pool.append(container.id)
        except Exception as e:
            logger.error(f"Error replenishing warm pool: {e}")
    
    async def _setup_repository(self, container, repo_url: str, commit_hash: str):
        """Clone and setup repository in container"""
        # Ensure git is available inside the container
        git_check = container.exec_run(["/bin/sh", "-c", "git --version"])
        if git_check.exit_code != 0:
            container.exec_run(["/bin/sh", "-c", "apt-get update"])
            container.exec_run(["/bin/sh", "-c", "apt-get install -y git"])

        commands = [
            "rm -rf /workspace/repo",
            # Full clone to support older commit checkout
            f"git clone {repo_url} /workspace/repo",
            f"cd /workspace/repo && git checkout {commit_hash}",
            # Install the repo in editable mode; fail fast if deps break
            "cd /workspace/repo && pip install -e .",
            # Install extra requirements if present
            "cd /workspace/repo && [ -f requirements.txt ] && pip install -r requirements.txt || true",
        ]
        
        for cmd in commands:
            result = container.exec_run(["/bin/sh", "-c", cmd])
            if result.exit_code != 0:
                out = result.output.decode("utf-8") if result.output else ""
                if "git checkout" in cmd:
                    logger.warning(f"Checkout failed ({cmd}); continuing without exact pin. Output: {out}")
                    continue
                raise RuntimeError(f"Failed to execute: {cmd}\nOutput: {out}")
    
    async def apply_mutation(self, container_id: str, mutation: Dict[str, Any]):
        """
        Apply a code mutation to prevent memorization.
        
        Args:
            container_id: Container to mutate
            mutation: Mutation specification
        """
        try:
            container = self.docker_client.containers.get(container_id)
            
            if mutation["type"] == "rename_variable":
                # Use sed to rename variables
                cmd = f"sed -i 's/{mutation['old_name']}/{mutation['new_name']}/g' /workspace/repo/{mutation['file']}"
                result = container.exec_run(cmd)
                
                if result.exit_code != 0:
                    logger.warning(f"Mutation failed: {mutation}")
            
            elif mutation["type"] == "move_file":
                # Move files to different locations
                cmd = f"mv /workspace/repo/{mutation['old_path']} /workspace/repo/{mutation['new_path']}"
                result = container.exec_run(cmd)
                
                if result.exit_code != 0:
                    logger.warning(f"File move failed: {mutation}")
                    
        except Exception as e:
            logger.error(f"Error applying mutation: {e}")
    
    async def execute_in_environment(
        self,
        container_id: str,
        command: str,
        workdir: str = "/workspace/repo"
    ) -> Dict[str, Any]:
        """
        Execute a command in the environment.
        
        Args:
            container_id: Container ID
            command: Command to execute
            workdir: Working directory
            
        Returns:
            Execution result
        """
        try:
            container = self.docker_client.containers.get(container_id)
            result = container.exec_run(["/bin/sh", "-c", command], workdir=workdir)
            
            return {
                "exit_code": result.exit_code,
                "stdout": result.output.decode("utf-8") if result.output else "",
                "success": result.exit_code == 0
            }
            
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }
    
    async def cleanup_environment(self, container_id: str):
        """Clean up an environment after use"""
        try:
            container = self.docker_client.containers.get(container_id)
            
            # Stop and remove container
            container.stop(timeout=10)
            container.remove()
            
            # Remove from active environments
            env_to_remove = None
            for env_id, env in self.active_environments.items():
                if env["container_id"] == container_id:
                    env_to_remove = env_id
                    break
            
            if env_to_remove:
                del self.active_environments[env_to_remove]
            
            logger.info(f"Cleaned up container {container_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up container: {e}")
    
    async def cleanup_all(self):
        """Clean up all active environments"""
        for env in list(self.active_environments.values()):
            await self.cleanup_environment(env["container_id"])
        
        # Clean up warm pool
        for container_id in self.warm_pool:
            try:
                container = self.docker_client.containers.get(container_id)
                container.stop(timeout=10)
                container.remove()
            except Exception:
                pass
        
        self.warm_pool.clear()