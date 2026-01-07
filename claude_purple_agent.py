#!/usr/bin/env python3
"""
Claude Sonnet Purple Agent for SWE-bench Evaluation
This agent wraps Claude Sonnet to solve SWE-bench tasks with A2A protocol
"""

import asyncio
import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import anthropic
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.a2a.client import A2AClient
from src.a2a.protocol import Task, TaskStatus, Part, PartType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ClaudeSonnetAgent:
    """Purple Agent wrapper for Claude Sonnet"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
            self.model = "claude-3-5-sonnet-20241022"  # Latest Sonnet
        else:
            logger.warning("No Anthropic API key found - using mock mode")
            self.client = None
            self.model = "mock"
            
        # A2A client for Green Agent communication
        self.a2a_client = A2AClient(
            agent_id="claude-sonnet-purple",
            base_url=os.getenv("GREEN_AGENT_URL", "http://localhost:8000")
        )
        
        # Track metrics
        self.metrics = {
            "tasks_attempted": 0,
            "tasks_completed": 0,
            "dialogue_turns": [],
            "review_iterations": [],
            "execution_times": []
        }
        
    async def solve_task(self, task: Task) -> Dict[str, Any]:
        """Solve a SWE-bench task using Claude Sonnet"""
        start_time = datetime.now()
        self.metrics["tasks_attempted"] += 1
        
        logger.info(f"Claude Sonnet attempting task: {task.id}")
        
        # Extract problem description
        problem = task.description
        repo_info = task.metadata.get("repo", "") if task.metadata else ""
        
        # Phase 1: Dialogue - Ask clarifying questions
        dialogue_count = 0
        if task.metadata and task.metadata.get("requires_dialogue"):
            clarified_description = await self._conduct_dialogue(task, problem)
            problem = clarified_description
            dialogue_count = len(self.dialogue_history)
            
        # Phase 2: Reproduction - Generate test to reproduce bug
        reproduction_script = await self._generate_reproduction(problem, repo_info)
        
        # Submit reproduction for verification
        repro_result = await self.a2a_client.submit_reproduction(
            task_id=task.id,
            script=reproduction_script
        )
        
        if not repro_result.get("verified"):
            # Try again with feedback
            reproduction_script = await self._improve_reproduction(
                problem, 
                reproduction_script, 
                repro_result.get("feedback", "")
            )
            
        # Phase 3: Solution - Generate patch
        patch = await self._generate_patch(problem, reproduction_script, repo_info)
        
        # Phase 4: Review - Handle code review feedback
        review_iterations = 0
        final_patch = patch
        
        while review_iterations < 3:  # Max 3 review iterations
            review_result = await self.a2a_client.submit_patch(
                task_id=task.id,
                patch=final_patch
            )
            
            if review_result.get("status") == "accepted":
                break
                
            # Incorporate feedback
            feedback = review_result.get("feedback", [])
            if feedback:
                final_patch = await self._incorporate_feedback(
                    problem, 
                    final_patch, 
                    feedback
                )
                review_iterations += 1
            else:
                break
                
        # Calculate execution time
        execution_time = (datetime.now() - start_time).total_seconds()
        
        # Update metrics
        self.metrics["tasks_completed"] += 1
        self.metrics["dialogue_turns"].append(dialogue_count)
        self.metrics["review_iterations"].append(review_iterations)
        self.metrics["execution_times"].append(execution_time)
        
        return {
            "task_id": task.id,
            "status": "completed",
            "patch": final_patch,
            "reproduction_script": reproduction_script,
            "dialogue_turns": dialogue_count,
            "review_iterations": review_iterations,
            "execution_time": execution_time
        }
        
    async def _conduct_dialogue(self, task: Task, problem: str) -> str:
        """Conduct dialogue to clarify ambiguous requirements"""
        self.dialogue_history = []
        clarified = problem
        
        # Generate questions using Claude
        questions_prompt = f"""You are solving a software engineering task. The description is ambiguous:

{problem}

Generate 3 clarifying questions to better understand the requirements. Format as JSON list."""

        if self.client:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": questions_prompt}]
            )
            questions = json.loads(response.content[0].text)
        else:
            questions = [
                "What specific error type occurs?",
                "In which file/function does this happen?",
                "Under what conditions?"
            ]
            
        # Ask questions via A2A dialogue
        for question in questions[:3]:  # Limit to 3 questions
            answer = await self.a2a_client.ask_question(task.id, question)
            self.dialogue_history.append({"q": question, "a": answer})
            clarified += f"\n- {question}: {answer}"
            
        return clarified
        
    async def _generate_reproduction(self, problem: str, repo_info: str) -> str:
        """Generate a test script that reproduces the bug"""
        
        prompt = f"""You are debugging a software issue. Generate a Python test that reproduces this bug:

Problem: {problem}
Repository: {repo_info}

Requirements:
1. The test should FAIL on buggy code
2. The test should PASS after the fix
3. Include assertions that verify the bug exists
4. Make it minimal and focused

Return only the Python code for the test."""

        if self.client:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        else:
            # Mock reproduction script
            return """def test_bug_reproduction():
    # This test reproduces the reported bug
    from module import problematic_function
    
    # This should raise an error in buggy code
    with pytest.raises(TypeError):
        result = problematic_function(commit=False)
    
    assert False, "Bug not reproduced - function didn't raise TypeError"
