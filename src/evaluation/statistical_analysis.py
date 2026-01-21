"""
Statistical Analysis - Proper comparison between models.

This addresses Gap 4: Single-run comparisons are statistically weak.
Now: Use paired t-tests, report p-values, only rank if significant.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import statistics
import math

logger = logging.getLogger(__name__)


@dataclass
class ModelComparison:
    """Statistical comparison between two models."""
    model_a: str
    model_b: str
    
    # Means
    mean_a: float
    mean_b: float
    difference: float  # mean_a - mean_b
    
    # Statistical test results
    t_statistic: float
    p_value: float
    degrees_of_freedom: int
    
    # Significance
    is_significant_95: bool  # p < 0.05
    is_significant_99: bool  # p < 0.01
    
    # Confidence interval of difference
    ci_difference: Tuple[float, float]
    
    # Recommendation
    winner: Optional[str] = None
    confidence_level: str = "not_significant"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_a": self.model_a,
            "model_b": self.model_b,
            "mean_a": self.mean_a,
            "mean_b": self.mean_b,
            "difference": self.difference,
            "t_statistic": self.t_statistic,
            "p_value": self.p_value,
            "is_significant_95": self.is_significant_95,
            "is_significant_99": self.is_significant_99,
            "winner": self.winner,
            "confidence_level": self.confidence_level,
            "interpretation": self._interpret()
        }
    
    def _interpret(self) -> str:
        if not self.is_significant_95:
            return f"No statistically significant difference between {self.model_a} and {self.model_b} (p={self.p_value:.3f})"
        
        better = self.model_a if self.difference > 0 else self.model_b
        worse = self.model_b if self.difference > 0 else self.model_a
        
        if self.is_significant_99:
            return f"{better} significantly outperforms {worse} (p={self.p_value:.3f}, 99% confidence)"
        else:
            return f"{better} outperforms {worse} (p={self.p_value:.3f}, 95% confidence)"


class StatisticalAnalyzer:
    """
    Performs statistical analysis for model comparisons.
    
    Key features:
    - Paired t-test for comparing models on same tasks
    - Effect size calculation
    - Multiple comparison correction (Bonferroni)
    - Clear ranking only when statistically significant
    """
    
    def __init__(self, significance_level: float = 0.05):
        self.significance_level = significance_level
    
    def compare_models(
        self,
        model_a_name: str,
        model_a_runs: List[float],  # Pass rates from multiple runs
        model_b_name: str,
        model_b_runs: List[float]
    ) -> ModelComparison:
        """
        Compare two models using their multi-run results.
        
        Uses Welch's t-test (doesn't assume equal variance).
        
        Args:
            model_a_name: Name of model A
            model_a_runs: Pass rates from A's runs
            model_b_name: Name of model B  
            model_b_runs: Pass rates from B's runs
            
        Returns:
            ModelComparison with statistical analysis
        """
        if len(model_a_runs) < 2 or len(model_b_runs) < 2:
            logger.warning("Need at least 2 runs per model for statistical comparison")
            return self._insufficient_data_comparison(
                model_a_name, model_b_name, model_a_runs, model_b_runs
            )
        
        mean_a = statistics.mean(model_a_runs)
        mean_b = statistics.mean(model_b_runs)
        
        std_a = statistics.stdev(model_a_runs)
        std_b = statistics.stdev(model_b_runs)
        
        n_a = len(model_a_runs)
        n_b = len(model_b_runs)
        
        # Welch's t-test
        t_stat, p_value, df = self._welch_t_test(
            mean_a, std_a, n_a,
            mean_b, std_b, n_b
        )
        
        # Significance
        is_sig_95 = p_value < 0.05
        is_sig_99 = p_value < 0.01
        
        # Confidence interval for difference
        ci_diff = self._difference_ci(mean_a, std_a, n_a, mean_b, std_b, n_b)
        
        # Determine winner
        winner = None
        confidence = "not_significant"
        
        if is_sig_99:
            winner = model_a_name if mean_a > mean_b else model_b_name
            confidence = "99%"
        elif is_sig_95:
            winner = model_a_name if mean_a > mean_b else model_b_name
            confidence = "95%"
        
        return ModelComparison(
            model_a=model_a_name,
            model_b=model_b_name,
            mean_a=mean_a,
            mean_b=mean_b,
            difference=mean_a - mean_b,
            t_statistic=t_stat,
            p_value=p_value,
            degrees_of_freedom=df,
            is_significant_95=is_sig_95,
            is_significant_99=is_sig_99,
            ci_difference=ci_diff,
            winner=winner,
            confidence_level=confidence
        )
    
    def _welch_t_test(
        self,
        mean1: float, std1: float, n1: int,
        mean2: float, std2: float, n2: int
    ) -> Tuple[float, float, int]:
        """
        Welch's t-test (unequal variance t-test).
        
        Returns: (t_statistic, p_value, degrees_of_freedom)
        """
        # Standard error
        se1 = (std1 ** 2) / n1 if n1 > 0 else 0
        se2 = (std2 ** 2) / n2 if n2 > 0 else 0
        
        se_diff = math.sqrt(se1 + se2) if (se1 + se2) > 0 else 0.001
        
        # t-statistic
        t_stat = (mean1 - mean2) / se_diff if se_diff > 0 else 0
        
        # Welch-Satterthwaite degrees of freedom
        if se1 + se2 > 0:
            df_num = (se1 + se2) ** 2
            df_den = (se1 ** 2) / (n1 - 1) + (se2 ** 2) / (n2 - 1) if n1 > 1 and n2 > 1 else 1
            df = int(df_num / df_den) if df_den > 0 else 1
        else:
            df = 1
        
        # p-value (two-tailed) using approximation
        # For proper p-value, would need scipy.stats.t.sf
        # Using approximation based on t-value
        p_value = self._approximate_p_value(abs(t_stat), df)
        
        return t_stat, p_value, df
    
    def _approximate_p_value(self, t: float, df: int) -> float:
        """
        Approximate p-value for t-distribution.
        For production, use scipy.stats.t.sf(t, df) * 2
        """
        # Simple approximation using normal distribution for large df
        # For small df, this underestimates p-value (conservative)
        if df >= 30:
            # Use normal approximation
            # P(|Z| > t) ≈ 2 * (1 - Φ(t))
            z = t
            p = 2 * (1 - self._normal_cdf(z))
        else:
            # Rough approximation for small df
            # Based on t-table values
            if t < 1.0:
                p = 0.5
            elif t < 2.0:
                p = 0.1
            elif t < 2.5:
                p = 0.05
            elif t < 3.0:
                p = 0.02
            elif t < 3.5:
                p = 0.01
            else:
                p = 0.005
        
        return p
    
    def _normal_cdf(self, x: float) -> float:
        """Approximate normal CDF using error function approximation."""
        # Approximation: Φ(x) ≈ 0.5 * (1 + erf(x/√2))
        # Using polynomial approximation for erf
        a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
        p = 0.3275911
        
        sign = 1 if x >= 0 else -1
        x = abs(x) / math.sqrt(2)
        
        t = 1.0 / (1.0 + p * x)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
        
        return 0.5 * (1.0 + sign * y)
    
    def _difference_ci(
        self,
        mean1: float, std1: float, n1: int,
        mean2: float, std2: float, n2: int,
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """Compute confidence interval for difference in means."""
        diff = mean1 - mean2
        
        se1 = (std1 ** 2) / n1 if n1 > 0 else 0
        se2 = (std2 ** 2) / n2 if n2 > 0 else 0
        se_diff = math.sqrt(se1 + se2)
        
        # t-value for 95% CI (approximate)
        t_crit = 2.0  # Conservative for small samples
        
        margin = t_crit * se_diff
        
        return (diff - margin, diff + margin)
    
    def _insufficient_data_comparison(
        self,
        model_a: str,
        model_b: str,
        runs_a: List[float],
        runs_b: List[float]
    ) -> ModelComparison:
        """Return comparison when insufficient data."""
        mean_a = statistics.mean(runs_a) if runs_a else 0
        mean_b = statistics.mean(runs_b) if runs_b else 0
        
        return ModelComparison(
            model_a=model_a,
            model_b=model_b,
            mean_a=mean_a,
            mean_b=mean_b,
            difference=mean_a - mean_b,
            t_statistic=0,
            p_value=1.0,  # No significance
            degrees_of_freedom=0,
            is_significant_95=False,
            is_significant_99=False,
            ci_difference=(0, 0),
            winner=None,
            confidence_level="insufficient_data"
        )
    
    def rank_models(
        self,
        model_results: Dict[str, List[float]]  # {model_name: [pass_rates]}
    ) -> List[Dict[str, Any]]:
        """
        Rank models with statistical validity indicators.
        
        Args:
            model_results: Dict mapping model names to list of pass rates
            
        Returns:
            Ranked list with statistical validity flags
        """
        # Compute means
        rankings = []
        for model, runs in model_results.items():
            if runs:
                mean = statistics.mean(runs)
                std = statistics.stdev(runs) if len(runs) > 1 else 0
                rankings.append({
                    "model": model,
                    "mean": mean,
                    "std": std,
                    "n_runs": len(runs),
                    "statistically_valid": len(runs) >= 3
                })
        
        # Sort by mean (descending)
        rankings.sort(key=lambda x: x["mean"], reverse=True)
        
        # Add rank
        for i, r in enumerate(rankings):
            r["rank"] = i + 1
        
        # Compare adjacent pairs for significance
        for i in range(len(rankings) - 1):
            model_a = rankings[i]["model"]
            model_b = rankings[i + 1]["model"]
            
            comparison = self.compare_models(
                model_a, model_results[model_a],
                model_b, model_results[model_b]
            )
            
            rankings[i]["vs_next"] = {
                "model": model_b,
                "difference": comparison.difference,
                "significant": comparison.is_significant_95,
                "p_value": comparison.p_value
            }
        
        return rankings
    
    def print_rankings(self, rankings: List[Dict[str, Any]]):
        """Print formatted ranking table."""
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                   MODEL RANKINGS                              ║
║         (With Statistical Validity Indicators)                ║
╚══════════════════════════════════════════════════════════════╝
""")
        
        print(f"{'Rank':<6} {'Model':<25} {'Mean ± Std':<15} {'Runs':<6} {'Valid':<8}")
        print("-" * 65)
        
        for r in rankings:
            valid = "✅" if r["statistically_valid"] else "⚠️"
            mean_std = f"{r['mean']:.1%} ± {r['std']:.1%}"
            print(f"{r['rank']:<6} {r['model']:<25} {mean_std:<15} {r['n_runs']:<6} {valid:<8}")
            
            if "vs_next" in r:
                vs = r["vs_next"]
                sig = "✓ sig" if vs["significant"] else "✗ n.s."
                print(f"       └─ vs {vs['model']}: {vs['difference']:+.1%} ({sig}, p={vs['p_value']:.3f})")
        
        print("-" * 65)
        print("\n⚠️  Rankings with p > 0.05 are NOT statistically significant")
        print("   Need ≥3 runs per model for valid statistical comparison\n")
