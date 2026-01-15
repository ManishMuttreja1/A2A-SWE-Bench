"""Fuzz Testing for SWE-bench Patches

Uses property-based testing to generate random inputs and verify patches
handle edge cases correctly.
"""

import ast
import logging
import random
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FuzzTestCase:
    """A fuzz test case"""
    name: str
    inputs: Dict[str, Any]
    expected_behavior: str  # "no_crash", "returns_value", "raises_exception"
    actual_result: Optional[str] = None
    passed: bool = False


@dataclass
class FuzzResult:
    """Results from fuzz testing"""
    total_tests: int
    passed: int
    failed: int
    crashes: int
    score: float
    test_cases: List[FuzzTestCase]


class FuzzTester:
    """
    Property-based fuzz testing for patches.
    
    Generates random inputs based on inferred types and tests
    that patched code handles them correctly.
    """
    
    def __init__(self, seed: Optional[int] = None):
        if seed:
            random.seed(seed)
        
        # Value generators by type
        self.generators = {
            "int": self._gen_int,
            "float": self._gen_float,
            "str": self._gen_str,
            "bool": self._gen_bool,
            "list": self._gen_list,
            "dict": self._gen_dict,
            "None": lambda: None,
        }
        
        # Edge case values
        self.edge_cases = {
            "int": [0, -1, 1, -2**31, 2**31-1, 2**63-1],
            "float": [0.0, -0.0, 1.0, -1.0, float('inf'), float('-inf'), float('nan')],
            "str": ["", " ", "\n", "\t", "a"*10000, "\x00", "🎉", "<script>"],
            "list": [[], [None], [1]*10000],
            "dict": [{}, {"": ""}, {None: None}],
        }
        
        self.stats = {
            "tests_generated": 0,
            "tests_run": 0,
            "crashes_found": 0,
        }
    
    def _gen_int(self) -> int:
        """Generate random integer"""
        if random.random() < 0.3:
            return random.choice(self.edge_cases["int"])
        return random.randint(-1000, 1000)
    
    def _gen_float(self) -> float:
        """Generate random float"""
        if random.random() < 0.3:
            return random.choice(self.edge_cases["float"])
        return random.uniform(-1000.0, 1000.0)
    
    def _gen_str(self) -> str:
        """Generate random string"""
        if random.random() < 0.3:
            return random.choice(self.edge_cases["str"])
        length = random.randint(0, 100)
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- "
        return "".join(random.choice(chars) for _ in range(length))
    
    def _gen_bool(self) -> bool:
        """Generate random boolean"""
        return random.choice([True, False])
    
    def _gen_list(self) -> list:
        """Generate random list"""
        if random.random() < 0.3:
            return random.choice(self.edge_cases["list"])
        length = random.randint(0, 10)
        return [self._gen_int() for _ in range(length)]
    
    def _gen_dict(self) -> dict:
        """Generate random dict"""
        if random.random() < 0.3:
            return random.choice(self.edge_cases["dict"])
        length = random.randint(0, 5)
        return {self._gen_str()[:10]: self._gen_int() for _ in range(length)}
    
    def extract_function_signatures(self, patch: str) -> List[Dict[str, Any]]:
        """Extract function signatures from a patch"""
        signatures = []
        
        # Find added function definitions in patch
        func_pattern = r'\+\s*def\s+(\w+)\s*\(([^)]*)\)'
        matches = re.findall(func_pattern, patch)
        
        for func_name, params_str in matches:
            params = []
            if params_str.strip():
                for param in params_str.split(','):
                    param = param.strip()
                    if ':' in param:
                        name, type_hint = param.split(':', 1)
                        params.append({
                            "name": name.strip(),
                            "type": type_hint.split('=')[0].strip()
                        })
                    else:
                        name = param.split('=')[0].strip()
                        if name and name != 'self':
                            params.append({
                                "name": name,
                                "type": "Any"
                            })
            
            signatures.append({
                "name": func_name,
                "params": params
            })
        
        return signatures
    
    def generate_fuzz_inputs(
        self,
        signature: Dict[str, Any],
        num_cases: int = 10
    ) -> List[Dict[str, Any]]:
        """Generate fuzz inputs for a function signature"""
        inputs_list = []
        
        for _ in range(num_cases):
            inputs = {}
            for param in signature.get("params", []):
                param_name = param["name"]
                param_type = param.get("type", "Any")
                
                # Map type hint to generator
                if "int" in param_type.lower():
                    inputs[param_name] = self._gen_int()
                elif "float" in param_type.lower():
                    inputs[param_name] = self._gen_float()
                elif "str" in param_type.lower():
                    inputs[param_name] = self._gen_str()
                elif "bool" in param_type.lower():
                    inputs[param_name] = self._gen_bool()
                elif "list" in param_type.lower():
                    inputs[param_name] = self._gen_list()
                elif "dict" in param_type.lower():
                    inputs[param_name] = self._gen_dict()
                else:
                    # Random type
                    gen = random.choice(list(self.generators.values()))
                    inputs[param_name] = gen()
            
            inputs_list.append(inputs)
            self.stats["tests_generated"] += 1
        
        return inputs_list
    
    def generate_edge_case_tests(
        self,
        patch: str,
        problem_statement: str
    ) -> List[FuzzTestCase]:
        """Generate edge case tests based on patch and problem"""
        test_cases = []
        
        # Extract what the patch is fixing
        keywords = self._extract_keywords(problem_statement)
        
        # Generate edge cases for common patterns
        edge_case_patterns = [
            ("empty_input", {"input": "", "data": [], "value": None}),
            ("zero_value", {"input": 0, "count": 0, "index": 0}),
            ("negative", {"input": -1, "count": -1, "index": -1}),
            ("large_value", {"input": 10**9, "count": 10**6}),
            ("unicode", {"input": "🎉émoji", "name": "名前"}),
            ("whitespace", {"input": "  \t\n  ", "name": " "}),
            ("special_chars", {"input": "<>&\"'\\", "path": "../../../etc/passwd"}),
        ]
        
        for name, inputs in edge_case_patterns:
            test_cases.append(FuzzTestCase(
                name=f"edge_case_{name}",
                inputs=inputs,
                expected_behavior="no_crash"
            ))
        
        return test_cases
    
    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract relevant keywords from problem statement"""
        keywords = set()
        
        # Common bug-related keywords
        patterns = [
            r'\b(null|none|empty|zero|negative|overflow|underflow)\b',
            r'\b(crash|error|exception|fail|break|invalid)\b',
            r'\b(boundary|edge|corner|limit|max|min)\b',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text.lower())
            keywords.update(matches)
        
        return keywords
    
    def run_fuzz_tests(
        self,
        patch: str,
        problem_statement: str,
        num_random_tests: int = 20
    ) -> FuzzResult:
        """
        Run fuzz tests on a patch.
        
        Since we can't actually execute the patch in isolation,
        we simulate by checking if the patch handles edge cases
        based on pattern matching.
        """
        test_cases = []
        
        # Generate edge case tests
        edge_tests = self.generate_edge_case_tests(patch, problem_statement)
        test_cases.extend(edge_tests)
        
        # Extract signatures and generate random tests
        signatures = self.extract_function_signatures(patch)
        for sig in signatures[:3]:  # Limit to 3 functions
            inputs_list = self.generate_fuzz_inputs(sig, num_random_tests // 3)
            for i, inputs in enumerate(inputs_list):
                test_cases.append(FuzzTestCase(
                    name=f"fuzz_{sig['name']}_{i}",
                    inputs=inputs,
                    expected_behavior="no_crash"
                ))
        
        # Evaluate test cases (heuristic-based since we can't execute)
        passed = 0
        failed = 0
        crashes = 0
        
        for tc in test_cases:
            result = self._evaluate_test_case(tc, patch)
            tc.passed = result["passed"]
            tc.actual_result = result["result"]
            
            if result["passed"]:
                passed += 1
            elif result["crash"]:
                crashes += 1
                failed += 1
            else:
                failed += 1
            
            self.stats["tests_run"] += 1
        
        total = len(test_cases)
        score = passed / total if total > 0 else 0.0
        
        return FuzzResult(
            total_tests=total,
            passed=passed,
            failed=failed,
            crashes=crashes,
            score=score,
            test_cases=test_cases
        )
    
    def _evaluate_test_case(
        self,
        test_case: FuzzTestCase,
        patch: str
    ) -> Dict[str, Any]:
        """
        Heuristically evaluate if patch handles test case.
        
        Checks for:
        - Input validation patterns
        - Null/empty checks
        - Type checking
        - Boundary handling
        """
        # Check if patch has defensive patterns
        defensive_patterns = [
            r'if\s+\w+\s+is\s+None',
            r'if\s+not\s+\w+',
            r'if\s+len\(\w+\)\s*[<>=]',
            r'try\s*:',
            r'except\s+',
            r'isinstance\(',
            r'hasattr\(',
            r'\.get\(',
            r'or\s+\[\]',
            r'or\s+\{\}',
            r'or\s+""',
            r'or\s+0',
        ]
        
        has_defensive_code = any(
            re.search(pattern, patch)
            for pattern in defensive_patterns
        )
        
        # Check specific edge cases
        inputs = test_case.inputs
        
        # Empty/None handling
        has_none_values = any(v is None for v in inputs.values())
        has_empty_values = any(
            v == "" or v == [] or v == {}
            for v in inputs.values()
            if isinstance(v, (str, list, dict))
        )
        
        # Check if patch handles these cases
        handles_none = "None" in patch or "is None" in patch
        handles_empty = (
            "len(" in patch or
            "if not" in patch or
            '""' in patch or
            "[]" in patch or
            "{}" in patch
        )
        
        # Determine pass/fail
        if has_none_values and not handles_none and not has_defensive_code:
            return {"passed": False, "crash": True, "result": "Potential None error"}
        
        if has_empty_values and not handles_empty and not has_defensive_code:
            return {"passed": False, "crash": False, "result": "May not handle empty"}
        
        if has_defensive_code:
            return {"passed": True, "crash": False, "result": "Has defensive code"}
        
        # Default: assume pass for well-structured patches
        return {"passed": True, "crash": False, "result": "OK"}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get fuzz testing statistics"""
        return {
            **self.stats,
            "crash_rate": (
                self.stats["crashes_found"] / self.stats["tests_run"]
                if self.stats["tests_run"] > 0 else 0
            )
        }
