"""
Multi-Run Executor - Runs benchmarks multiple times for statistical validity.

This addresses Gap 4: High variance in single runs makes comparisons fragile.
Now: Run N times, report mean ± std dev, use statistical tests for rankings.
"""

import asyncio
import logging
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Awaitable
import statistics

logger = logging.getLogger(__name__)


@dataclass
class RunConfig:
    """Configuration for multi-run evaluation."""
    num_runs: int = 3  # Minimum 3 runs for statistical validity
    num_tasks_per_run: int = 10
    model: str = "gpt-4o"
    random_seed_base: int = 42  # Different seed per run
    save_individual_runs: bool = True
    output_dir: Path = field(default_factory=lambda: Path("results/multi_run"))


@dataclass
class SingleRunResult:
    """Result from a single benchmark run."""
    run_id: int
    timestamp: str
    seed: int
    
    # Core metrics
    pass_rate: float  # Execution pass rate OR semantic match
    total_tasks: int
    tasks_passed: int
    tasks_failed: int
    
    # Additional metrics
    avg_execution_time: float = 0.0
    
    # Per-task results
    task_results: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "seed": self.seed,
            "pass_rate": self.pass_rate,
            "total_tasks": self.total_tasks,
            "tasks_passed": self.tasks_passed,
            "tasks_failed": self.tasks_failed,
            "avg_execution_time": self.avg_execution_time,
            "task_results": self.task_results
        }


@dataclass 
class MultiRunResult:
    """Aggregated results from multiple runs with statistical analysis."""
    model: str
    num_runs: int
    timestamp: str
    
    # Statistical metrics (the key improvement)
    mean_pass_rate: float
    std_dev_pass_rate: float
    min_pass_rate: float
    max_pass_rate: float
    confidence_interval_95: tuple  # (lower, upper)
    
    # Variance analysis
    variance: float
    coefficient_of_variation: float  # std/mean - shows relative variability
    
    # Individual runs
    runs: List[SingleRunResult] = field(default_factory=list)
    
    # Metadata
    config: Optional[RunConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "num_runs": self.num_runs,
            "timestamp": self.timestamp,
            "mean_pass_rate": self.mean_pass_rate,
            "std_dev_pass_rate": self.std_dev_pass_rate,
            "min_pass_rate": self.min_pass_rate,
            "max_pass_rate": self.max_pass_rate,
            "confidence_interval_95": self.confidence_interval_95,
            "variance": self.variance,
            "coefficient_of_variation": self.coefficient_of_variation,
            "runs": [r.to_dict() for r in self.runs],
            "statistical_validity": self._assess_validity()
        }
    
    def _assess_validity(self) -> Dict[str, Any]:
        """Assess statistical validity of results."""
        return {
            "sufficient_runs": self.num_runs >= 3,
            "low_variance": self.coefficient_of_variation < 0.2,  # <20% CV is acceptable
            "reliable_mean": self.std_dev_pass_rate < 0.1,  # Std dev < 10% is good
            "recommendation": self._get_recommendation()
        }
    
    def _get_recommendation(self) -> str:
        if self.num_runs < 3:
            return "UNRELIABLE: Need at least 3 runs for statistical validity"
        if self.coefficient_of_variation > 0.3:
            return "HIGH VARIANCE: Results vary significantly between runs. Increase num_runs or investigate causes."
        if self.std_dev_pass_rate > 0.15:
            return "MODERATE VARIANCE: Consider more runs for confident comparisons"
        return "STATISTICALLY VALID: Results are stable enough for model comparisons"


