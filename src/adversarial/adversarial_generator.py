"""Adversarial Test Generator using LLM

Uses language models to generate edge cases and adversarial inputs
designed to break naive patches.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AdversarialTest:
    """An adversarial test case"""
    name: str
    description: str
    test_code: str
    category: str  # "edge_case", "boundary", "malformed", "race_condition"
    severity: str  # "low", "medium", "high"


class AdversarialGenerator:
    """
    LLM-powered adversarial test generation.
    
    Generates edge cases, boundary conditions, and attack vectors
    that might break patches.
    """
    
    def __init__(self, client=None):
        self.client = client  # OpenAI client
        self.stats = {
            "tests_generated": 0,
            "categories": {}
        }
    
    async def generate_edge_cases(
        self,
        problem_statement: str,
        patch: str,
        num_cases: int = 5
    ) -> List[AdversarialTest]:
        """Generate edge cases using LLM"""
        
        if self.client:
            return await self._generate_with_llm(problem_statement, patch, num_cases)
        else:
            return self._generate_heuristic(problem_statement, patch, num_cases)
    
    async def _generate_with_llm(
        self,
        problem: str,
        patch: str,
        num_cases: int
    ) -> List[AdversarialTest]:
        """Generate adversarial tests using LLM"""
        prompt = f"""You are a security researcher testing code patches for vulnerabilities.

Problem being fixed:
{problem[:500]}

Patch:
{patch[:1000]}

Generate {num_cases} adversarial test cases that might break this patch.
Focus on:
1. Edge cases (empty, null, boundary values)
2. Malformed inputs
3. Type confusion
4. Resource exhaustion
5. Injection attacks

For each test, provide:
- Name (short identifier)
- Description (what it tests)
- Category (edge_case, boundary, malformed, injection, resource)
- Test input or scenario

