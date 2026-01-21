#!/usr/bin/env python3
"""
Compute Trajectory-Based Process Score for SWE-bench A2A Results

Implements the composite score S from the paper:
S = 0.35*s_correct + 0.20*s_process + 0.15*s_efficiency + 0.15*s_collab + 0.10*s_understand + 0.05*s_adapt
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from enum import Enum


class MetricCategory(str, Enum):
    """Metric categories for process scoring"""
    CORRECTNESS = "correctness"
    PROCESS = "process"
    EFFICIENCY = "efficiency"
    COLLABORATION = "collaboration"
    UNDERSTANDING = "understanding"
    ADAPTATION = "adaptation"


def compute_process_score_for_result(
    result: Dict[str, Any],
    trajectory: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Compute the full process score for a single result.
    
    Since we don't have full trajectories stored, we estimate from available data.
    """
    
    # Extract what we have
    semantic_match = 0.0
    if result.get('success') and 'comparison' in result:
        semantic_match = result['comparison'].get('fuzzy_recall', 0.0)
    
    elapsed = result.get('elapsed', 30.0)  # Default 30s
    
    # Build task_result for correctness scoring
    task_result = {
        "passed": semantic_match >= 0.95,  # Consider 95%+ as "passed"
        "tests_passed": int(semantic_match * 10),  # Estimate
        "tests_failed": int((1 - semantic_match) * 10),
        "execution_time": elapsed,
        "patch_rejected": not result.get('success', False),
    }
    
    # Build minimal trajectory from what we know
    # In a full implementation, this would come from actual agent logs
    if trajectory is None:
        trajectory = [
            {"type": "read_problem", "timestamp": 0},
            {"type": "analyze_code", "timestamp": 1},
            {"type": "generate_patch", "timestamp": 2},
            {"type": "submit_patch", "timestamp": 3},
        ]
        
        # If we have elapsed time, infer more actions
        if elapsed > 10:
            trajectory.insert(2, {"type": "search_codebase", "timestamp": 1.5})
        if elapsed > 20:
            trajectory.insert(3, {"type": "test_locally", "timestamp": 2.5})
    
    # Build reproduction metrics (estimated)
    reproduction_metrics = {
        "attempted": False,  # We didn't enforce this
        "verified": False,
        "attempts": 0
    }
    
    # Build dialogue metrics (estimated)
    dialogue_metrics = {
        "total_questions": 0,  # No dialogue in current implementation
        "relevant_questions": 0,
        "information_revealed": 0.0,
        "information_gain_efficiency": 0.0,
        "requirements_quality_score": 0.3  # Baseline from problem statement
    }
    
    # Build review metrics (estimated)
    review_metrics = {
        "iterations": 1,
        "total_issues": 0,
        "issues_resolved": 0,
        "feedback_incorporation_score": 0.0,
        "iteration_scores": [semantic_match]
    }
    
    # Calculate individual scores
    scores = {}
    
    # 1. Correctness (0.35) - based on semantic match
    if semantic_match >= 0.95:
        scores[MetricCategory.CORRECTNESS] = 1.0
    elif semantic_match >= 0.7:
        scores[MetricCategory.CORRECTNESS] = 0.7 + (semantic_match - 0.7) * 1.0
    elif semantic_match >= 0.5:
        scores[MetricCategory.CORRECTNESS] = 0.5 + (semantic_match - 0.5) * 1.0
    else:
        scores[MetricCategory.CORRECTNESS] = semantic_match * 1.0
    
    # 2. Process (0.20) - penalize for no reproduction gate
    scores[MetricCategory.PROCESS] = 0.3  # Baseline for direct patch (no repro)
    if result.get('comparison', {}).get('files_correct', 0) == 1.0:
        scores[MetricCategory.PROCESS] += 0.2  # Correct file identification
    if semantic_match > 0.5:
        scores[MetricCategory.PROCESS] += 0.2  # Good semantic match implies some exploration
    
    # 3. Efficiency (0.15) - based on time and tokens
    if elapsed < 5:
        scores[MetricCategory.EFFICIENCY] = 1.0
    elif elapsed < 15:
        scores[MetricCategory.EFFICIENCY] = 0.8
    elif elapsed < 30:
        scores[MetricCategory.EFFICIENCY] = 0.6
    else:
        scores[MetricCategory.EFFICIENCY] = max(0.3, 1.0 - (elapsed - 30) / 100)
    
    # 4. Collaboration (0.15) - N/A for single-shot prompting
    scores[MetricCategory.COLLABORATION] = 0.3  # Baseline for no dialogue
    
    # 5. Understanding (0.10) - inferred from file/patch correctness
    if result.get('comparison', {}).get('files_correct', 0) == 1.0:
        scores[MetricCategory.UNDERSTANDING] = 0.6 + semantic_match * 0.4
    else:
        scores[MetricCategory.UNDERSTANDING] = semantic_match * 0.5
    
    # 6. Adaptation (0.05) - N/A for single-shot (no feedback loop)
    scores[MetricCategory.ADAPTATION] = 0.5  # Neutral
    
    # Calculate weighted total
    weights = {
        MetricCategory.CORRECTNESS: 0.35,
        MetricCategory.PROCESS: 0.20,
        MetricCategory.EFFICIENCY: 0.15,
        MetricCategory.COLLABORATION: 0.15,
        MetricCategory.UNDERSTANDING: 0.10,
        MetricCategory.ADAPTATION: 0.05
    }
    
    total_score = sum(scores[cat] * weights[cat] for cat in MetricCategory)
    
    return {
        "total_score": total_score,
        "scores": {cat.value: round(scores[cat], 3) for cat in MetricCategory},
        "weights": {cat.value: weights[cat] for cat in MetricCategory},
        "grade": _score_to_grade(total_score),
        "semantic_match": semantic_match,
        "notes": {
            "reproduction_gate": "not_enforced",
            "dialogue": "not_used",
            "review_loop": "not_used"
        }
    }


