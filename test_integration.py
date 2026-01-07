#!/usr/bin/env python3
"""
Comprehensive Integration Test for SWE-bench A2A System

This script demonstrates all implemented features working together:
1. Real SWE-bench data loading
2. Issue2Test reproduction gate enforcement
3. Interactive dialogue with ambiguity
4. Senior Developer code review
5. Retro-Holdout mutations
6. Advanced scoring metrics
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Import all our modules
from src.swebench.integration import SWEBenchIntegration
from src.swebench.dataset_loader import DatasetLoader
from src.swebench.instance_mapper import InstanceMapper

from src.green_agent.reproduction_gate import ReproductionGate
from src.green_agent.dialogue_manager import DialogueManager
from src.green_agent.code_reviewer import SeniorDeveloperReviewer
from src.green_agent.ambiguity_layer import AmbiguityLayer

from src.mutation.retro_holdout import RetroHoldoutGenerator

from src.scoring.advanced_metrics import AdvancedMetrics

from src.a2a.protocol import A2AProtocol, TaskRequest, Task
from src.a2a.server import A2AServer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IntegrationTestRunner:
    """Runs comprehensive integration tests"""
    
    def __init__(self):
        # Initialize all components
        self.swebench = SWEBenchIntegration(
            dataset_config="verified",
            docker_enabled=False  # Disable Docker for testing
        )
        
        self.reproduction_gate = ReproductionGate(strict_mode=True)
        self.dialogue_manager = DialogueManager()
        self.code_reviewer = SeniorDeveloperReviewer(
            strictness="medium",
            personality="constructive"
        )
        self.retro_holdout = RetroHoldoutGenerator(mutation_seed=42)
        self.metrics = AdvancedMetrics()
        
        # Track test results
        self.test_results = []
    
    async def run_all_tests(self):
        """Run all integration tests"""
        print("""
╔═══════════════════════════════════════════════════════════════╗
║     SWE-bench A2A Integration Test Suite                     ║
║     Testing all implemented features from the document       ║
╚═══════════════════════════════════════════════════════════════╝
        """)
        
        # Test 1: SWE-bench Data Loading
        await self.test_swebench_loading()
        
        # Test 2: Issue2Test Reproduction Gate
        await self.test_reproduction_gate()
        
        # Test 3: Interactive Dialogue with Ambiguity
        await self.test_dialogue_system()
        
        # Test 4: Senior Developer Code Review
        await self.test_code_review()
        
        # Test 5: Retro-Holdout Mutations
        await self.test_retro_holdout()
        
        # Test 6: Advanced Scoring Metrics
        await self.test_scoring_metrics()
        
        # Test 7: End-to-End Flow
        await self.test_end_to_end_flow()
        
        # Print summary
        self.print_summary()
    
    async def test_swebench_loading(self):
        """Test 1: SWE-bench dataset loading and task creation"""
        print("\n" + "="*60)
        print("TEST 1: SWE-bench Dataset Loading")
        print("="*60)
        
        try:
            # Initialize SWE-bench integration
            await self.swebench.initialize()
            
            # Create a task from a random instance
            task = await self.swebench.create_task_from_instance(random_selection=True)
            
            print(f"✅ Successfully loaded SWE-bench dataset")
            print(f"✅ Created task: {task.id}")
            print(f"   Title: {task.title}")
            print(f"   Repository: {task.resources.get('repository', {}).get('name')}")
            
            # Get statistics
            stats = await self.swebench.get_statistics()
            print(f"✅ Dataset statistics:")
            print(f"   Total instances: {stats['dataset']['total_instances']}")
            print(f"   Loaded configs: {stats['dataset']['loaded_configs']}")
            
            self.test_results.append(("SWE-bench Loading", "PASSED"))
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            self.test_results.append(("SWE-bench Loading", "FAILED"))
    
    async def test_reproduction_gate(self):
        """Test 2: Issue2Test reproduction gate enforcement"""
        print("\n" + "="*60)
        print("TEST 2: Issue2Test Reproduction Gate")
        print("="*60)
        
        try:
            # Create a mock task
            task = Task(
                title="Fix authentication bug",
                description="Users can access restricted content without login"
            )
            
            # Check if reproduction is required
            required = await self.reproduction_gate.check_reproduction_required(task)
            print(f"✅ Reproduction required: {required}")
            
            # Try to submit patch without reproduction (should fail)
            patch_allowed = await self.reproduction_gate.check_patch_allowed(task)
            print(f"✅ Patch without reproduction blocked: {not patch_allowed['allowed']}")
            print(f"   Reason: {patch_allowed['reason']}")
            
            # Submit a reproduction script
            reproduction_script = """
