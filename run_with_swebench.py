#!/usr/bin/env python3
"""
A2A SWEbench - Simple Integration Script
Run SWE-bench evaluations with A2A enhancements
"""

import json
import random
import hashlib
from datetime import datetime


def print_header():
    print("""
╔════════════════════════════════════════════════════════════╗
║              A2A SWEbench Integration Guide                ║
╚════════════════════════════════════════════════════════════╝

The A2A SWEbench Framework enhances SWE-bench with:
✅ Anti-memorization through code mutations
✅ Self-healing environment synthesis
✅ Full trajectory capture
✅ OpenAI-powered fixes
    """)


def show_integration_steps():
    """Show how to integrate with SWE-bench"""
    
    print("📚 INTEGRATION METHODS\n")
    print("="*60)
    
    print("\n1️⃣  METHOD 1: Drop-in Replacement\n")
    print("Replace your SWE-bench evaluation code:")
    print("""
# Original SWE-bench:
from swebench.harness.run_evaluation import run_evaluation
results = run_evaluation(dataset="princeton-nlp/SWE-bench")

# With A2A SWEbench:
from swebench_a2a import run_evaluation_a2a
results = run_evaluation_a2a(
    dataset="princeton-nlp/SWE-bench",
    enable_mutations=True,    # Prevent memorization
    enable_synthesis=True,    # Auto-fix environments
    capture_trajectory=True   # Full action logging
)
    """)
    
    print("\n2️⃣  METHOD 2: Wrap Your Agent\n")
    print("Add A2A protocol to existing agents:")
    print("""
from swebench_a2a.agents import PurpleAgentWrapper

# Wrap your existing solver
wrapped_agent = PurpleAgentWrapper(
    solver=your_swe_bench_solver,
    port=8001,
    enable_monitoring=True
)

# Start the wrapped agent
wrapped_agent.start()
    """)
    
    print("\n3️⃣  METHOD 3: API Integration\n")
    print("Use A2A SWEbench as a service:")
    print("""
# Start A2A SWEbench server
python demo_server.py

# Submit evaluations via API
curl -X POST http://localhost:8080/api/v1/tasks \\
  -H "Content-Type: application/json" \\
  -d '{
    "repo": "django/django",
    "issue": "11133",
    "enable_mutations": true
  }'
    """)


def show_mutation_examples():
    """Show mutation examples"""
    
    print("\n🔀 ANTI-MEMORIZATION MUTATIONS\n")
    print("="*60)
    
    original_code = """
def calculate_discount(price, discount_percent):
    discount = price * (discount_percent / 100)
    return price - discount
"""
    
    mutated_code = """
def calculate_discount(amount, reduction_rate):
    reduction = amount * (reduction_rate / 100)
    return amount - reduction
"""
    
    print("Original Code:")
    print(original_code)
    
    print("Mutated Code (prevents memorization):")
    print(mutated_code)
    
    print("\nMutation Types Applied:")
    print("• Variable renaming: price → amount")
    print("• Parameter renaming: discount_percent → reduction_rate")
    print("• Semantic preservation: Functionality unchanged")


def show_openai_integration():
    """Show OpenAI integration"""
    
    print("\n🤖 OPENAI INTEGRATION\n")
    print("="*60)
    
    print("\nSetup:")
    print("""
# Set your OpenAI API key
export OPENAI_API_KEY='your-api-key'

# Install OpenAI library
pip install openai

# Run with OpenAI synthesis
python demo_openai.py
    """)
    
    print("\nCapabilities:")
    print("• Automatic code fix generation")
    print("• Test failure analysis")
    print("• Environment repair")
    print("• Test case generation")
    
    print("\nExample Usage:")
    print("""
from swebench_a2a.llm import OpenAIClient

client = OpenAIClient()

# Fix a test failure automatically
fix = await client.generate_code_fix(
    error_message="AttributeError: 'NoneType' has no attribute 'split'",
    code_context=failing_code
)
    """)


def show_quick_start():
    """Show quick start commands"""
    
    print("\n🚀 QUICK START\n")
    print("="*60)
    
    commands = [
        ("Start A2A server", "python demo_server.py"),
        ("Access dashboard", "open http://localhost:8080"),
        ("Run integration demo", "python swebench_integration.py"),
        ("Run with OpenAI", "python demo_openai.py"),
        ("Deploy with Docker", "docker-compose up -d"),
        ("Deploy to Kubernetes", "kubectl apply -k k8s/")
    ]
    
    for desc, cmd in commands:
        print(f"\n{desc}:")
        print(f"  $ {cmd}")


