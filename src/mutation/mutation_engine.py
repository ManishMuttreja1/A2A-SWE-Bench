"""Main mutation engine that orchestrates all mutation strategies"""

import os
import random
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import tempfile
import shutil

from .ast_mutator import ASTMutator, MutationConfig
from .semantic_mutator import SemanticMutator

logger = logging.getLogger(__name__)


class MutationEngine:
    """
    Main engine for applying code mutations.
    Orchestrates different mutation strategies.
    """
    
    def __init__(
        self,
        enable_ast: bool = True,
        enable_semantic: bool = True,
        mutation_rate: float = 0.3,
        preserve_tests: bool = True
    ):
        self.enable_ast = enable_ast
        self.enable_semantic = enable_semantic
        self.mutation_rate = mutation_rate
        self.preserve_tests = preserve_tests
        
        # Initialize mutators
        config = MutationConfig(
            mutation_rate=mutation_rate,
            preserve_functionality=True
        )
        self.ast_mutator = ASTMutator(config) if enable_ast else None
        self.semantic_mutator = SemanticMutator() if enable_semantic else None
        
        # Statistics
        self.stats = {
            "repos_mutated": 0,
            "files_mutated": 0,
            "files_skipped": 0,
            "mutations_applied": 0,
            "errors": 0
        }
    
    async def mutate_repository(
        self,
        repo_path: str,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mutate an entire repository.
        
        Args:
            repo_path: Path to repository
            output_path: Optional output path (defaults to in-place)
            
        Returns:
            Mutation result
        """
        repo_path = Path(repo_path)
        
        if not repo_path.exists():
            logger.error(f"Repository not found: {repo_path}")
            return {"success": False, "error": "Repository not found"}
        
        # Create output directory if needed
        if output_path:
            output_path = Path(output_path)
            if repo_path != output_path:
                shutil.copytree(repo_path, output_path, dirs_exist_ok=True)
                repo_path = output_path
        
        logger.info(f"Mutating repository: {repo_path}")
        
        # Find Python files
        python_files = list(repo_path.rglob("*.py"))
        
        result = {
            "success": True,
            "total_files": len(python_files),
            "mutated_files": [],
            "skipped_files": [],
            "errors": []
        }
        
        for py_file in python_files:
            # Skip test files if configured
            if self.preserve_tests and self._is_test_file(py_file):
                result["skipped_files"].append(str(py_file))
                self.stats["files_skipped"] += 1
                continue
            
            # Skip __pycache__ and other generated files
            if "__pycache__" in str(py_file) or ".pyc" in str(py_file):
                continue
            
            # Apply mutation
            try:
                if await self.mutate_file(py_file):
                    result["mutated_files"].append(str(py_file))
                    self.stats["files_mutated"] += 1
                else:
                    result["skipped_files"].append(str(py_file))
                    
            except Exception as e:
                logger.error(f"Error mutating {py_file}: {e}")
                result["errors"].append({
                    "file": str(py_file),
                    "error": str(e)
                })
                self.stats["errors"] += 1
        
        self.stats["repos_mutated"] += 1
        
        # Add statistics
        result["statistics"] = self.get_statistics()
        
        return result
    
    async def mutate_file(self, filepath: Path) -> bool:
        """
        Mutate a single Python file.
        
        Args:
            filepath: Path to Python file
            
        Returns:
            True if file was mutated
        """
        # Random decision to mutate
        if random.random() > self.mutation_rate:
            return False
        
        try:
            # Read original code
            with open(filepath, 'r') as f:
                original_code = f.read()
            
            mutated_code = original_code
            
            # Apply AST mutations
            if self.enable_ast and self.ast_mutator:
                mutated_code = self.ast_mutator.mutate_code(
                    mutated_code,
                    str(filepath)
                )
                
                if mutated_code != original_code:
                    self.stats["mutations_applied"] += 1
            
            # Apply semantic mutations
            if self.enable_semantic and self.semantic_mutator:
                mutated_code = self.semantic_mutator.mutate_code(mutated_code)
                
                if mutated_code != original_code:
                    self.stats["mutations_applied"] += 1
            
            # Write back if changed
            if mutated_code != original_code:
                # Verify syntax before writing
                if self._verify_syntax(mutated_code):
                    with open(filepath, 'w') as f:
                        f.write(mutated_code)
                    return True
                else:
                    logger.warning(f"Syntax verification failed for {filepath}")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to mutate {filepath}: {e}")
            return False
    
    def _is_test_file(self, filepath: Path) -> bool:
        """Check if file is a test file"""
        name = filepath.name.lower()
        path_str = str(filepath).lower()
        
        # Check filename patterns
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
        
        # Check directory patterns
        if "test" in path_str or "tests" in path_str:
            return True
        
        return False
    
    def _verify_syntax(self, code: str) -> bool:
        """Verify Python syntax is valid"""
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False
    
    async def mutate_code_string(
        self,
        code: str,
        filename: str = "code.py"
    ) -> str:
        """
        Mutate a code string directly.
        
        Args:
            code: Python source code
            filename: Optional filename for context
            
        Returns:
            Mutated code
        """
        mutated = code
        
        # Apply mutations in sequence
        if self.enable_ast and self.ast_mutator:
            mutated = self.ast_mutator.mutate_code(mutated, filename)
        
        if self.enable_semantic and self.semantic_mutator:
            mutated = self.semantic_mutator.mutate_code(mutated)
        
        # Verify syntax
        if not self._verify_syntax(mutated):
            logger.warning("Mutation produced invalid syntax, returning original")
            return code
        
        return mutated
    
    async def create_mutation_variants(
        self,
        code: str,
        num_variants: int = 5
    ) -> List[str]:
        """
        Create multiple mutation variants of code.
        
        Args:
            code: Original Python code
            num_variants: Number of variants to create
            
        Returns:
            List of mutated code variants
        """
        variants = []
        
        for i in range(num_variants):
            # Vary mutation rate for diversity
            original_rate = self.mutation_rate
            self.mutation_rate = random.uniform(0.1, 0.5)
            
            variant = await self.mutate_code_string(code, f"variant_{i}.py")
            
            # Ensure variant is different
            if variant != code and variant not in variants:
                variants.append(variant)
            
            self.mutation_rate = original_rate
        
        # Add original if not enough variants
        while len(variants) < num_variants:
            variants.append(code)
        
        return variants[:num_variants]
    
    def analyze_mutation_resistance(
        self,
        code: str,
        test_function: callable
    ) -> Dict[str, Any]:
        """
        Analyze how resistant code is to mutations.
        
        Args:
            code: Python code to analyze
            test_function: Function to test if code still works
            
        Returns:
            Analysis results
        """
        results = {
            "total_mutations": 0,
            "successful_mutations": 0,
            "failed_mutations": 0,
            "resistance_score": 0.0
        }
        
        # Try different mutation strategies
        strategies = [
            ("variable_rename", {"rename_variables": True}),
            ("function_rename", {"rename_functions": True}),
            ("reorder", {"reorder_functions": True}),
            ("semantic", {"semantic_only": True})
        ]
        
        for strategy_name, config in strategies:
            try:
                # Apply mutation
                mutated = self.ast_mutator.mutate_code(code, "test.py")
                results["total_mutations"] += 1
                
                # Test if it still works
                if test_function(mutated):
                    results["successful_mutations"] += 1
                else:
                    results["failed_mutations"] += 1
                    
            except Exception as e:
                logger.error(f"Mutation test failed: {e}")
                results["failed_mutations"] += 1
        
        # Calculate resistance score
        if results["total_mutations"] > 0:
            results["resistance_score"] = (
                results["successful_mutations"] / results["total_mutations"]
            )
        
        return results
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get mutation engine statistics"""
        stats = {
            **self.stats,
            "config": {
                "ast_enabled": self.enable_ast,
                "semantic_enabled": self.enable_semantic,
                "mutation_rate": self.mutation_rate,
                "preserve_tests": self.preserve_tests
            }
        }
        
        if self.ast_mutator:
            stats["ast_stats"] = self.ast_mutator.get_statistics()
        
        return stats
    
    async def validate_mutations(
        self,
        original_path: str,
        mutated_path: str,
        test_command: str = "pytest"
    ) -> Dict[str, Any]:
        """
        Validate that mutations preserve functionality.
        
        Args:
            original_path: Path to original code
            mutated_path: Path to mutated code
            test_command: Command to run tests
            
        Returns:
            Validation results
        """
        import subprocess
        
        results = {
            "original_tests_pass": False,
            "mutated_tests_pass": False,
            "functionality_preserved": False
        }
        
        # Test original
        try:
            result = subprocess.run(
                f"{test_command} {original_path}",
                shell=True,
                capture_output=True,
                timeout=60
            )
            results["original_tests_pass"] = result.returncode == 0
        except Exception as e:
            logger.error(f"Original test failed: {e}")
        
        # Test mutated
        try:
            result = subprocess.run(
                f"{test_command} {mutated_path}",
                shell=True,
                capture_output=True,
                timeout=60
            )
            results["mutated_tests_pass"] = result.returncode == 0
        except Exception as e:
            logger.error(f"Mutated test failed: {e}")
        
        # Check if functionality preserved
        results["functionality_preserved"] = (
            results["original_tests_pass"] == results["mutated_tests_pass"]
        )
        
        return results