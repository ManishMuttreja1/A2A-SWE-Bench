#!/usr/bin/env python3
"""
Download SWE-bench dataset from HuggingFace Hub
"""

import os
from pathlib import Path
from datasets import load_dataset
import json

def download_swebench_lite():
    """Download SWE-bench Lite dataset for testing"""
    print("📥 Downloading SWE-bench Lite dataset...")
    
    # Create data directory
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    try:
        # Load from HuggingFace Hub
        dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
        
        # Save to local disk
        cache_dir = data_dir / "swebench_lite"
        dataset.save_to_disk(str(cache_dir))
        
        # Also save as JSON for easy inspection
        json_path = data_dir / "swebench_lite.json"
        with open(json_path, "w") as f:
            json.dump([item for item in dataset], f, indent=2)
        
        print(f"✅ Downloaded {len(dataset)} instances to {cache_dir}")
        print(f"✅ Also saved JSON to {json_path}")
        
        # Show first instance as example
        if len(dataset) > 0:
            first = dataset[0]
            print("\n📋 Example instance:")
            print(f"  Instance ID: {first.get('instance_id', 'N/A')}")
            print(f"  Repo: {first.get('repo', 'N/A')}")
            print(f"  Problem: {first.get('problem_statement', 'N/A')[:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Error downloading dataset: {e}")
        print("⚠️  Will use mock data for demo purposes")
        
        # Create mock data
        mock_data = [
            {
                "instance_id": "django__django-11099",
                "repo": "django/django",
                "problem_statement": "TypeError in User.save() when commit=False",
                "base_commit": "abc123",
                "test_patch": "def test_bug():\n    assert False",
                "hints_text": "Check the save method"
            }
        ]
        
        mock_path = data_dir / "swebench_mock.json"
        with open(mock_path, "w") as f:
            json.dump(mock_data, f, indent=2)
        
        print(f"✅ Created mock data at {mock_path}")
        return False

if __name__ == "__main__":
    download_swebench_lite()