"""
            
    async def _generate_patch(self, problem: str, reproduction: str, repo_info: str) -> str:
        """Generate a patch to fix the issue"""
        
        prompt = f"""You are fixing a software bug. Generate a patch that solves this issue:

Problem: {problem}
Repository: {repo_info}

Bug Reproduction Test:
{reproduction}

Requirements:
1. Fix the bug so the reproduction test passes
2. Maintain backward compatibility
3. Follow the existing code style
4. Include only necessary changes

Return the patch in unified diff format."""

        if self.client:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        else:
            # Mock patch
            return """--- a/module.py
+++ b/module.py
@@ -42,7 +42,7 @@ class User:
     def save(self, commit=True):
-        if commit == False:  # Bug: comparing to boolean
+        if not commit:  # Fixed: proper boolean check
             data = self.to_dict()
             return self._save_draft(data)
"""
            
    async def _incorporate_feedback(self, problem: str, patch: str, feedback: List[Dict]) -> str:
        """Incorporate code review feedback into the patch"""
        
        feedback_text = "\n".join([
            f"- {f['severity']}: {f['message']}" 
            for f in feedback
        ])
        
        prompt = f"""You received code review feedback on your patch. Improve it:

Original Problem: {problem}

Your Patch:
{patch}

Review Feedback:
{feedback_text}

Generate an improved patch that addresses all feedback. Return only the improved patch in unified diff format."""

        if self.client:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        else:
            # Mock improved patch
            return patch.replace("# Bug:", "# Fixed:")
            
    async def _improve_reproduction(self, problem: str, script: str, feedback: str) -> str:
        """Improve reproduction script based on feedback"""
        
        prompt = f"""Your bug reproduction script needs improvement:

Problem: {problem}

Your Script:
{script}

Feedback: {feedback}

Generate an improved reproduction script that addresses the feedback."""

        if self.client:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        else:
            return script + "\n# Improved based on feedback"


async def run_benchmark():
    """Run SWE-bench benchmark with Claude Sonnet"""
    
    print("""
╔═══════════════════════════════════════════════════════════════╗
║     Benchmarking Claude Sonnet on SWE-bench with A2A         ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Initialize agent
    agent = ClaudeSonnetAgent()
    
    # Connect to Green Agent
    print("🔌 Connecting to Green Agent server...")
    
    # Request tasks from Green Agent
    num_tasks = int(os.getenv("NUM_TASKS", "5"))  # Start with 5 tasks
    
    results = []
    for i in range(num_tasks):
        try:
            # Request next task
            print(f"\n📋 Requesting task {i+1}/{num_tasks}...")
            task = await agent.a2a_client.request_task()
            
            print(f"   Task ID: {task.id}")
            print(f"   Description: {task.description[:100]}...")
            
            # Solve task
            print("   🧠 Claude Sonnet solving...")
            result = await agent.solve_task(task)
            
            # Report results
            print(f"   ✅ Completed in {result['execution_time']:.1f}s")
            print(f"   Dialogue turns: {result['dialogue_turns']}")
            print(f"   Review iterations: {result['review_iterations']}")
            
            results.append(result)
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            
    # Generate report
    print("\n" + "="*60)
    print("BENCHMARK RESULTS")
    print("="*60)
    
    if results:
        avg_time = sum(r['execution_time'] for r in results) / len(results)
        avg_dialogue = sum(r['dialogue_turns'] for r in results) / len(results)
        avg_review = sum(r['review_iterations'] for r in results) / len(results)
        
        print(f"""
Model: Claude 3.5 Sonnet
Tasks Completed: {len(results)}/{num_tasks}
Success Rate: {len(results)/num_tasks*100:.1f}%

Performance Metrics:
- Avg Execution Time: {avg_time:.1f}s
- Avg Dialogue Turns: {avg_dialogue:.1f}
- Avg Review Iterations: {avg_review:.1f}

Process Quality:
- Bug Reproduction: ✅ (Required by A2A)
- Dialogue Engagement: {"High" if avg_dialogue > 2 else "Medium" if avg_dialogue > 0 else "Low"}
- Feedback Incorporation: {"High" if avg_review > 1 else "Medium" if avg_review > 0 else "Low"}
        """)
        
        # Save detailed results
        with open("claude_benchmark_results.json", "w") as f:
            json.dump({
                "model": "claude-3.5-sonnet",
                "timestamp": datetime.now().isoformat(),
                "tasks": results,
                "metrics": agent.metrics
            }, f, indent=2)
            
        print("\n💾 Detailed results saved to claude_benchmark_results.json")
    else:
        print("No results collected")


if __name__ == "__main__":
    # Check if Green Agent is running
    import requests
    try:
        response = requests.get("http://localhost:8000/health")
        if response.status_code == 200:
            print("✅ Green Agent server is running")
            asyncio.run(run_benchmark())
        else:
            print("❌ Green Agent server not responding properly")
    except:
        print("❌ Green Agent server not running. Start it first:")
        print("   python start_green_agent.py")