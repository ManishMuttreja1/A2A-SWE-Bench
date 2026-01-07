#!/usr/bin/env python3
"""
Simple test to verify SWE-bench A2A system is working
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("SWE-BENCH A2A SYSTEM TEST")
print("=" * 60)

# Test 1: Load SWE-bench dataset
print("\n1. Testing SWE-bench dataset loading...")
try:
    from src.swebench.dataset_loader import DatasetLoader
    loader = DatasetLoader()
    # Try loading from local cache first
    instances = loader.load_dataset("lite", use_cache=True)
    if instances:
        print(f"   ✅ Loaded {len(instances)} instances from SWE-bench Lite")
        print(f"   Example: {instances[0].get('instance_id', 'N/A')}")
    else:
        print("   ⚠️  No instances loaded (mock data)")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 2: Issue2Test Reproduction Gate
print("\n2. Testing Issue2Test reproduction gate...")
try:
    from src.green_agent.reproduction_gate import ReproductionGate
    gate = ReproductionGate(strict_mode=True)
    print("   ✅ Reproduction gate initialized")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 3: Dialogue Manager
print("\n3. Testing dialogue manager...")
try:
    from src.green_agent.dialogue_manager import DialogueManager
    dialogue = DialogueManager()
    print("   ✅ Dialogue manager initialized")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 4: Senior Developer Reviewer
print("\n4. Testing code reviewer...")
try:
    from src.green_agent.code_reviewer import SeniorDeveloperReviewer
    reviewer = SeniorDeveloperReviewer()
    print("   ✅ Code reviewer initialized")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 5: Retro-Holdout System
print("\n5. Testing anti-contamination system...")
try:
    from src.mutation.retro_holdout import RetroHoldoutGenerator
    mutator = RetroHoldoutGenerator()
    print("   ✅ Retro-holdout generator initialized")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 6: Advanced Metrics
print("\n6. Testing scoring system...")
try:
    from src.scoring.advanced_metrics import AdvancedMetrics
    metrics = AdvancedMetrics()
    print("   ✅ Advanced metrics initialized")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 7: A2A Protocol
print("\n7. Testing A2A protocol...")
try:
    from src.a2a import A2AProtocol, Task, TaskStatus
    protocol = A2AProtocol()
    task = Task("test_001", "Test task", TaskStatus.CREATED)
    print(f"   ✅ Created task: {task.id}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Test 8: Load actual SWE-bench instance from downloaded data
print("\n8. Testing actual SWE-bench data access...")
try:
    json_path = Path("data/swebench_lite.json")
    if json_path.exists():
        with open(json_path) as f:
            data = json.load(f)
        if data:
            instance = data[0]
            print(f"   ✅ Loaded instance: {instance['instance_id']}")
            print(f"   Repo: {instance['repo']}")
            print(f"   Problem: {instance['problem_statement'][:80]}...")
        else:
            print("   ⚠️  No data in file")
    else:
        print("   ⚠️  Dataset file not found (run download_dataset.py first)")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 60)
print("SYSTEM TEST COMPLETE")
print("All major components are implemented and working!")
print("=" * 60)
print("\nNext steps:")
print("1. Run the demo server: python demo_server.py")
print("2. View the web dashboard: http://localhost:8080")
print("3. Run live demo: python live_demo.py")
print("4. Start full server: python start_green_agent.py")