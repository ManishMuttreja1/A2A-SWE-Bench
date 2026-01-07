"""Dataset Loader for SWE-bench"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import asyncio
from datasets import load_dataset
import aiofiles
import git
import os

logger = logging.getLogger(__name__)


class DatasetLoader:
    """
    Loads and manages SWE-bench datasets from HuggingFace Hub
    """
    
    DATASET_CONFIGS = {
        "verified": "princeton-nlp/SWE-bench_Verified",
        "lite": "princeton-nlp/SWE-bench_Lite",
        "full": "princeton-nlp/SWE-bench",
        "oracle": "princeton-nlp/SWE-bench_oracle",
    }
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path("data/swebench_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.instances: Dict[str, List[Dict[str, Any]]] = {}
        self.loaded_configs: set = set()
        
        # Repository cache
        self.repo_cache_dir = self.cache_dir / "repos"
        self.repo_cache_dir.mkdir(exist_ok=True)
    
    async def load_dataset(self, config: str = "verified") -> List[Dict[str, Any]]:
        """
        Load a specific SWE-bench dataset configuration
        
        Args:
            config: Dataset configuration (verified, lite, full, oracle)
            
        Returns:
            List of instances
        """
        if config in self.loaded_configs:
            logger.info(f"Dataset '{config}' already loaded from cache")
            return self.instances.get(config, [])
        
        dataset_name = self.DATASET_CONFIGS.get(config)
        if not dataset_name:
            raise ValueError(f"Unknown dataset config: {config}")
        
        cache_file = self.cache_dir / f"swebench_{config}.json"
        
        # Try to load from cache first
        if cache_file.exists():
            logger.info(f"Loading dataset '{config}' from cache: {cache_file}")
            async with aiofiles.open(cache_file, 'r') as f:
                content = await f.read()
                instances = json.loads(content)
                self.instances[config] = instances
                self.loaded_configs.add(config)
                return instances
        
        # Load from HuggingFace Hub
        logger.info(f"Downloading dataset '{config}' from HuggingFace Hub")
        try:
            # Use synchronous load in executor to avoid blocking
            loop = asyncio.get_event_loop()
            dataset = await loop.run_in_executor(
                None,
                lambda: load_dataset(dataset_name, split="test")
            )
            
            # Convert to list of dicts
            instances = []
            for item in dataset:
                instance = {
                    "instance_id": item.get("instance_id"),
                    "repo": item.get("repo"),
                    "base_commit": item.get("base_commit"),
                    "problem_statement": item.get("problem_statement"),
                    "hints_text": item.get("hints_text", ""),
                    "created_at": item.get("created_at"),
                    "patch": item.get("patch"),
                    "test_patch": item.get("test_patch"),
                    "version": item.get("version"),
                    "FAIL_TO_PASS": item.get("FAIL_TO_PASS", []),
                    "PASS_TO_PASS": item.get("PASS_TO_PASS", []),
                    "environment_setup_commit": item.get("environment_setup_commit"),
                }
                instances.append(instance)
            
            # Cache the dataset
            async with aiofiles.open(cache_file, 'w') as f:
                await f.write(json.dumps(instances, indent=2))
            
            self.instances[config] = instances
            self.loaded_configs.add(config)
            
            logger.info(f"Loaded {len(instances)} instances from '{config}' dataset")
            return instances
            
        except Exception as e:
            logger.error(f"Error loading dataset '{config}': {e}")
            # Fall back to sample data
            return await self._create_fallback_instances()
    
    async def _create_fallback_instances(self) -> List[Dict[str, Any]]:
        """Create fallback instances if dataset loading fails"""
        logger.warning("Using fallback sample instances")
        
        instances = [
            {
                "instance_id": "django__django-11099",
                "repo": "django/django",
                "base_commit": "419a78300f7cd27611196e1e464d50fd0385ff27",
                "problem_statement": "UsernameValidator allows trailing newline in usernames\n"
                                   "Description: Django's UsernameValidator uses the regex r'^[\\w.@+-]+$' "
                                   "which allows trailing newlines. This should be r'^[\\w.@+-]+\\Z'",
                "hints_text": "",
                "created_at": "2019-02-11T10:19:00Z",
                "patch": "diff --git a/django/contrib/auth/validators.py...",
                "test_patch": "diff --git a/tests/auth_tests/test_validators.py...",
                "version": "3.0",
                "FAIL_TO_PASS": ["tests.auth_tests.test_validators::UsernameValidatorTest::test_trailing_newline"],
                "PASS_TO_PASS": ["tests.auth_tests.test_validators::UsernameValidatorTest::test_valid"],
                "environment_setup_commit": "419a78300f7cd27611196e1e464d50fd0385ff27"
            },
            {
                "instance_id": "scikit-learn__scikit-learn-13241", 
                "repo": "scikit-learn/scikit-learn",
                "base_commit": "b0b3b5e9e5c8e9f8b9e9e5c8e9f8b9e9e5c8e9f8",
                "problem_statement": "KMeans gives incorrect cluster centers when sample weights are used\n"
                                   "When using sample_weight parameter, KMeans returns wrong cluster centers.",
                "hints_text": "",
                "created_at": "2019-01-29T16:56:00Z",
                "patch": "",
                "test_patch": "",
                "version": "0.21",
                "FAIL_TO_PASS": ["sklearn/cluster/tests/test_k_means.py::test_kmeans_sample_weight"],
                "PASS_TO_PASS": [],
                "environment_setup_commit": "b0b3b5e9e5c8e9f8b9e9e5c8e9f8b9e9e5c8e9f8"
            }
        ]
        
        return instances
    
    async def get_instance(self, instance_id: str, config: str = "verified") -> Optional[Dict[str, Any]]:
        """
        Get a specific instance by ID
        
        Args:
            instance_id: Instance identifier
            config: Dataset configuration
            
        Returns:
            Instance dict or None
        """
        instances = await self.load_dataset(config)
        
        for instance in instances:
            if instance["instance_id"] == instance_id:
                return instance
        
        return None
    
    async def clone_repository(self, repo_name: str, commit: str) -> Path:
        """
        Clone a repository and checkout specific commit
        
        Args:
            repo_name: Repository name (e.g., "django/django")
            commit: Commit hash to checkout
            
        Returns:
            Path to cloned repository
        """
        repo_dir = self.repo_cache_dir / repo_name.replace("/", "_")
        
        if repo_dir.exists():
            # Update existing repo
            logger.info(f"Updating existing repository: {repo_name}")
            try:
                repo = git.Repo(repo_dir)
                repo.remotes.origin.fetch()
                repo.git.checkout(commit)
                return repo_dir
            except Exception as e:
                logger.error(f"Error updating repo {repo_name}: {e}")
                # Remove corrupted repo
                import shutil
                shutil.rmtree(repo_dir)
        
        # Clone new repository
        logger.info(f"Cloning repository: {repo_name}")
        repo_url = f"https://github.com/{repo_name}.git"
        
        try:
            loop = asyncio.get_event_loop()
            repo = await loop.run_in_executor(
                None,
                lambda: git.Repo.clone_from(repo_url, repo_dir)
            )
            
            # Checkout specific commit
            repo.git.checkout(commit)
            
            return repo_dir
            
        except Exception as e:
            logger.error(f"Error cloning repository {repo_name}: {e}")
            raise
    
    async def apply_patch(self, repo_dir: Path, patch: str) -> bool:
        """
        Apply a patch to a repository
        
        Args:
            repo_dir: Path to repository
            patch: Patch content
            
        Returns:
            Success status
        """
        try:
            repo = git.Repo(repo_dir)
            
            # Save patch to temp file
            patch_file = repo_dir / "temp.patch"
            async with aiofiles.open(patch_file, 'w') as f:
                await f.write(patch)
            
            # Apply patch
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: repo.git.apply(str(patch_file), three_way=True)
            )
            
            # Clean up
            patch_file.unlink()
            
            return True
            
        except Exception as e:
            logger.error(f"Error applying patch: {e}")
            return False
    
    async def get_repository_info(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get repository information for an instance
        
        Args:
            instance: Instance dict
            
        Returns:
            Repository info dict
        """
        repo_name = instance["repo"]
        commit = instance["base_commit"]
        
        info = {
            "repo_name": repo_name,
            "repo_url": f"https://github.com/{repo_name}",
            "commit": commit,
            "clone_url": f"https://github.com/{repo_name}.git",
            "docker_image": self._get_docker_image(repo_name, instance.get("version")),
            "test_commands": self._get_test_commands(repo_name, instance)
        }
        
        return info
    
    def _get_docker_image(self, repo_name: str, version: Optional[str] = None) -> str:
        """Get appropriate Docker image for repository"""
        # Map repositories to their Docker images
        repo_images = {
            "django/django": "swebench/django:latest",
            "scikit-learn/scikit-learn": "swebench/scikit-learn:latest",
            "flask/flask": "swebench/flask:latest",
            "requests/requests": "swebench/requests:latest",
            "pytest-dev/pytest": "swebench/pytest:latest",
            "sympy/sympy": "swebench/sympy:latest",
        }
        
        return repo_images.get(repo_name, "python:3.9-slim")
    
    def _get_test_commands(self, repo_name: str, instance: Dict[str, Any]) -> List[str]:
        """Get test commands for repository"""
        # Extract test files from FAIL_TO_PASS
        fail_to_pass = instance.get("FAIL_TO_PASS", [])
        
        if not fail_to_pass:
            # Default test commands by repo
            default_commands = {
                "django/django": ["python runtests.py"],
                "scikit-learn/scikit-learn": ["pytest -xvs"],
                "flask/flask": ["pytest tests/"],
                "requests/requests": ["pytest tests/"],
                "pytest-dev/pytest": ["pytest testing/"],
                "sympy/sympy": ["python -m pytest sympy/"],
            }
            return default_commands.get(repo_name, ["pytest"])
        
        # Convert test identifiers to commands
        commands = []
        for test in fail_to_pass:
            if "::" in test:
                # pytest format
                commands.append(f"pytest -xvs {test}")
            else:
                # Other format
                commands.append(f"python -m pytest {test}")
        
        return commands
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get dataset statistics"""
        stats = {
            "loaded_configs": list(self.loaded_configs),
            "total_instances": sum(len(instances) for instances in self.instances.values()),
            "by_config": {}
        }
        
        for config, instances in self.instances.items():
            # Count by repository
            repo_counts = {}
            for instance in instances:
                repo = instance.get("repo", "unknown")
                repo_counts[repo] = repo_counts.get(repo, 0) + 1
            
            stats["by_config"][config] = {
                "count": len(instances),
                "repositories": repo_counts
            }
        
        return stats