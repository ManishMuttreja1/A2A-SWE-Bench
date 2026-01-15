"""Adversarial Testing Framework for SWE-bench A2A

Implements:
- Fuzz testing (property-based tests)
- Adversarial input generation
- Patch mutation testing
- Semantic equivalence attacks
"""

from .fuzz_tester import FuzzTester
from .adversarial_generator import AdversarialGenerator
from .mutation_tester import PatchMutationTester
from .evaluator import AdversarialEvaluator

__all__ = [
    "FuzzTester",
    "AdversarialGenerator",
    "PatchMutationTester",
    "AdversarialEvaluator",
]