Format as:
TEST 1:
Name: <name>
Description: <description>
Category: <category>
Input: <test input or scenario>
---"""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            
            content = response.choices[0].message.content
            return self._parse_llm_response(content)
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._generate_heuristic(problem, patch, num_cases)
    
    def _parse_llm_response(self, content: str) -> List[AdversarialTest]:
        """Parse LLM response into AdversarialTest objects"""
        tests = []
        
        # Split by TEST markers
        test_blocks = re.split(r'TEST\s+\d+:', content)
        
        for block in test_blocks[1:]:  # Skip first empty block
            try:
                name_match = re.search(r'Name:\s*(.+)', block)
                desc_match = re.search(r'Description:\s*(.+)', block)
                cat_match = re.search(r'Category:\s*(.+)', block)
                input_match = re.search(r'Input:\s*(.+)', block, re.DOTALL)
                
                if name_match and desc_match:
                    tests.append(AdversarialTest(
                        name=name_match.group(1).strip(),
                        description=desc_match.group(1).strip(),
                        test_code=input_match.group(1).strip() if input_match else "",
                        category=cat_match.group(1).strip().lower() if cat_match else "edge_case",
                        severity="medium"
                    ))
                    self.stats["tests_generated"] += 1
                    
            except Exception as e:
                logger.warning(f"Failed to parse test block: {e}")
        
        return tests
    
    def _generate_heuristic(
        self,
        problem: str,
        patch: str,
        num_cases: int
    ) -> List[AdversarialTest]:
        """Generate adversarial tests using heuristics (no LLM)"""
        tests = []
        
        # Common adversarial patterns
        adversarial_patterns = [
            AdversarialTest(
                name="null_input",
                description="Test with None/null input",
                test_code="input = None",
                category="edge_case",
                severity="high"
            ),
            AdversarialTest(
                name="empty_string",
                description="Test with empty string",
                test_code='input = ""',
                category="edge_case",
                severity="medium"
            ),
            AdversarialTest(
                name="empty_list",
                description="Test with empty list",
                test_code="input = []",
                category="edge_case",
                severity="medium"
            ),
            AdversarialTest(
                name="negative_number",
                description="Test with negative number",
                test_code="input = -1",
                category="boundary",
                severity="medium"
            ),
            AdversarialTest(
                name="large_number",
                description="Test with very large number",
                test_code="input = 10**18",
                category="boundary",
                severity="medium"
            ),
            AdversarialTest(
                name="unicode_input",
                description="Test with unicode characters",
                test_code='input = "🎉émoji名前"',
                category="malformed",
                severity="low"
            ),
            AdversarialTest(
                name="sql_injection",
                description="Test SQL injection attempt",
                test_code='input = "\'; DROP TABLE users; --"',
                category="injection",
                severity="high"
            ),
            AdversarialTest(
                name="path_traversal",
                description="Test path traversal attempt",
                test_code='input = "../../../etc/passwd"',
                category="injection",
                severity="high"
            ),
            AdversarialTest(
                name="large_payload",
                description="Test with large payload",
                test_code='input = "x" * 1000000',
                category="resource",
                severity="medium"
            ),
            AdversarialTest(
                name="special_chars",
                description="Test with special characters",
                test_code='input = "<>&\\"\\\'\\\\\\x00\\n\\r\\t"',
                category="malformed",
                severity="medium"
            ),
        ]
        
        # Select based on problem context
        problem_lower = problem.lower()
        
        selected = []
        for test in adversarial_patterns:
            # Prioritize relevant tests
            if "string" in problem_lower and test.category in ["edge_case", "malformed"]:
                selected.append(test)
            elif "number" in problem_lower or "int" in problem_lower:
                if test.category == "boundary":
                    selected.append(test)
            elif "list" in problem_lower or "array" in problem_lower:
                if "empty" in test.name or "large" in test.name:
                    selected.append(test)
            elif "path" in problem_lower or "file" in problem_lower:
                if test.category == "injection":
                    selected.append(test)
            else:
                selected.append(test)
            
            if len(selected) >= num_cases:
                break
        
        # Fill remaining with general tests
        while len(selected) < num_cases and len(selected) < len(adversarial_patterns):
            for test in adversarial_patterns:
                if test not in selected:
                    selected.append(test)
                    if len(selected) >= num_cases:
                        break
        
        self.stats["tests_generated"] += len(selected)
        return selected[:num_cases]
    
    def evaluate_patch_against_tests(
        self,
        patch: str,
        tests: List[AdversarialTest]
    ) -> Dict[str, Any]:
        """
        Evaluate if patch handles adversarial tests.
        
        Uses heuristic analysis since we can't execute.
        """
        results = {
            "total": len(tests),
            "likely_handled": 0,
            "likely_vulnerable": 0,
            "unknown": 0,
            "details": []
        }
        
        for test in tests:
            handled = self._check_if_handled(patch, test)
            
            if handled == "yes":
                results["likely_handled"] += 1
            elif handled == "no":
                results["likely_vulnerable"] += 1
            else:
                results["unknown"] += 1
            
            results["details"].append({
                "test": test.name,
                "category": test.category,
                "handled": handled
            })
        
        results["score"] = (
            results["likely_handled"] / results["total"]
            if results["total"] > 0 else 0
        )
        
        return results
    
    def _check_if_handled(self, patch: str, test: AdversarialTest) -> str:
        """Check if patch likely handles an adversarial test"""
        
        # Defensive patterns for each category
        category_patterns = {
            "edge_case": [
                r'if\s+\w+\s+is\s+None',
                r'if\s+not\s+\w+',
                r'if\s+len\(\w+\)',
                r'\.get\(',
                r'or\s+\[\]',
                r'or\s+""',
            ],
            "boundary": [
                r'if\s+\w+\s*[<>]=?\s*\d+',
                r'max\(',
                r'min\(',
                r'clamp',
                r'bound',
            ],
            "malformed": [
                r'try\s*:',
                r'except\s+',
                r'validate',
                r'sanitize',
                r'escape',
            ],
            "injection": [
                r'escape',
                r'quote',
                r'sanitize',
                r'parameterized',
                r'prepared',
                r'safe_',
            ],
            "resource": [
                r'limit',
                r'max_',
                r'timeout',
                r'[:100]',  # Slicing
            ],
        }
        
        patterns = category_patterns.get(test.category, [])
        
        for pattern in patterns:
            if re.search(pattern, patch, re.IGNORECASE):
                return "yes"
        
        # Check for general defensive code
        if re.search(r'try\s*:', patch) and re.search(r'except', patch):
            return "maybe"
        
        return "unknown"
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get generator statistics"""
        return self.stats
