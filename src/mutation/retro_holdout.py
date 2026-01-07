"""Retro-Holdout Anti-Contamination System"""

import ast
import asyncio
import logging
import random
import re
import hashlib
from typing import Dict, Any, List, Optional, Set, Tuple
from pathlib import Path
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)


class RetroHoldoutGenerator:
    """
    Implements the Retro-Holdout methodology to prevent data contamination.
    Creates semantically equivalent but syntactically different versions of code.
    """
    
    def __init__(self, mutation_seed: Optional[int] = None):
        """
        Args:
            mutation_seed: Seed for reproducible mutations
        """
        if mutation_seed:
            random.seed(mutation_seed)
        
        # Track mutations
        self.mutation_history: Dict[str, Dict[str, Any]] = {}
        
        # Variable renaming mappings
        self.rename_mappings = {
            # Common variable names to alternatives
            "data": ["info", "content", "payload", "records"],
            "result": ["output", "response", "outcome", "value"],
            "user": ["account", "member", "person", "client"],
            "item": ["element", "entry", "object", "entity"],
            "config": ["settings", "options", "params", "configuration"],
            "manager": ["handler", "controller", "coordinator", "orchestrator"],
            "request": ["query", "call", "demand", "solicitation"],
            "response": ["reply", "answer", "feedback", "return_value"],
            "error": ["exception", "fault", "issue", "problem"],
            "cache": ["storage", "buffer", "store", "repository"],
            "index": ["position", "offset", "location", "idx"],
            "count": ["total", "number", "quantity", "amount"],
            "list": ["array", "collection", "sequence", "items"],
            "dict": ["mapping", "hashmap", "table", "dictionary"],
            "key": ["identifier", "id", "name", "label"],
            "value": ["content", "data", "worth", "val"],
            "session": ["connection", "context", "state", "period"],
            "model": ["schema", "structure", "template", "pattern"],
            "view": ["display", "render", "presentation", "interface"],
            "utils": ["helpers", "tools", "utilities", "common"]
        }
        
        # Class name transformations
        self.class_transformations = {
            "Manager": "Handler",
            "Controller": "Coordinator",
            "Service": "Provider",
            "Factory": "Builder",
            "Adapter": "Wrapper",
            "Repository": "Store",
            "Validator": "Checker",
            "Processor": "Engine",
            "Generator": "Creator",
            "Parser": "Analyzer"
        }
        
        # Function name transformations
        self.function_transformations = {
            "get": "fetch",
            "set": "assign",
            "create": "make",
            "delete": "remove",
            "update": "modify",
            "process": "handle",
            "validate": "check",
            "parse": "analyze",
            "render": "display",
            "execute": "run"
        }
    
    async def generate_retro_holdout(
        self,
        instance: Dict[str, Any],
        repo_path: Path,
        level: str = "medium"
    ) -> Dict[str, Any]:
        """
        Generate a retro-holdout version of an instance
        
        Args:
            instance: Original SWE-bench instance
            repo_path: Path to repository
            level: Mutation level (light, medium, heavy)
            
        Returns:
            Mutated instance with renamed variables and paraphrased descriptions
        """
        instance_id = instance["instance_id"]
        logger.info(f"Generating retro-holdout for {instance_id} with level {level}")
        
        # Generate unique hash for this mutation
        mutation_hash = hashlib.md5(
            f"{instance_id}_{level}_{datetime.utcnow().isoformat()}".encode()
        ).hexdigest()[:8]
        
        mutated_instance = {
            **instance,
            "instance_id": f"{instance_id}_retro_{mutation_hash}",
            "is_retro_holdout": True,
            "original_instance_id": instance_id,
            "mutation_level": level,
            "mutation_hash": mutation_hash
        }
        
        # 1. Mutate repository code
        mutations = await self._mutate_repository(repo_path, level)
        mutated_instance["code_mutations"] = mutations
        
        # 2. Paraphrase problem statement
        mutated_instance["problem_statement"] = await self._paraphrase_description(
            instance["problem_statement"],
            level
        )
        
        # 3. Rename test identifiers
        mutated_instance["FAIL_TO_PASS"] = self._mutate_test_names(
            instance.get("FAIL_TO_PASS", []),
            mutations
        )
        mutated_instance["PASS_TO_PASS"] = self._mutate_test_names(
            instance.get("PASS_TO_PASS", []),
            mutations
        )
        
        # 4. Mutate patch if available
        if instance.get("patch"):
            mutated_instance["patch"] = await self._mutate_patch(
                instance["patch"],
                mutations
            )
        
        # Track mutation
        self.mutation_history[mutation_hash] = {
            "original_instance": instance_id,
            "mutations": mutations,
            "timestamp": datetime.utcnow().isoformat(),
            "level": level
        }
        
        return mutated_instance
    
    async def _mutate_repository(
        self,
        repo_path: Path,
        level: str
    ) -> Dict[str, Any]:
        """Mutate repository code with semantic renaming"""
        mutations = {
            "variables": {},
            "functions": {},
            "classes": {},
            "modules": {},
            "files_mutated": []
        }
        
        # Determine mutation probability based on level
        mutation_prob = {
            "light": 0.3,
            "medium": 0.6,
            "heavy": 0.9
        }[level]
        
        # Process Python files
        for py_file in repo_path.rglob("*.py"):
            # Skip test files in light mode
            if level == "light" and ("test" in str(py_file).lower() or "spec" in str(py_file).lower()):
                continue
            
            try:
                file_mutations = await self._mutate_file(
                    py_file,
                    mutation_prob,
                    mutations
                )
                
                if file_mutations:
                    mutations["files_mutated"].append(str(py_file))
                    
            except Exception as e:
                logger.warning(f"Error mutating {py_file}: {e}")
        
        return mutations
    
    async def _mutate_file(
        self,
        file_path: Path,
        mutation_prob: float,
        global_mutations: Dict[str, Any]
    ) -> bool:
        """Mutate a single Python file"""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Parse AST
            tree = ast.parse(content)
            
            # Create transformer
            transformer = SemanticRenameTransformer(
                mutation_prob,
                self.rename_mappings,
                self.class_transformations,
                self.function_transformations,
                global_mutations
            )
            
            # Transform AST
            new_tree = transformer.visit(tree)
            
            # Convert back to source
            import astor
            new_content = astor.to_source(new_tree)
            
            # Write back if changed
            if new_content != content:
                with open(file_path, 'w') as f:
                    f.write(new_content)
                return True
                
        except Exception as e:
            logger.error(f"Failed to mutate {file_path}: {e}")
        
        return False
    
    async def _paraphrase_description(
        self,
        description: str,
        level: str
    ) -> str:
        """Paraphrase problem description to avoid memorization"""
        # Simple rule-based paraphrasing
        paraphrased = description
        
        # Replace technical terms
        replacements = {
            "bug": "issue",
            "error": "problem",
            "fails": "doesn't work",
            "crashes": "stops working",
            "throws": "raises",
            "returns": "gives back",
            "function": "method",
            "method": "function",
            "parameter": "argument",
            "argument": "parameter",
            "module": "package",
            "package": "module"
        }
        
        if level in ["medium", "heavy"]:
            for old, new in replacements.items():
                if random.random() < 0.5:  # Randomly apply replacements
                    paraphrased = re.sub(
                        r'\b' + old + r'\b',
                        new,
                        paraphrased,
                        flags=re.IGNORECASE
                    )
        
        if level == "heavy":
            # Restructure sentences
            sentences = paraphrased.split('. ')
            if len(sentences) > 2:
                # Randomly reorder middle sentences
                middle = sentences[1:-1]
                random.shuffle(middle)
                paraphrased = '. '.join([sentences[0]] + middle + [sentences[-1]])
        
        # Add variation prefix
        variation_prefixes = [
            "There's an issue where ",
            "A problem occurs when ",
            "The system encounters an error when ",
            "Users report that "
        ]
        
        if level != "light" and not paraphrased.startswith(tuple(variation_prefixes)):
            paraphrased = random.choice(variation_prefixes) + paraphrased[0].lower() + paraphrased[1:]
        
        return paraphrased
    
    def _mutate_test_names(
        self,
        test_names: List[str],
        mutations: Dict[str, Any]
    ) -> List[str]:
        """Mutate test names based on code mutations"""
        mutated_tests = []
        
        for test in test_names:
            mutated = test
            
            # Apply class renames
            for old_class, new_class in mutations.get("classes", {}).items():
                mutated = mutated.replace(old_class, new_class)
            
            # Apply function renames
            for old_func, new_func in mutations.get("functions", {}).items():
                mutated = mutated.replace(old_func, new_func)
            
            mutated_tests.append(mutated)
        
        return mutated_tests
    
    async def _mutate_patch(
        self,
        patch: str,
        mutations: Dict[str, Any]
    ) -> str:
        """Mutate a patch to match renamed code"""
        mutated_patch = patch
        
        # Apply all mutations to the patch
        for old_var, new_var in mutations.get("variables", {}).items():
            mutated_patch = re.sub(
                r'\b' + old_var + r'\b',
                new_var,
                mutated_patch
            )
        
        for old_func, new_func in mutations.get("functions", {}).items():
            mutated_patch = re.sub(
                r'\b' + old_func + r'\b',
                new_func,
                mutated_patch
            )
        
        for old_class, new_class in mutations.get("classes", {}).items():
            mutated_patch = re.sub(
                r'\b' + old_class + r'\b',
                new_class,
                mutated_patch
            )
        
        return mutated_patch
    
    async def verify_semantic_equivalence(
        self,
        original_path: Path,
        mutated_path: Path,
        test_commands: List[str]
    ) -> bool:
        """
        Verify that mutations preserve semantic equivalence
        
        Args:
            original_path: Path to original code
            mutated_path: Path to mutated code
            test_commands: Test commands to run
            
        Returns:
            True if tests pass on both versions
        """
        # Run tests on original
        original_results = await self._run_tests(original_path, test_commands)
        
        # Run tests on mutated
        mutated_results = await self._run_tests(mutated_path, test_commands)
        
        # Compare results
        return (
            original_results["passed"] == mutated_results["passed"] and
            original_results["failed"] == mutated_results["failed"]
        )
    
    async def _run_tests(
        self,
        repo_path: Path,
        test_commands: List[str]
    ) -> Dict[str, Any]:
        """Run tests and collect results"""
        import subprocess
        
        results = {
            "passed": 0,
            "failed": 0,
            "errors": []
        }
        
        for cmd in test_commands:
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    results["passed"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(result.stderr)
                    
            except subprocess.TimeoutExpired:
                results["failed"] += 1
                results["errors"].append("Test timed out")
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(str(e))
        
        return results
    
    def calculate_contamination_score(
        self,
        original_performance: float,
        mutated_performance: float
    ) -> float:
        """
        Calculate contamination score based on performance drop
        
        Args:
            original_performance: Performance on original dataset
            mutated_performance: Performance on mutated dataset
            
        Returns:
            Contamination score from 0 (no contamination) to 1 (fully contaminated)
        """
        if original_performance == 0:
            return 0.0
        
        # Large performance drop indicates contamination
        performance_drop = original_performance - mutated_performance
        contamination = performance_drop / original_performance
        
        return max(0.0, min(1.0, contamination))
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get retro-holdout statistics"""
        return {
            "total_mutations": len(self.mutation_history),
            "mutations_by_level": self._count_by_level(),
            "average_files_mutated": self._average_files_mutated(),
            "unique_instances": len(set(
                m["original_instance"] for m in self.mutation_history.values()
            ))
        }
    
    def _count_by_level(self) -> Dict[str, int]:
        """Count mutations by level"""
        counts = {"light": 0, "medium": 0, "heavy": 0}
        for mutation in self.mutation_history.values():
            level = mutation.get("level", "medium")
            counts[level] += 1
        return counts
    
    def _average_files_mutated(self) -> float:
        """Calculate average files mutated"""
        total_files = sum(
            len(m.get("mutations", {}).get("files_mutated", []))
            for m in self.mutation_history.values()
        )
        return total_files / max(len(self.mutation_history), 1)


class SemanticRenameTransformer(ast.NodeTransformer):
    """AST transformer for semantic renaming"""
    
    def __init__(
        self,
        mutation_prob: float,
        rename_mappings: Dict[str, List[str]],
        class_transformations: Dict[str, str],
        function_transformations: Dict[str, str],
        global_mutations: Dict[str, Any]
    ):
        self.mutation_prob = mutation_prob
        self.rename_mappings = rename_mappings
        self.class_transformations = class_transformations
        self.function_transformations = function_transformations
        self.global_mutations = global_mutations
        self.local_renames: Dict[str, str] = {}
    
    def visit_Name(self, node):
        """Rename variables"""
        if random.random() < self.mutation_prob:
            old_name = node.id
            
            # Check if already renamed
            if old_name in self.local_renames:
                node.id = self.local_renames[old_name]
            # Check for renameable pattern
            elif old_name in self.rename_mappings:
                new_name = random.choice(self.rename_mappings[old_name])
                node.id = new_name
                self.local_renames[old_name] = new_name
                self.global_mutations["variables"][old_name] = new_name
        
        return node
    
    def visit_ClassDef(self, node):
        """Rename classes"""
        if random.random() < self.mutation_prob:
            for suffix, replacement in self.class_transformations.items():
                if node.name.endswith(suffix):
                    new_name = node.name[:-len(suffix)] + replacement
                    self.global_mutations["classes"][node.name] = new_name
                    node.name = new_name
                    break
        
        self.generic_visit(node)
        return node
    
    def visit_FunctionDef(self, node):
        """Rename functions"""
        if random.random() < self.mutation_prob:
            for prefix, replacement in self.function_transformations.items():
                if node.name.startswith(prefix + "_"):
                    new_name = node.name.replace(prefix + "_", replacement + "_", 1)
                    self.global_mutations["functions"][node.name] = new_name
                    node.name = new_name
                    break
        
        self.generic_visit(node)
        return node