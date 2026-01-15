"""Patch Mutation Testing

Tests if patches are robust by mutating them and verifying
tests catch the mutations.
"""

import ast
import logging
import random
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Mutation:
    """A code mutation"""
    name: str
    original: str
    mutated: str
    location: str
    type: str  # "operator", "boundary", "negation", "removal"


@dataclass
class MutationResult:
    """Result of mutation testing"""
    total_mutants: int
    killed: int  # Tests caught the mutation
    survived: int  # Tests didn't catch
    score: float  # killed / total
    mutations: List[Tuple[Mutation, bool]]  # (mutation, was_killed)


class PatchMutationTester:
    """
    Mutation testing for patches.
    
    Creates mutant versions of patches and checks if tests
    would detect them (mutation score).
    """
    
    def __init__(self, seed: Optional[int] = None):
        if seed:
            random.seed(seed)
        
        # Mutation operators
        self.operators = {
            # Arithmetic
            "+": "-",
            "-": "+",
            "*": "/",
            "/": "*",
            "//": "/",
            "%": "//",
            "**": "*",
            
            # Comparison
            "==": "!=",
            "!=": "==",
            "<": "<=",
            ">": ">=",
            "<=": "<",
            ">=": ">",
            
            # Logical
            "and": "or",
            "or": "and",
            
            # Assignment compound
            "+=": "-=",
            "-=": "+=",
            "*=": "/=",
            "/=": "*=",
        }
        
        # Boundary mutations
        self.boundary_patterns = [
            (r'(\d+)', lambda m: str(int(m.group(1)) + 1)),  # n -> n+1
            (r'(\d+)', lambda m: str(int(m.group(1)) - 1)),  # n -> n-1
            (r'< (\d+)', lambda m: f'<= {m.group(1)}'),  # < n -> <= n
            (r'<= (\d+)', lambda m: f'< {m.group(1)}'),  # <= n -> < n
            (r'> (\d+)', lambda m: f'>= {m.group(1)}'),  # > n -> >= n
            (r'>= (\d+)', lambda m: f'> {m.group(1)}'),  # >= n -> > n
        ]
        
        self.stats = {
            "total_mutations": 0,
            "mutations_by_type": {}
        }
    
    def generate_mutations(
        self,
        patch: str,
        max_mutations: int = 10
    ) -> List[Mutation]:
        """Generate mutations of a patch"""
        mutations = []
        
        # Operator mutations
        for original, replacement in self.operators.items():
            pattern = rf'(?<![<>=!]){re.escape(original)}(?![<>=])'
            matches = list(re.finditer(pattern, patch))
            
            for match in matches[:2]:  # Limit per operator
                mutated = patch[:match.start()] + replacement + patch[match.end():]
                
                mutations.append(Mutation(
                    name=f"op_{original}_to_{replacement}_{match.start()}",
                    original=original,
                    mutated=mutated,
                    location=f"pos_{match.start()}",
                    type="operator"
                ))
                self.stats["total_mutations"] += 1
                
                if len(mutations) >= max_mutations:
                    break
            
            if len(mutations) >= max_mutations:
                break
        
        # Negation mutations
        negation_patterns = [
            (r'if\s+(\w+)', r'if not \1'),
            (r'if\s+not\s+(\w+)', r'if \1'),
            (r'while\s+(\w+)', r'while not \1'),
            (r'return\s+True', r'return False'),
            (r'return\s+False', r'return True'),
        ]
        
        for pattern, replacement in negation_patterns:
            if len(mutations) >= max_mutations:
                break
                
            match = re.search(pattern, patch)
            if match:
                mutated = re.sub(pattern, replacement, patch, count=1)
                mutations.append(Mutation(
                    name=f"negate_{pattern[:20]}",
                    original=match.group(0),
                    mutated=mutated,
                    location=f"pos_{match.start()}",
                    type="negation"
                ))
                self.stats["total_mutations"] += 1
        
        # Statement removal mutations
        removal_patterns = [
            r'^\+\s*(return\s+.+)$',
            r'^\+\s*(raise\s+.+)$',
            r'^\+\s*(assert\s+.+)$',
            r'^\+\s*(break)$',
            r'^\+\s*(continue)$',
        ]
        
        for pattern in removal_patterns:
            if len(mutations) >= max_mutations:
                break
                
            match = re.search(pattern, patch, re.MULTILINE)
            if match:
                # Remove the statement
                mutated = patch[:match.start()] + "+ pass" + patch[match.end():]
                mutations.append(Mutation(
                    name=f"remove_{match.group(1)[:20]}",
                    original=match.group(1),
                    mutated=mutated,
                    location=f"line_{patch[:match.start()].count(chr(10))}",
                    type="removal"
                ))
                self.stats["total_mutations"] += 1
        
        # Boundary mutations
        for pattern, replacer in self.boundary_patterns:
            if len(mutations) >= max_mutations:
                break
                
            match = re.search(pattern, patch)
            if match:
                try:
                    replacement = replacer(match)
                    mutated = patch[:match.start()] + replacement + patch[match.end():]
                    mutations.append(Mutation(
                        name=f"boundary_{match.group(0)[:10]}",
                        original=match.group(0),
                        mutated=mutated,
                        location=f"pos_{match.start()}",
                        type="boundary"
                    ))
                    self.stats["total_mutations"] += 1
                except (ValueError, IndexError):
                    pass
        
        return mutations[:max_mutations]
    
    def evaluate_mutation(
        self,
        original_patch: str,
        mutation: Mutation,
        expected_patch: str
    ) -> bool:
        """
        Check if a mutation would be caught.
        
        A mutation is "killed" if the mutated patch differs
        significantly from the expected behavior.
        """
        # Calculate similarity between mutated and expected
        mutated_patch = mutation.mutated
        
        # Simple heuristic: check if key parts are preserved
        # In real implementation, would run tests
        
        # Extract key assertions/returns from expected
        key_patterns = [
            r'return\s+.+',
            r'raise\s+.+',
            r'assert\s+.+',
            r'if\s+.+:',
        ]
        
        expected_keys = []
        for pattern in key_patterns:
            matches = re.findall(pattern, expected_patch)
            expected_keys.extend(matches)
        
        # Check if mutation changes any key pattern
        for key in expected_keys:
            if key in original_patch and key not in mutated_patch:
                return True  # Mutation killed - changed key behavior
        
        # Check operator changes in critical locations
        if mutation.type == "operator":
            # Operator mutations in comparisons are usually caught
            if any(op in mutation.original for op in ["==", "!=", "<", ">"]):
                return True
        
        # Negation mutations are usually caught
        if mutation.type == "negation":
            return True
        
        # Statement removals are usually caught
        if mutation.type == "removal":
            return True
        
        # Default: assume not killed (conservative)
        return False
    
    def run_mutation_testing(
        self,
        generated_patch: str,
        expected_patch: str,
        max_mutations: int = 10
    ) -> MutationResult:
        """
        Run mutation testing on a generated patch.
        
        Args:
            generated_patch: The patch generated by the agent
            expected_patch: The expected/gold patch
            max_mutations: Maximum mutations to generate
            
        Returns:
            MutationResult with mutation score
        """
        mutations = self.generate_mutations(generated_patch, max_mutations)
        
        results = []
        killed = 0
        survived = 0
        
        for mutation in mutations:
            is_killed = self.evaluate_mutation(
                generated_patch, mutation, expected_patch
            )
            
            results.append((mutation, is_killed))
            
            if is_killed:
                killed += 1
            else:
                survived += 1
            
            # Track by type
            mut_type = mutation.type
            if mut_type not in self.stats["mutations_by_type"]:
                self.stats["mutations_by_type"][mut_type] = {"total": 0, "killed": 0}
            self.stats["mutations_by_type"][mut_type]["total"] += 1
            if is_killed:
                self.stats["mutations_by_type"][mut_type]["killed"] += 1
        
        total = len(mutations)
        score = killed / total if total > 0 else 1.0
        
        return MutationResult(
            total_mutants=total,
            killed=killed,
            survived=survived,
            score=score,
            mutations=results
        )
    
    def analyze_survived_mutations(
        self,
        result: MutationResult
    ) -> List[Dict[str, Any]]:
        """Analyze mutations that survived (weren't caught)"""
        analysis = []
        
        for mutation, was_killed in result.mutations:
            if not was_killed:
                analysis.append({
                    "name": mutation.name,
                    "type": mutation.type,
                    "original": mutation.original,
                    "location": mutation.location,
                    "recommendation": self._get_recommendation(mutation)
                })
        
        return analysis
    
    def _get_recommendation(self, mutation: Mutation) -> str:
        """Get recommendation for improving test coverage"""
        recommendations = {
            "operator": "Add test cases that verify operator behavior",
            "boundary": "Add boundary value tests",
            "negation": "Add tests for both true and false conditions",
            "removal": "Add tests that verify the removed statement's effect",
        }
        return recommendations.get(mutation.type, "Add more comprehensive tests")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get mutation testing statistics"""
        return {
            **self.stats,
            "kill_rates_by_type": {
                t: (
                    v["killed"] / v["total"] if v["total"] > 0 else 0
                )
                for t, v in self.stats["mutations_by_type"].items()
            }
        }