def show_configuration():
    """Show configuration options"""
    
    print("\n⚙️  CONFIGURATION\n")
    print("="*60)
    
    print("\nEnvironment Variables:")
    config = {
        "OPENAI_API_KEY": "Your OpenAI API key",
        "A2A_SERVER_PORT": "Server port (default: 8080)",
        "DATABASE_URL": "Database connection string",
        "ENABLE_MUTATIONS": "Enable anti-memorization (true/false)",
        "MUTATION_RATE": "Mutation probability (0.0-1.0)",
        "SYNTHESIS_TIMEOUT": "Synthesis timeout in seconds"
    }
    
    for key, desc in config.items():
        print(f"  {key}: {desc}")
    
    print("\nConfiguration File (.env):")
    print("""
# .env file example
OPENAI_API_KEY=sk-your-key-here
A2A_SERVER_PORT=8080
DATABASE_URL=sqlite:///./swebench.db
ENABLE_MUTATIONS=true
MUTATION_RATE=0.3
    """)


def simulate_evaluation():
    """Simulate an evaluation run"""
    
    print("\n📊 SIMULATED EVALUATION\n")
    print("="*60)
    
    tasks = [
        ("django__django-11133", "django/django", "#11133"),
        ("scikit-learn__scikit-learn-13142", "scikit-learn/scikit-learn", "#13142"),
        ("matplotlib__matplotlib-8761", "matplotlib/matplotlib", "#8761"),
        ("pandas__pandas-21543", "pandas-dev/pandas", "#21543"),
        ("numpy__numpy-14832", "numpy/numpy", "#14832")
    ]
    
    print(f"\nEvaluating {len(tasks)} SWE-bench tasks...\n")
    
    results = []
    for task_id, repo, issue in tasks:
        # Simulate evaluation
        success = random.random() > 0.4
        score = random.random() if success else 0
        time_taken = random.uniform(5, 30)
        mutations = random.random() > 0.5
        
        result = {
            "task": task_id,
            "success": success,
            "score": score,
            "time": time_taken,
            "mutations": mutations
        }
        results.append(result)
        
        status = "✅" if success else "❌"
        mut_status = "🔀" if mutations else "  "
        print(f"{status} {mut_status} {task_id[:30]:30} | Score: {score:.2f} | Time: {time_taken:.1f}s")
    
    # Statistics
    successful = sum(1 for r in results if r["success"])
    total = len(results)
    avg_score = sum(r["score"] for r in results) / total
    avg_time = sum(r["time"] for r in results) / total
    with_mutations = sum(1 for r in results if r["mutations"])
    
    print("\n" + "="*60)
    print("EVALUATION SUMMARY")
    print("="*60)
    print(f"Success Rate: {successful}/{total} ({successful/total*100:.1f}%)")
    print(f"Average Score: {avg_score:.3f}")
    print(f"Average Time: {avg_time:.1f} seconds")
    print(f"With Mutations: {with_mutations}/{total}")
    print(f"Memorization Prevention: {with_mutations/total*100:.1f}%")


def main():
    """Main entry point"""
    
    print_header()
    
    while True:
        print("\n" + "="*60)
        print("SELECT AN OPTION:")
        print("="*60)
        print("1. Show Integration Methods")
        print("2. Show Mutation Examples")
        print("3. Show OpenAI Integration")
        print("4. Show Quick Start Commands")
        print("5. Show Configuration Options")
        print("6. Run Simulated Evaluation")
        print("7. Exit")
        print()
        
        try:
            choice = input("Enter choice (1-7): ").strip()
            
            if choice == "1":
                show_integration_steps()
            elif choice == "2":
                show_mutation_examples()
            elif choice == "3":
                show_openai_integration()
            elif choice == "4":
                show_quick_start()
            elif choice == "5":
                show_configuration()
            elif choice == "6":
                simulate_evaluation()
            elif choice == "7":
                print("\n✨ Thank you for using A2A SWEbench!")
                print("📚 Documentation: https://github.com/swebench-a2a")
                break
            else:
                print("Invalid choice, please try again.")
                
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()