def _score_to_grade(score: float) -> str:
    """Convert numerical score to letter grade"""
    if score >= 0.95: return "A+"
    if score >= 0.90: return "A"
    if score >= 0.85: return "A-"
    if score >= 0.80: return "B+"
    if score >= 0.75: return "B"
    if score >= 0.70: return "B-"
    if score >= 0.65: return "C+"
    if score >= 0.60: return "C"
    if score >= 0.55: return "C-"
    if score >= 0.50: return "D"
    return "F"


def process_results_file(filepath: str) -> Dict[str, Any]:
    """Process an existing results file and add process scores"""
    
    with open(filepath) as f:
        data = json.load(f)
    
    results = data.get('results', [])
    scored_results = []
    
    total_composite = 0.0
    successful_count = 0
    
    for result in results:
        process_score = compute_process_score_for_result(result)
        result['process_score'] = process_score
        scored_results.append(result)
        
        if result.get('success'):
            total_composite += process_score['total_score']
            successful_count += 1
    
    avg_composite = total_composite / successful_count if successful_count > 0 else 0.0
    
    # Update data with process scores
    data['results'] = scored_results
    data['process_score_computed'] = True
    data['avg_composite_score'] = avg_composite
    data['composite_grade'] = _score_to_grade(avg_composite)
    
    return data


def print_process_score_report(data: Dict[str, Any]):
    """Print a detailed process score report"""
    
    print("""
╔══════════════════════════════════════════════════════════════════╗
║           TRAJECTORY-BASED PROCESS SCORE REPORT                  ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    print(f"Model: {data.get('model', 'unknown')}")
    print(f"Tasks: {data.get('num_tasks', len(data.get('results', [])))}")
    print(f"Average Composite Score: {data.get('avg_composite_score', 0):.1%}")
    print(f"Composite Grade: {data.get('composite_grade', 'N/A')}")
    print()
    
    # Category breakdown
    categories = {}
    for result in data.get('results', []):
        if result.get('success') and 'process_score' in result:
            for cat, score in result['process_score']['scores'].items():
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(score)
    
    print("Category Breakdown (average across successful tasks):")
    print("-" * 60)
    weights = {
        "correctness": 0.35,
        "process": 0.20,
        "efficiency": 0.15,
        "collaboration": 0.15,
        "understanding": 0.10,
        "adaptation": 0.05
    }
    
    for cat, scores in sorted(categories.items(), key=lambda x: -weights.get(x[0], 0)):
        avg = sum(scores) / len(scores) if scores else 0
        weight = weights.get(cat, 0)
        contribution = avg * weight
        print(f"  {cat.upper():<15} {avg:>6.1%}  (weight: {weight:.0%}, contribution: {contribution:.1%})")
    
    print()
    print("Per-Task Results:")
    print("-" * 80)
    print(f"{'Instance':<40} {'Semantic':<10} {'Composite':<10} {'Grade':<6}")
    print("-" * 80)
    
    for result in data.get('results', []):
        iid = result.get('instance_id', 'unknown')[:38]
        if result.get('success') and 'process_score' in result:
            ps = result['process_score']
            semantic = ps.get('semantic_match', 0)
            composite = ps.get('total_score', 0)
            grade = ps.get('grade', 'N/A')
            print(f"  {iid:<40} {semantic:>6.1%}    {composite:>6.1%}    {grade:<6}")
        else:
            print(f"  {iid:<40} {'FAIL':<10} {'-':<10} {'F':<6}")
    
    print("-" * 80)
    print()
    print("Notes:")
    print("  - Reproduction gate was NOT enforced in these experiments")
    print("  - Dialogue/collaboration scoring based on baseline (no multi-turn)")
    print("  - Adaptation scoring neutral (no feedback loop)")
    print("  - Full trajectory logging would improve accuracy")


async def main():
    """Main entry point"""
    import argparse
    parser = argparse.ArgumentParser(description="Compute process scores for SWE-bench A2A results")
    parser.add_argument("--file", type=str, help="Results JSON file to process")
    parser.add_argument("--latest", action="store_true", help="Process the most recent results file")
    parser.add_argument("--save", action="store_true", help="Save updated results with process scores")
    args = parser.parse_args()
    
    # Find file to process
    if args.file:
        filepath = args.file
    elif args.latest:
        # Find most recent results file
        results_files = list(Path(__file__).parent.glob("a2a_*_results_*.json"))
        results_files.extend(Path(__file__).parent.glob("claude_*_results_*.json"))
        if not results_files:
            print("No results files found")
            return
        filepath = str(max(results_files, key=lambda p: p.stat().st_mtime))
        print(f"Processing: {filepath}")
    else:
        print("Usage: python compute_process_score.py --file <results.json> or --latest")
        return
    
    # Process
    data = process_results_file(filepath)
    print_process_score_report(data)
    
    # Save if requested
    if args.save:
        output_path = filepath.replace('.json', '_with_process_score.json')
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\n💾 Saved: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
