"""
Result Collector - Aggregates and formats execution results.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Single execution result."""
    instance_id: str
    execution_pass: bool  # The key metric: did tests pass?
    exit_code: int
    tests_passed: int
    tests_failed: int
    execution_time: float
    error: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    repo: str = ""
    base_commit: str = ""
    
    # Explicitly NOT including semantic_match - that's the old metric
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BatchExecutionResult:
    """Aggregated results from a batch execution."""
    timestamp: str
    model: str
    num_tasks: int
    
    # EXECUTION-BASED metrics (replacing semantic F1)
    execution_pass_rate: float  # % of tasks that passed
    total_passed: int
    total_failed: int
    total_tests_passed: int
    total_tests_failed: int
    avg_execution_time: float
    
    # Individual results
    results: List[ExecutionResult] = field(default_factory=list)
    
    # Metadata
    metric_type: str = "execution"  # Explicitly mark metric type
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["results"] = [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.results]
        return d


class ResultCollector:
    """
    Collects and aggregates execution results.
    
    Key difference from semantic scoring:
    - Reports pass_rate (binary) instead of avg_f1 (continuous)
    - Results are based on actual test execution, not text similarity
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path("results/execution")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results: List[ExecutionResult] = []
    
    def add_result(self, result: Dict[str, Any]) -> ExecutionResult:
        """Add a single execution result."""
        exec_result = ExecutionResult(
            instance_id=result.get("instance_id", "unknown"),
            execution_pass=result.get("execution_pass", result.get("success", False)),
            exit_code=result.get("exit_code", -1),
            tests_passed=result.get("tests_passed", 0),
            tests_failed=result.get("tests_failed", 0),
            execution_time=result.get("execution_time", 0),
            error=result.get("error"),
            stdout=result.get("stdout", "")[:1000],  # Truncate
            stderr=result.get("stderr", "")[:1000],
            repo=result.get("repo", ""),
            base_commit=result.get("base_commit", "")
        )
        self.results.append(exec_result)
        return exec_result
    
    def add_results(self, results: List[Dict[str, Any]]) -> List[ExecutionResult]:
        """Add multiple results."""
        return [self.add_result(r) for r in results]
    
    def compute_summary(self, model: str = "unknown") -> BatchExecutionResult:
        """Compute summary metrics from collected results."""
        if not self.results:
            return BatchExecutionResult(
                timestamp=datetime.now().isoformat(),
                model=model,
                num_tasks=0,
                execution_pass_rate=0.0,
                total_passed=0,
                total_failed=0,
                total_tests_passed=0,
                total_tests_failed=0,
                avg_execution_time=0.0,
                results=[]
            )
        
        passed = sum(1 for r in self.results if r.execution_pass)
        total = len(self.results)
        
        return BatchExecutionResult(
            timestamp=datetime.now().isoformat(),
            model=model,
            num_tasks=total,
            execution_pass_rate=passed / total,
            total_passed=passed,
            total_failed=total - passed,
            total_tests_passed=sum(r.tests_passed for r in self.results),
            total_tests_failed=sum(r.tests_failed for r in self.results),
            avg_execution_time=sum(r.execution_time for r in self.results) / total,
            results=self.results,
            metric_type="execution"
        )
    
    def save_results(self, model: str = "unknown", filename: Optional[str] = None) -> Path:
        """Save results to JSON file."""
        summary = self.compute_summary(model)
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"execution_results_{model}_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(summary.to_dict(), f, indent=2, default=str)
        
        logger.info(f"Saved execution results to {filepath}")
        return filepath
    
    def print_summary(self, model: str = "unknown"):
        """Print execution summary to console."""
        summary = self.compute_summary(model)
        
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║            EXECUTION-BASED RESULTS (NOT Semantic F1)         ║
╚══════════════════════════════════════════════════════════════╝

Model: {summary.model}
Tasks: {summary.num_tasks}
Timestamp: {summary.timestamp}

┌────────────────────────────────────────────────────────────┐
│ EXECUTION PASS RATE: {summary.execution_pass_rate:.1%}                              │
│ (This is binary pass/fail, NOT semantic similarity)        │
├────────────────────────────────────────────────────────────┤
│ Passed: {summary.total_passed}/{summary.num_tasks}                                           │
│ Failed: {summary.total_failed}/{summary.num_tasks}                                           │
│ Tests Passed: {summary.total_tests_passed}                                       │
│ Tests Failed: {summary.total_tests_failed}                                       │
│ Avg Execution Time: {summary.avg_execution_time:.1f}s                             │
└────────────────────────────────────────────────────────────┘

Per-task results:
""")
        for r in summary.results:
            status = "✅ PASS" if r.execution_pass else "❌ FAIL"
            print(f"  {r.instance_id}: {status} ({r.tests_passed} passed, {r.tests_failed} failed)")
    
    def clear(self):
        """Clear collected results."""
        self.results = []


def compare_semantic_vs_execution(
    semantic_results: List[Dict[str, Any]],
    execution_results: List[ExecutionResult]
) -> Dict[str, Any]:
    """
    Compare semantic F1 scores with actual execution results.
    
    This highlights the gap between "looks correct" and "actually works".
    """
    comparisons = []
    
    semantic_by_id = {r["instance_id"]: r for r in semantic_results}
    
    for exec_result in execution_results:
        instance_id = exec_result.instance_id
        semantic = semantic_by_id.get(instance_id, {})
        
        semantic_score = semantic.get("semantic_match", semantic.get("fuzzy_recall", 0))
        
        comparisons.append({
            "instance_id": instance_id,
            "semantic_f1": semantic_score,
            "execution_pass": exec_result.execution_pass,
            "gap": "HIGH_SEMANTIC_FAIL_EXEC" if semantic_score > 0.5 and not exec_result.execution_pass else
                   "LOW_SEMANTIC_PASS_EXEC" if semantic_score < 0.3 and exec_result.execution_pass else
                   "CONSISTENT"
        })
    
    # Compute gap statistics
    high_semantic_but_fail = sum(1 for c in comparisons if c["gap"] == "HIGH_SEMANTIC_FAIL_EXEC")
    low_semantic_but_pass = sum(1 for c in comparisons if c["gap"] == "LOW_SEMANTIC_PASS_EXEC")
    
    return {
        "comparisons": comparisons,
        "high_semantic_fail_execution": high_semantic_but_fail,
        "low_semantic_pass_execution": low_semantic_but_pass,
        "metric_gap_rate": high_semantic_but_fail / len(comparisons) if comparisons else 0,
        "interpretation": f"{high_semantic_but_fail} patches looked correct but failed execution - "
                         f"semantic F1 overestimated by {high_semantic_but_fail/len(comparisons)*100:.0f}%"
                         if comparisons else "No data"
    }
