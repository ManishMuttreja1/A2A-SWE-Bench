#!/usr/bin/env python3
"""
Script to convert local benchmark results to AgentBeats format and submit them.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import glob

# AgentBeats agent IDs from scenario.toml
AGENT_IDS = {
    "claude-sonnet-4.5": "019bbec8-5656-7792-b572-21fcf6cc36fb",
    "gpt-5.2": "019bbec8-5656-7792-b572-21fcf6cc36fb",
    "gpt-4o": "019bbec8-5656-7792-b572-21fcf6cc36fb",
}

def convert_to_agentbeats_format(result_file: Path) -> Optional[Dict[str, Any]]:
    """
    Convert local benchmark result JSON to AgentBeats format.
    
    Expected AgentBeats format:
    {
        "participants": {"agent": "agent-id"},
        "id": "agent-id",
        "score": 44.8,
        "accuracy": 44.8,
        "timestamp": "2026-01-16T00:00:00Z",
        "model": "gpt-5.2",
        "tasks_completed": 100,
        "status": "completed"
    }
    """
    try:
        with open(result_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {result_file}: {e}")
        return None
    
    # Extract model name from filename or config
    model = data.get("config", {}).get("model", "")
    if not model:
        # Try to extract from filename
        filename = result_file.name
        if "claude-sonnet" in filename:
            model = "claude-sonnet-4.5"
        elif "gpt-5.2" in filename or "gpt-52" in filename:
            model = "gpt-5.2"
        elif "gpt-4o" in filename:
            model = "gpt-4o"
    
    if not model:
        print(f"Could not determine model from {result_file}")
        return None
    
    # Get agent ID
    agent_id = AGENT_IDS.get(model, AGENT_IDS["gpt-5.2"])  # Default fallback
    
    # Extract statistics
    stats = data.get("statistics", {})
    num_tasks = stats.get("num_tasks", data.get("config", {}).get("num_tasks", 0))
    
    # Calculate score and accuracy from execution metrics
    # For execution-based: use execution_pass_rate
    # For semantic-based: use semantic_match_rate
    execution_results = data.get("execution_results", [])
    if execution_results:
        # Calculate pass rate from execution results
        passed = sum(1 for r in execution_results if r.get("execution_pass", False))
        accuracy = (passed / len(execution_results)) * 100 if execution_results else 0.0
    else:
        # Fallback to statistics
        mean_pass_rate = stats.get("mean_pass_rate", 0.0)
        accuracy = mean_pass_rate * 100
    
    # Use accuracy as score (or calculate weighted score)
    score = accuracy
    
    # Extract timestamp
    timestamp_str = data.get("timestamp", "")
    if timestamp_str:
        # Convert YYYYMMDD_HHMMSS to ISO format
        try:
            dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except:
            from datetime import timezone
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        from datetime import timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Determine status
    status = "completed"
    if num_tasks == 0:
        status = "failed"
    elif accuracy == 0 and num_tasks > 0:
        status = "completed"  # Still completed, just 0% pass
    
    agentbeats_result = {
        "participants": {
            "agent": agent_id
        },
        "id": agent_id,
        "score": round(score, 1),
        "accuracy": round(accuracy, 1),
        "timestamp": timestamp,
        "model": model,
        "tasks_completed": num_tasks,
        "status": status
    }
    
    return agentbeats_result

def find_latest_results() -> Dict[str, Path]:
    """Find the latest result files for each model."""
    results_dir = Path(".")
    latest_results = {}
    
    # Find all proper_benchmark_*.json files
    pattern = "proper_benchmark_*.json"
    result_files = list(results_dir.glob(pattern))
    
    # Group by model and find latest
    by_model = {}
    for result_file in result_files:
        model = None
        if "claude-sonnet" in result_file.name:
            model = "claude-sonnet-4.5"
        elif "gpt-5.2" in result_file.name or "gpt-52" in result_file.name:
            model = "gpt-5.2"
        elif "gpt-4o" in result_file.name:
            model = "gpt-4o"
        
        if model:
            if model not in by_model:
                by_model[model] = []
            by_model[model].append(result_file)
    
    # Find latest for each model (by modification time)
    for model, files in by_model.items():
        latest = max(files, key=lambda f: f.stat().st_mtime)
        latest_results[model] = latest
    
    return latest_results

def save_agentbeats_results(results: Dict[str, Dict[str, Any]], output_dir: Path):
    """Save AgentBeats-formatted results to leaderboard/results/ directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for model, result in results.items():
        # Create filename based on timestamp
        from datetime import timezone
        timestamp = result.get("timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        # Extract date part
        date_part = timestamp.split("T")[0].replace("-", "")
        filename = f"run_{model.replace('-', '_')}_{date_part}.json"
        output_file = output_dir / filename
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"✅ Saved AgentBeats result: {output_file}")
        print(f"   Model: {model}")
        print(f"   Score: {result['score']}%")
        print(f"   Accuracy: {result['accuracy']}%")
        print(f"   Tasks: {result['tasks_completed']}")
        print()

def main():
    """Main function to convert and submit results."""
    print("=== Converting Local Results to AgentBeats Format ===\n")
    
    # Find latest results
    latest_results = find_latest_results()
    
    if not latest_results:
        print("❌ No benchmark result files found!")
        print("   Looking for files matching: proper_benchmark_*.json")
        return 1
    
    print(f"Found {len(latest_results)} model(s) with results:\n")
    
    # Convert each result
    agentbeats_results = {}
    for model, result_file in latest_results.items():
        print(f"📊 Processing {model}...")
        print(f"   File: {result_file}")
        
        converted = convert_to_agentbeats_format(result_file)
        if converted:
            agentbeats_results[model] = converted
            print(f"   ✅ Converted successfully")
        else:
            print(f"   ❌ Conversion failed")
        print()
    
    if not agentbeats_results:
        print("❌ No results could be converted!")
        return 1
    
    # Save to leaderboard/results/
    output_dir = Path("leaderboard/results")
    save_agentbeats_results(agentbeats_results, output_dir)
    
    print("=== Summary ===")
    print(f"✅ Converted {len(agentbeats_results)} result(s) to AgentBeats format")
    print(f"📁 Results saved to: {output_dir}")
    print()
    print("Next steps:")
    print("1. Review the converted results in leaderboard/results/")
    print("2. Commit and push to trigger AgentBeats webhook (if configured)")
    print("3. Or manually submit via AgentBeats API if needed")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
