#!/usr/bin/env python3
"""
Quick Start Script for SWE-bench A2A Evaluation

Usage:
    python run_evaluation.py --mode [basic|dialogue|review|full]
"""

import asyncio
import argparse
import logging
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.swebench.integration import SWEBenchIntegration
from src.green_agent.reproduction_gate import ReproductionGate
from src.green_agent.dialogue_manager import DialogueManager
from src.green_agent.code_reviewer import SeniorDeveloperReviewer
from src.scoring.advanced_metrics import AdvancedMetrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_basic_evaluation():
    """Run basic SWE-bench evaluation"""
    print("🚀 Running Basic SWE-bench Evaluation")
    
    # Initialize
    swebench = SWEBenchIntegration(docker_enabled=False)
    await swebench.initialize()
    
    # Create task
    task = await swebench.create_task_from_instance(random_selection=True)
    print(f"Task: {task.title}")
    print(f"Repository: {task.resources.get('repository', {}).get('name')}")
    
    # Simulate patch submission
    from src.swebench.instance_mapper import InstanceMapper
    mapper = InstanceMapper()
    
    patch_artifact = mapper.create_patch_artifact(
        "diff --git a/fix.py...",
        "Fix the bug"
    )
    
    result = await swebench.submit_patch(task.id, patch_artifact)
    print(f"Result: {'✅ Passed' if result['success'] else '❌ Failed'}")


async def run_dialogue_evaluation():
    """Run evaluation with dialogue"""
    print("💬 Running Dialogue-Enhanced Evaluation")
    
    # Initialize
    dialogue_manager = DialogueManager()
    
    # Create ambiguous description
    original = "TypeError in authentication module when user object is None"
    dialogue = await dialogue_manager.initiate_dialogue(
        "test_task",
        original,
        ambiguity_level="medium"
    )
    
    print(f"Ambiguous: {dialogue['description']}")
    
    # Simulate questions
    questions = [
        "What specific error type occurs?",
        "Which module has the issue?",
        "When does this happen?"
    ]
    
    for q in questions:
        response = await dialogue_manager.process_question(
            "test_task", q, "test_agent"
        )
        print(f"Q: {q}")
        print(f"A: {response['answer']}\n")
    
    # Get score
    score = dialogue_manager.calculate_requirements_quality_score("test_task")
    print(f"Requirements Quality Score: {score:.2%}")


async def run_review_evaluation():
    """Run evaluation with code review"""
    print("👨‍💻 Running Code Review Evaluation")
    
    reviewer = SeniorDeveloperReviewer(
        strictness="medium",
        personality="constructive"
    )
    
    # Sample patch with issues
    patch = """
diff --git a/auth.py b/auth.py
@@ -1,5 +1,8 @@
 def authenticate(user, password):
-    if user and password:
+    if user == None:  # Bad: comparing to None
+        return False
+    if password == "":  # Bad: comparing to empty string
+        return False
+    eval(f"check_{user}")  # Security issue!
     return True
"""
    
    review = await reviewer.review_patch("task_1", patch, iteration=1)
    
    print(f"Review Result: {'✅ Accepted' if review['accepted'] else '❌ Needs Work'}")
    print(f"Issues Found: {len(review['issues'])}")
    print("\nFeedback:")
    print(review['feedback'])


async def run_full_evaluation():
    """Run full evaluation pipeline"""
    print("🎯 Running Full Evaluation Pipeline")
    
    # Initialize all components
    swebench = SWEBenchIntegration(docker_enabled=False)
    reproduction_gate = ReproductionGate(strict_mode=True)
    dialogue_manager = DialogueManager()
    reviewer = SeniorDeveloperReviewer()
    metrics = AdvancedMetrics()
    
    print("\n1️⃣ Initializing SWE-bench...")
    await swebench.initialize()
    
    print("2️⃣ Creating task...")
    task = await swebench.create_task_from_instance(random_selection=True)
    
    print("3️⃣ Checking reproduction requirement...")
    needs_reproduction = await reproduction_gate.check_reproduction_required(task)
    print(f"   Reproduction required: {needs_reproduction}")
    
    if needs_reproduction:
        print("4️⃣ Submitting reproduction script...")
        script = "def test_bug(): assert False  # Reproduces bug"
        await reproduction_gate.submit_reproduction(task, script)
    
    print("5️⃣ Initiating dialogue...")
    dialogue = await dialogue_manager.initiate_dialogue(
        task.id,
        task.description,
        ambiguity_level="medium"
    )
    
    print("6️⃣ Submitting patch for review...")
    patch = "diff --git a/fix.py..."
    review = await reviewer.review_patch(task.id, patch, iteration=1)
    
    print("7️⃣ Calculating comprehensive score...")
    score = await metrics.calculate_comprehensive_score(
        task.id,
        {"passed": True, "tests_passed": 8, "tests_failed": 2},
        [{"type": "complete", "success": True}],
        dialogue_manager.get_dialogue_state(task.id),
        reproduction_gate.get_reproduction_status(task.id),
        review
    )
    
    print(f"\n📊 Final Results:")
    print(f"   Total Score: {score['total_score']:.2%}")
    print(f"   Grade: {score['grade']}")
    print(f"   Breakdown:")
    for category, cat_score in score['scores'].items():
        print(f"     {category}: {cat_score:.2%}")


async def main():
    parser = argparse.ArgumentParser(
        description="Run SWE-bench A2A Evaluation"
    )
    parser.add_argument(
        "--mode",
        choices=["basic", "dialogue", "review", "full"],
        default="basic",
        help="Evaluation mode"
    )
    
    args = parser.parse_args()
    
    print("""
╔═══════════════════════════════════════════════════════════════╗
║            SWE-bench A2A Evaluation System                   ║
║            Dynamic Agent Assessment Framework                ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    if args.mode == "basic":
        await run_basic_evaluation()
    elif args.mode == "dialogue":
        await run_dialogue_evaluation()
    elif args.mode == "review":
        await run_review_evaluation()
    elif args.mode == "full":
        await run_full_evaluation()
    
    print("\n✅ Evaluation complete!")


if __name__ == "__main__":
    asyncio.run(main())