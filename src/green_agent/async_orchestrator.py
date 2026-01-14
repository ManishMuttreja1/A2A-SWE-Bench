"""Async Environment Orchestrator with proper timeout handling"""

import asyncio
import logging
import docker
from typing import Dict, Any, Optional, List
import uuid
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class AsyncEnvironmentOrchestrator:
    """
    Async-first Docker environment manager with timeout support.
    """
    
    def __init__(
        self,
        docker_socket: str = "unix://var/run/docker.sock",
        warm_pool_size: int = 3,
        base_image: str = "python:3.10-slim",
        max_workers: int = 10
    ):
        self.docker_client = docker.from_env()
        self.warm_pool_size = warm_pool_size
        self.base_image = base_image
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Track environments
        self.active_environments: Dict[str, Dict[str, Any]] = {}
        self.warm_pool: List[str] = []
        
        # Container configuration with resource limits
        self.container_config = {
            "detach": True,
            "tty": True,
            "stdin_open": True,
            "working_dir": "/workspace",
            "mem_limit": "2g",  # Reduced memory limit
            "cpu_quota": 50000,  # Reduced CPU quota for stability
            "network_mode": "bridge",
            "labels": {
                "swe-bench": "true",
                "orchestrator": "async-green-agent"
            },
            "environment": {
                "PYTHONUNBUFFERED": "1",
                "PYTHONDONTWRITEBYTECODE": "1"
            }
        }
    
    async def provision_environment(
        self,
        repo_url: str,
        commit_hash: str,
        instance_id: str,
        timeout: int = 300
    ) -> Optional[Dict[str, Any]]:
        """
        Provision environment with timeout protection.
        """
        env_id = str(uuid.uuid4())
        logger.info(f"Provisioning environment {env_id} for {instance_id}")
        
        try:
            # Create container with timeout
            container = await asyncio.wait_for(
                self._create_container_async(),
                timeout=60
            )
            
            if not container:
                raise RuntimeError("Failed to create container")
            
            # Setup repository with timeout
            await asyncio.wait_for(
                self._setup_repository_async(container, repo_url, commit_hash),
                timeout=timeout
            )
            
            environment = {
                "id": env_id,
                "container_id": container.id,
                "container_name": container.name,
                "repo_url": repo_url,
                "commit_hash": commit_hash,
                "instance_id": instance_id,
                "status": "ready"
            }
            
            self.active_environments[env_id] = environment
            return environment
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout provisioning environment for {instance_id}")
            return None
        except Exception as e:
            logger.error(f"Error provisioning environment: {e}")
            return None
    
    async def _create_container_async(self) -> Optional[Any]:
        """Create container asynchronously"""
        loop = asyncio.get_event_loop()
        
        def create_container():
            return self.docker_client.containers.run(
                self.base_image,
                "sleep infinity",
                **self.container_config
            )
        
        try:
            container = await loop.run_in_executor(self.executor, create_container)
            
            # Basic setup
            setup_commands = [
                "apt-get update -qq",
                "apt-get install -y -qq git curl build-essential > /dev/null 2>&1",
                "pip install -q --upgrade pip",
                "pip install -q pytest pytest-cov pytest-django"
            ]
            
            for cmd in setup_commands:
                await self._exec_async(container, cmd, timeout=30)
            
            return container
            
        except Exception as e:
            logger.error(f"Error creating container: {e}")
            return None
    
    async def _setup_repository_async(
        self,
        container,
        repo_url: str,
        commit_hash: str
    ):
        """Setup repository asynchronously"""
        # Extract repo name
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        
        commands = [
            f"git clone --depth 1 {repo_url} /workspace/repo",
            f"cd /workspace/repo && git fetch --depth 50 origin {commit_hash}",
            f"cd /workspace/repo && git checkout {commit_hash}",
        ]
        
        # Add repo-specific setup
        if "django" in repo_url:
            commands.extend([
                "cd /workspace/repo && pip install -q -e .",
                "cd /workspace/repo && pip install -q -r tests/requirements/py3.txt || true"
            ])
        
        for cmd in commands:
            result = await self._exec_async(container, cmd, timeout=60)
            if not result.get("success"):
                logger.warning(f"Command failed: {cmd}")
    
    async def _exec_async(
        self,
        container,
        command: str,
        timeout: int = 30,
        workdir: str = None
    ) -> Dict[str, Any]:
        """Execute command asynchronously with timeout"""
        loop = asyncio.get_event_loop()
        
        def exec_command():
            kwargs = {"workdir": workdir} if workdir else {}
            result = container.exec_run(
                ["/bin/sh", "-c", command],
                **kwargs
            )
            return {
                "exit_code": result.exit_code,
                "stdout": result.output.decode("utf-8", errors="ignore") if result.output else "",
                "success": result.exit_code == 0
            }
        
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self.executor, exec_command),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Command timed out after {timeout}s: {command}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "success": False
            }
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }
    
    async def execute_in_environment(
        self,
        container_id: str,
        command: str,
        workdir: str = "/workspace/repo",
        timeout: int = 120
    ) -> Dict[str, Any]:
        """
        Execute command in environment with timeout.
        """
        try:
            container = self.docker_client.containers.get(container_id)
            return await self._exec_async(container, command, timeout, workdir)
            
        except docker.errors.NotFound:
            logger.error(f"Container {container_id} not found")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Container not found",
                "success": False
            }
        except Exception as e:
            logger.error(f"Error executing in environment: {e}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }
    
    async def cleanup_environment(self, env_id: str):
        """Clean up environment"""
        if env_id not in self.active_environments:
            return
        
        env = self.active_environments[env_id]
        container_id = env.get("container_id")
        
        if container_id:
            try:
                container = self.docker_client.containers.get(container_id)
                await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    container.remove,
                    True  # force
                )
            except Exception as e:
                logger.error(f"Error removing container: {e}")
        
        del self.active_environments[env_id]
    
    async def cleanup_all(self):
        """Clean up all environments"""
        env_ids = list(self.active_environments.keys())
        for env_id in env_ids:
            await self.cleanup_environment(env_id)
        
        # Clean up warm pool
        for container_id in self.warm_pool:
            try:
                container = self.docker_client.containers.get(container_id)
                container.remove(force=True)
            except Exception:
                pass
        
        self.warm_pool.clear()
    
    def __del__(self):
        """Cleanup on deletion"""
        self.executor.shutdown(wait=False)