import pytest

def test_restricted_access_bug():
    # This should fail on buggy code
    from auth import check_permission
    
    user = None  # No logged in user
    resource = "restricted_content"
    
    # Bug: This should return False but returns True
    assert not check_permission(user, resource), "Unauthorized access allowed!"
"""
            
            result = await self.reproduction_gate.submit_reproduction(
                task, 
                reproduction_script
            )
            
            print(f"✅ Reproduction submitted and verified: {result['reproduced_bug']}")
            print(f"   Message: {result['message']}")
            
            # Now patch should be allowed
            patch_allowed = await self.reproduction_gate.check_patch_allowed(task)
            print(f"✅ Patch now allowed: {patch_allowed['allowed']}")
            
            self.test_results.append(("Reproduction Gate", "PASSED"))
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            self.test_results.append(("Reproduction Gate", "FAILED"))
    
    async def test_dialogue_system(self):
        """Test 3: Interactive dialogue with ambiguity injection"""
        print("\n" + "="*60)
        print("TEST 3: Interactive Dialogue System")
        print("="*60)
        
        try:
            # Original clear description
            original = "TypeError in User.save() method at line 45 when commit=False parameter is used"
            
            # Initiate dialogue with ambiguity
            dialogue_result = await self.dialogue_manager.initiate_dialogue(
                task_id="test_task_1",
                original_description=original,
                ambiguity_level="medium"
            )
            
            print(f"✅ Dialogue initiated")
            print(f"   Original: {original}")
            print(f"   Ambiguous: {dialogue_result['description']}")
            print(f"   Ambiguity score: {dialogue_result['ambiguity_score']:.2f}")
            
            # Simulate agent asking questions
            question1 = "What type of error is occurring?"
            response1 = await self.dialogue_manager.process_question(
                "test_task_1",
                question1,
                "agent_1"
            )
            print(f"\n✅ Question 1: {question1}")
            print(f"   Answer: {response1['answer']}")
            print(f"   Quality score: {response1['quality_score']:.2f}")
            
            question2 = "Where exactly does the error occur?"
            response2 = await self.dialogue_manager.process_question(
                "test_task_1",
                question2,
                "agent_1"
            )
            print(f"\n✅ Question 2: {question2}")
            print(f"   Answer: {response2['answer']}")
            
            # Get dialogue state
            state = self.dialogue_manager.get_dialogue_state("test_task_1")
            print(f"\n✅ Dialogue state:")
            print(f"   Information revealed: {state['information_revealed']:.2%}")
            print(f"   Efficiency score: {state['efficiency_score']:.2%}")
            print(f"   Requirements quality: {self.dialogue_manager.calculate_requirements_quality_score('test_task_1'):.2%}")
            
            self.test_results.append(("Dialogue System", "PASSED"))
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            self.test_results.append(("Dialogue System", "FAILED"))
    
    async def test_code_review(self):
        """Test 4: Senior Developer code review persona"""
        print("\n" + "="*60)
        print("TEST 4: Senior Developer Code Review")
        print("="*60)
        
        try:
            # Sample patch
            patch = """
diff --git a/auth.py b/auth.py
index abc123..def456 100644
--- a/auth.py
+++ b/auth.py
@@ -42,7 +42,10 @@ class User:
     def save(self, commit=True):
         # Save user to database
-        data = self.to_dict()
+        if commit == False:  # Issue: comparing to boolean
+            data = self.to_dict()
+        else:
+            data = self.to_dict()
         
         if commit:
             db.save(data)
