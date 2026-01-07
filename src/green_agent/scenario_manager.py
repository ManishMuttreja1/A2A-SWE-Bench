"""Scenario Manager for SWE-bench instances"""

import json
import random
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import aiofiles
import asyncio

logger = logging.getLogger(__name__)


class ScenarioManager:
    """
    Manages SWE-bench scenarios/instances.
    Handles loading, selection, and metadata management.
    """
    
    def __init__(self, scenarios_path: Optional[Path] = None):
        self.scenarios_path = scenarios_path or Path("data/swe-bench-instances.json")
        self.scenarios: List[Dict[str, Any]] = []
        self.scenario_index: Dict[str, Dict[str, Any]] = {}
        self._loaded = False
    
    async def load_scenarios(self):
        """Load scenarios from file"""
        if self._loaded:
            return
        
        try:
            if self.scenarios_path.exists():
                async with aiofiles.open(self.scenarios_path, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)
                    
                    # Handle both list and dict formats
                    if isinstance(data, list):
                        self.scenarios = data
                    elif isinstance(data, dict):
                        self.scenarios = data.get("instances", [])
                    
                    # Build index
                    for scenario in self.scenarios:
                        instance_id = scenario.get("instance_id")
                        if instance_id:
                            self.scenario_index[instance_id] = scenario
                    
                    self._loaded = True
                    logger.info(f"Loaded {len(self.scenarios)} scenarios")
            else:
                # Create sample scenarios for testing
                await self._create_sample_scenarios()
                
        except Exception as e:
            logger.error(f"Error loading scenarios: {e}")
            # Fall back to sample scenarios
            await self._create_sample_scenarios()
    
    async def _create_sample_scenarios(self):
        """Create sample scenarios for testing"""
        self.scenarios = [
            {
                "instance_id": "django__django-11099",
                "repo": "django/django",
                "base_commit": "abc123",
                "problem_statement": "Fix authentication bug in Django views where users can access restricted content",
                "test_commands": ["python manage.py test auth"],
                "oracle_tests": ["test_auth.py::test_restricted_access"],
                "mutation_targets": [
                    {"file": "django/auth/views.py", "old_name": "user", "new_name": "current_user"}
                ]
            },
            {
                "instance_id": "scikit-learn__scikit-learn-13241",
                "repo": "scikit-learn/scikit-learn",
                "base_commit": "def456",
                "problem_statement": "KMeans clustering fails with sparse matrices",
                "test_commands": ["pytest sklearn/cluster/tests/test_kmeans.py"],
                "oracle_tests": ["test_kmeans.py::test_sparse_matrix"]
            },
            {
                "instance_id": "flask__flask-3024",
                "repo": "flask/flask",
                "base_commit": "ghi789",
                "problem_statement": "URL routing fails with special characters",
                "test_commands": ["pytest tests/test_routing.py"],
                "oracle_tests": ["test_routing.py::test_special_chars"]
            }
        ]
        
        # Build index
        for scenario in self.scenarios:
            self.scenario_index[scenario["instance_id"]] = scenario
        
        self._loaded = True
        logger.info(f"Created {len(self.scenarios)} sample scenarios")
    
    async def get_scenario(self, scenario_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a specific scenario or a random one.
        
        Args:
            scenario_id: Optional specific scenario ID
            
        Returns:
            Scenario dict or None if not found
        """
        if not self._loaded:
            await self.load_scenarios()
        
        if scenario_id:
            return self.scenario_index.get(scenario_id)
        
        # Return random scenario
        if self.scenarios:
            return random.choice(self.scenarios)
        
        return None
    
    async def get_scenarios_by_repo(self, repo_name: str) -> List[Dict[str, Any]]:
        """Get all scenarios for a specific repository"""
        if not self._loaded:
            await self.load_scenarios()
        
        return [
            scenario for scenario in self.scenarios
            if scenario.get("repo") == repo_name
        ]
    
    async def get_scenario_metadata(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific scenario"""
        scenario = await self.get_scenario(scenario_id)
        
        if not scenario:
            return None
        
        return {
            "instance_id": scenario.get("instance_id"),
            "repo": scenario.get("repo"),
            "difficulty": scenario.get("difficulty", "medium"),
            "category": scenario.get("category", "bug_fix"),
            "has_tests": bool(scenario.get("oracle_tests")),
            "mutatable": bool(scenario.get("mutation_targets"))
        }
    
    async def add_fresh_scenario(self, scenario: Dict[str, Any]) -> bool:
        """
        Add a fresh scenario (e.g., from GitHub harvester).
        
        Args:
            scenario: New scenario dict
            
        Returns:
            Success boolean
        """
        try:
            instance_id = scenario.get("instance_id")
            if not instance_id:
                instance_id = f"fresh_{len(self.scenarios)}_{asyncio.get_event_loop().time()}"
                scenario["instance_id"] = instance_id
            
            # Add to collections
            self.scenarios.append(scenario)
            self.scenario_index[instance_id] = scenario
            
            # Mark as fresh (not in training data)
            scenario["fresh"] = True
            scenario["added_at"] = asyncio.get_event_loop().time()
            
            logger.info(f"Added fresh scenario: {instance_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding fresh scenario: {e}")
            return False
    
    async def get_fresh_scenarios(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently added fresh scenarios"""
        if not self._loaded:
            await self.load_scenarios()
        
        fresh = [s for s in self.scenarios if s.get("fresh", False)]
        
        # Sort by added time, most recent first
        fresh.sort(key=lambda x: x.get("added_at", 0), reverse=True)
        
        return fresh[:limit]