class MultiRunExecutor:
    """
    Executes benchmarks multiple times for statistical validity.
    
    Key improvement over single-run:
    - Reports mean ± std dev instead of single value
    - Computes confidence intervals
    - Warns if variance is too high for reliable comparison
    """
    
    def __init__(self, config: Optional[RunConfig] = None):
        self.config = config or RunConfig()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
    
    async def execute_multi_run(
        self,
        run_function: Callable[[int, int], Awaitable[Dict[str, Any]]],
        model: str = "gpt-4o"
    ) -> MultiRunResult:
        """
        Execute multiple runs of a benchmark.
        
        Args:
            run_function: Async function(run_id, seed) -> {pass_rate, task_results, ...}
            model: Model name for labeling
            
        Returns:
            MultiRunResult with statistical analysis
        """
        runs = []
        
        print(f"\n{'='*60}")
        print(f"MULTI-RUN EVALUATION: {model}")
        print(f"Runs: {self.config.num_runs}, Tasks per run: {self.config.num_tasks_per_run}")
        print(f"{'='*60}\n")
        
        for run_id in range(self.config.num_runs):
            seed = self.config.random_seed_base + run_id
            
            print(f"[Run {run_id + 1}/{self.config.num_runs}] Seed: {seed}")
            
            try:
                result = await run_function(run_id, seed)
                
                single_run = SingleRunResult(
                    run_id=run_id,
                    timestamp=datetime.now().isoformat(),
                    seed=seed,
                    pass_rate=result.get("pass_rate", 0),
                    total_tasks=result.get("total_tasks", 0),
                    tasks_passed=result.get("tasks_passed", 0),
                    tasks_failed=result.get("tasks_failed", 0),
                    avg_execution_time=result.get("avg_execution_time", 0),
                    task_results=result.get("task_results", [])
                )
                
                runs.append(single_run)
                
                print(f"  → Pass rate: {single_run.pass_rate:.1%}")
                
                # Save individual run
                if self.config.save_individual_runs:
                    self._save_run(single_run, model)
                
            except Exception as e:
                logger.error(f"Run {run_id} failed: {e}")
                print(f"  → FAILED: {e}")
        
        # Compute statistics
        multi_result = self._compute_statistics(runs, model)
        
        # Print summary
        self._print_summary(multi_result)
        
        # Save aggregated results
        self._save_multi_run(multi_result)
        
        return multi_result
    
    def _compute_statistics(
        self, 
        runs: List[SingleRunResult],
        model: str
    ) -> MultiRunResult:
        """Compute statistical metrics from runs."""
        if not runs:
            return MultiRunResult(
                model=model,
                num_runs=0,
                timestamp=datetime.now().isoformat(),
                mean_pass_rate=0,
                std_dev_pass_rate=0,
                min_pass_rate=0,
                max_pass_rate=0,
                confidence_interval_95=(0, 0),
                variance=0,
                coefficient_of_variation=0,
                runs=[]
            )
        
        pass_rates = [r.pass_rate for r in runs]
        
        mean = statistics.mean(pass_rates)
        
        if len(pass_rates) > 1:
            std_dev = statistics.stdev(pass_rates)
            variance = statistics.variance(pass_rates)
        else:
            std_dev = 0
            variance = 0
        
        # Coefficient of variation (normalized std dev)
        cv = std_dev / mean if mean > 0 else 0
        
        # 95% confidence interval (t-distribution approximation)
        # For small samples, use t-value ~2.0 for 95% CI
        t_value = 2.0  # Approximate for n=3
        margin = t_value * std_dev / (len(pass_rates) ** 0.5) if len(pass_rates) > 0 else 0
        ci_lower = max(0, mean - margin)
        ci_upper = min(1, mean + margin)
        
        return MultiRunResult(
            model=model,
            num_runs=len(runs),
            timestamp=datetime.now().isoformat(),
            mean_pass_rate=mean,
            std_dev_pass_rate=std_dev,
            min_pass_rate=min(pass_rates),
            max_pass_rate=max(pass_rates),
            confidence_interval_95=(ci_lower, ci_upper),
            variance=variance,
            coefficient_of_variation=cv,
            runs=runs,
            config=self.config
        )
    
    def _print_summary(self, result: MultiRunResult):
        """Print statistical summary."""
        validity = result._assess_validity()
        
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║              MULTI-RUN STATISTICAL SUMMARY                   ║
╚══════════════════════════════════════════════════════════════╝

Model: {result.model}
Runs: {result.num_runs}

┌────────────────────────────────────────────────────────────┐
│ PASS RATE: {result.mean_pass_rate:.1%} ± {result.std_dev_pass_rate:.1%}                          │
│ 95% CI: [{result.confidence_interval_95[0]:.1%}, {result.confidence_interval_95[1]:.1%}]                                  │
├────────────────────────────────────────────────────────────┤
│ Min: {result.min_pass_rate:.1%}  Max: {result.max_pass_rate:.1%}  Range: {(result.max_pass_rate - result.min_pass_rate):.1%}              │
│ Variance: {result.variance:.4f}                                        │
│ Coef. of Variation: {result.coefficient_of_variation:.1%}                              │
└────────────────────────────────────────────────────────────┘

Statistical Validity:
  Sufficient runs (≥3): {'✅' if validity['sufficient_runs'] else '❌'}
  Low variance (<20% CV): {'✅' if validity['low_variance'] else '❌'}
  Reliable mean (<10% std): {'✅' if validity['reliable_mean'] else '❌'}

Recommendation: {validity['recommendation']}
""")
    
    def _save_run(self, run: SingleRunResult, model: str):
        """Save individual run to file."""
        filename = f"{model}_run{run.run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.config.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(run.to_dict(), f, indent=2)
        
        logger.info(f"Saved run to {filepath}")
    
    def _save_multi_run(self, result: MultiRunResult):
        """Save aggregated multi-run results."""
        filename = f"{result.model}_multirun_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.config.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        
        logger.info(f"Saved multi-run results to {filepath}")
        print(f"\n💾 Results saved to: {filepath}")


# Mock run function for testing
async def mock_benchmark_run(run_id: int, seed: int) -> Dict[str, Any]:
    """Mock benchmark run for testing multi-run framework."""
    import random
    random.seed(seed)
    
    # Simulate ~30% pass rate with variance
    base_rate = 0.30
    variance = random.gauss(0, 0.05)  # ±5% variance
    pass_rate = max(0, min(1, base_rate + variance))
    
    num_tasks = 10
    passed = int(pass_rate * num_tasks)
    
    return {
        "pass_rate": pass_rate,
        "total_tasks": num_tasks,
        "tasks_passed": passed,
        "tasks_failed": num_tasks - passed,
        "avg_execution_time": random.uniform(1, 5),
        "task_results": [
            {"task_id": f"task-{i}", "passed": i < passed}
            for i in range(num_tasks)
        ]
    }