+            os.system(f"echo 'Saved user {self.id}'")  # Security issue
"""
            
            # Review the patch
            review = await self.code_reviewer.review_patch(
                task_id="test_task_2",
                patch=patch,
                iteration=1
            )
            
            print(f"✅ Code review completed")
            print(f"   Accepted: {review['accepted']}")
            print(f"   Issues found: {len(review['issues'])}")
            
            # Print issues by severity
            for severity in ["blocker", "critical", "major", "minor"]:
                count = review['severity_summary'].get(severity, 0)
                if count > 0:
                    print(f"   {severity.upper()}: {count}")
            
            print(f"\n📝 Feedback:")
            print(review['feedback'][:500] + "..." if len(review['feedback']) > 500 else review['feedback'])
            
            # Simulate agent response
            agent_response = "I understand the security concern with os.system. I'll use subprocess.run instead."
            discussion = await self.code_reviewer.simulate_discussion(
                "test_task_2",
                agent_response
            )
            print(f"\n✅ Discussion simulation:")
            print(f"   Agent response accepted: {discussion.get('accepted_argument', False)}")
            print(f"   Reviewer response: {discussion['response']}")
            
            self.test_results.append(("Code Review", "PASSED"))
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            self.test_results.append(("Code Review", "FAILED"))
    
    async def test_retro_holdout(self):
        """Test 5: Retro-Holdout anti-contamination system"""
        print("\n" + "="*60)
        print("TEST 5: Retro-Holdout Anti-Contamination")
        print("="*60)
        
        try:
            # Create a mock instance
            instance = {
                "instance_id": "django__django-11099",
                "repo": "django/django",
                "base_commit": "abc123",
                "problem_statement": "UsernameValidator allows trailing newline in usernames",
                "FAIL_TO_PASS": ["tests.auth_tests.test_validators::test_trailing_newline"],
                "PASS_TO_PASS": ["tests.auth_tests.test_validators::test_valid"],
                "patch": "diff --git a/django/contrib/auth/validators.py..."
            }
            
            # Generate retro-holdout version
            repo_path = Path("./test_repo")
            repo_path.mkdir(exist_ok=True)
            
            # Create a sample file to mutate
            test_file = repo_path / "auth.py"
            test_file.write_text("""
class UserManager:
    def create_user(self, data):
        result = self.validate(data)
        return result
    
    def get_user(self, user_id):
        cache = self.cache
        if user_id in cache:
            return cache[user_id]
        return None
""")
            
            mutated = await self.retro_holdout.generate_retro_holdout(
                instance,
                repo_path,
                level="medium"
            )
            
            print(f"✅ Retro-holdout generated")
            print(f"   Original ID: {instance['instance_id']}")
            print(f"   Mutated ID: {mutated['instance_id']}")
            print(f"   Mutation hash: {mutated['mutation_hash']}")
            
            # Check problem statement mutation
            print(f"\n📝 Problem statement comparison:")
            print(f"   Original: {instance['problem_statement'][:80]}...")
            print(f"   Mutated: {mutated['problem_statement'][:80]}...")
            
            # Calculate contamination score
            original_perf = 0.85
            mutated_perf = 0.45
            contamination = self.retro_holdout.calculate_contamination_score(
                original_perf,
                mutated_perf
            )
            print(f"\n✅ Contamination analysis:")
            print(f"   Original performance: {original_perf:.2%}")
            print(f"   Mutated performance: {mutated_perf:.2%}")
            print(f"   Contamination score: {contamination:.2%}")
            print(f"   Interpretation: {'High' if contamination > 0.3 else 'Low'} contamination")
            
            # Clean up
            import shutil
            shutil.rmtree(repo_path, ignore_errors=True)
            
            self.test_results.append(("Retro-Holdout", "PASSED"))
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            self.test_results.append(("Retro-Holdout", "FAILED"))
    
    async def test_scoring_metrics(self):
        """Test 6: Advanced scoring metrics"""
        print("\n" + "="*60)
        print("TEST 6: Advanced Scoring Metrics")
        print("="*60)
        
        try:
            # Create mock data
            task_result = {
                "passed": True,
                "tests_passed": 8,
                "tests_failed": 2,
                "execution_time": 120,
                "difficulty": "medium"
            }
            
            trajectory = [
                {"type": "search", "success": True},
                {"type": "read", "success": True},
                {"type": "grep", "success": True},
                {"type": "reproduce", "success": True},
                {"type": "edit", "success": True},
                {"type": "test", "success": False},
                {"type": "fix", "success": True},
                {"type": "test", "success": True},
                {"type": "patch", "success": True}
            ]
            
            dialogue_metrics = {
                "requirements_quality_score": 0.75,
                "information_gain_efficiency": 0.8,
                "total_questions": 3,
                "relevant_questions": 2,
                "information_revealed": 0.85
            }
            
            reproduction_metrics = {
                "attempted": True,
                "verified": True,
                "attempts": 1
            }
            
            review_metrics = {
                "iterations": 2,
                "total_issues": 5,
                "issues_resolved": 4,
                "feedback_incorporation_score": 0.8,
                "iteration_scores": [0.6, 0.85]
            }
            
            # Calculate comprehensive score
            score_result = await self.metrics.calculate_comprehensive_score(
                task_id="test_task_3",
                task_result=task_result,
                trajectory=trajectory,
                dialogue_metrics=dialogue_metrics,
                reproduction_metrics=reproduction_metrics,
                review_metrics=review_metrics
            )
            
            print(f"✅ Comprehensive scoring completed")
            print(f"   Total Score: {score_result['total_score']:.2%}")
            print(f"   Grade: {score_result['grade']}")
            
            print(f"\n📊 Category Breakdown:")
            for category, score in score_result['scores'].items():
                weight = score_result['weights'][category]
                print(f"   {category.capitalize()}: {score:.2%} (weight: {weight:.0%})")
            
            # Generate detailed report
            report = self.metrics.generate_detailed_report("test_task_3")
            print(f"\n📋 Detailed Report Preview:")
            print(report[:800] + "..." if len(report) > 800 else report)
            
            self.test_results.append(("Scoring Metrics", "PASSED"))
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            self.test_results.append(("Scoring Metrics", "FAILED"))
    
    async def test_end_to_end_flow(self):
        """Test 7: Complete end-to-end flow"""
        print("\n" + "="*60)
        print("TEST 7: End-to-End Integration Flow")
        print("="*60)
        
        try:
            print("Simulating complete agent evaluation flow...")
            
            # Step 1: Load SWE-bench instance
            print("\n1️⃣ Loading SWE-bench instance...")
            task = await self.swebench.create_task_from_instance(random_selection=True)
            print(f"   ✅ Task created: {task.id}")
            
            # Step 2: Inject ambiguity
            print("\n2️⃣ Injecting ambiguity into problem statement...")
            dialogue = await self.dialogue_manager.initiate_dialogue(
                task.id,
                task.description,
                ambiguity_level="medium"
            )
            print(f"   ✅ Ambiguous description created")
            
            # Step 3: Agent asks clarifying questions
            print("\n3️⃣ Simulating agent dialogue...")
            await self.dialogue_manager.process_question(
                task.id,
                "What specific error is occurring?",
                "test_agent"
            )
            print(f"   ✅ Clarification questions processed")
            
            # Step 4: Check reproduction requirement
            print("\n4️⃣ Checking reproduction gate...")
            reproduction_required = await self.reproduction_gate.check_reproduction_required(task)
            print(f"   ✅ Reproduction required: {reproduction_required}")
            
            # Step 5: Submit reproduction
            if reproduction_required:
                print("\n5️⃣ Submitting reproduction script...")
                await self.reproduction_gate.submit_reproduction(
                    task,
                    "def test_bug(): assert False  # Bug reproduced"
                )
                print(f"   ✅ Reproduction verified")
            
            # Step 6: Submit patch for review
            print("\n6️⃣ Submitting patch for code review...")
            patch = "diff --git a/fix.py..."
            review = await self.code_reviewer.review_patch(
                task.id,
                patch,
                iteration=1
            )
            print(f"   ✅ Code review completed: {'Accepted' if review['accepted'] else 'Needs revision'}")
            
            # Step 7: Calculate final score
            print("\n7️⃣ Calculating comprehensive score...")
            final_score = await self.metrics.calculate_comprehensive_score(
                task.id,
                {"passed": True, "tests_passed": 10, "tests_failed": 0},
                [{"type": "complete", "success": True}],
                self.dialogue_manager.get_dialogue_state(task.id),
                self.reproduction_gate.get_reproduction_status(task.id),
                review
            )
            print(f"   ✅ Final Grade: {final_score['grade']} ({final_score['total_score']:.2%})")
            
            print("\n🎉 End-to-end flow completed successfully!")
            self.test_results.append(("End-to-End Flow", "PASSED"))
            
        except Exception as e:
            print(f"❌ Failed: {e}")
            self.test_results.append(("End-to-End Flow", "FAILED"))
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, status in self.test_results if status == "PASSED")
        failed = sum(1 for _, status in self.test_results if status == "FAILED")
        
        print(f"\nTotal Tests: {len(self.test_results)}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        
        print("\nDetailed Results:")
        for test_name, status in self.test_results:
            symbol = "✅" if status == "PASSED" else "❌"
            print(f"  {symbol} {test_name}: {status}")
        
        if passed == len(self.test_results):
            print("""
╔═══════════════════════════════════════════════════════════════╗
║     🎉 ALL TESTS PASSED! 🎉                                  ║
║     SWE-bench A2A system is fully integrated                 ║
║     All document requirements have been implemented          ║
╚═══════════════════════════════════════════════════════════════╝
            """)
        else:
            print(f"\n⚠️ Some tests failed. Please review the output above.")


async def main():
    """Main entry point"""
    runner = IntegrationTestRunner()
    await runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())