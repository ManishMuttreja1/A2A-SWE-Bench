#!/usr/bin/env python3
"""
SWEbench-A2A Framework Demo with OpenAI Integration
Demonstrates real LLM-powered code synthesis and repair
"""

import asyncio
import os
import sys
import logging
from datetime import datetime

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_openai_integration():
    """Demonstrate OpenAI integration capabilities"""
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║        SWEbench-A2A Framework - OpenAI Integration Demo      ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        print("\nTo use OpenAI integration:")
        print("1. Get an API key from https://platform.openai.com/api-keys")
        print("2. Set it in your environment:")
        print("   export OPENAI_API_KEY='your-api-key-here'")
        print("\n⚠️  Running in mock mode without OpenAI...")
        return await demo_mock_mode()
    
    print(f"✅ OpenAI API key found: {api_key[:8]}...")
    
    try:
        from src.llm.openai_client import get_openai_client, test_openai_connection
        
        # Test connection
        print("\n🔍 Testing OpenAI connection...")
        if await test_openai_connection():
            print("✅ OpenAI connection successful!")
        else:
            print("❌ OpenAI connection failed")
            return
        
        # Get client
        client = get_openai_client()
        
        # Demo 1: Code Fix Generation
        print("\n" + "="*60)
        print("Demo 1: Automatic Code Fix Generation")
        print("="*60)
        
        error_message = """
AttributeError: 'NoneType' object has no attribute 'split'
  File "process.py", line 42, in process_data
    parts = data.split(',')
"""
        
        code_context = """
def process_data(data):
    # Process CSV data
    parts = data.split(',')
    return [p.strip() for p in parts]
"""
        
        print(f"Error: {error_message.strip()}")
        print(f"\nOriginal Code:\n{code_context}")
        
        print("\n🤖 Generating fix with OpenAI...")
        fix = await client.generate_code_fix(
            error_message=error_message,
            code_context=code_context,
            file_path="process.py"
        )
        
        if fix:
            print(f"\n✅ Generated Fix:\n{fix}")
        else:
            print("❌ Failed to generate fix")
        
        # Demo 2: Test Failure Analysis
        print("\n" + "="*60)
        print("Demo 2: Test Failure Analysis")
        print("="*60)
        
        test_output = """
FAILED test_calculator.py::test_division - ZeroDivisionError: division by zero
"""
        
        test_code = """
def test_division():
    from calculator import divide
    assert divide(10, 2) == 5
    assert divide(10, 0) == None  # Should handle division by zero
"""
        
        print(f"Test Failure:\n{test_output}")
        print(f"\nTest Code:\n{test_code}")
        
        print("\n🤖 Analyzing with OpenAI...")
        analysis = await client.analyze_test_failure(
            test_output=test_output,
            test_code=test_code
        )
        
        print(f"\n📊 Analysis Results:")
        print(f"  Root Cause: {analysis.get('root_cause', 'Unknown')}")
        print(f"  Confidence: {analysis.get('confidence', 0):.2f}")
        if analysis.get('fix'):
            print(f"\n✅ Suggested Fix:\n{analysis['fix']}")
        
        # Demo 3: Environment Fix Synthesis
        print("\n" + "="*60)
        print("Demo 3: Environment Setup Fix")
        print("="*60)
        
        env_error = """
ERROR: Could not find a version that satisfies the requirement tensorflow==2.15.0
ERROR: No matching distribution found for tensorflow==2.15.0
"""
        
        print(f"Environment Error:\n{env_error}")
        
        print("\n🤖 Synthesizing fix with OpenAI...")
        env_fix = await client.synthesize_environment_fix(
            error_type="dependency",
            error_details=env_error,
            requirements="tensorflow==2.15.0\nnumpy>=1.20.0"
        )
        
        if env_fix:
            print("\n✅ Environment Fix:")
            if "requirements" in env_fix:
                print(f"\nFixed requirements.txt:\n{env_fix['requirements']}")
            if "commands" in env_fix:
                print(f"\nCommands to run:")
                for cmd in env_fix['commands']:
                    print(f"  $ {cmd}")
        
        # Demo 4: Test Generation
        print("\n" + "="*60)  
        print("Demo 4: Automatic Test Generation")
        print("="*60)
        
        function_sig = "def calculate_discount(price: float, discount_percent: float) -> float:"
        function_doc = "Calculate the discounted price given original price and discount percentage"
        
        print(f"Function:\n{function_sig}")
        print(f"Doc: {function_doc}")
        
        print("\n🤖 Generating tests with OpenAI...")
        test_cases = await client.generate_test_cases(
            function_signature=function_sig,
            function_docstring=function_doc
        )
        
        if test_cases:
            print(f"\n✅ Generated {len(test_cases)} test cases:")
            for i, test in enumerate(test_cases, 1):
                print(f"\nTest {i}:\n{test[:200]}...")
        
        # Show statistics
        stats = client.get_statistics()
        print("\n" + "="*60)
        print("📊 OpenAI Usage Statistics")
        print("="*60)
        print(f"  Total Requests: {stats['requests']}")
        print(f"  Tokens Used: {stats['tokens_used']}")
        print(f"  Cache Hits: {stats['cache_hits']}")
        print(f"  Errors: {stats['errors']}")
        print(f"  Model: {stats['model']}")
        
    except ImportError as e:
        print(f"\n❌ OpenAI library not installed: {e}")
        print("Install with: pip install openai")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logger.error(f"Demo error: {e}", exc_info=True)


async def demo_mock_mode():
    """Run demo in mock mode without OpenAI"""
    
    print("\n🎭 Running in Mock Mode (No OpenAI)")
    print("="*50)
    
    # Simulate some operations
    demos = [
        ("Code Fix", "Added null check: if data is not None: ..."),
        ("Test Analysis", "Missing error handling for edge case"),
        ("Environment Fix", "Use tensorflow==2.14.0 instead"),
        ("Test Generation", "Generated 5 comprehensive test cases")
    ]
    
    for name, result in demos:
        print(f"\n✓ {name}: {result}")
        await asyncio.sleep(0.5)
    
    print("\n" + "="*50)
    print("ℹ️  To enable real OpenAI integration:")
    print("1. Set OPENAI_API_KEY environment variable")
    print("2. Run: pip install openai")
    print("3. Re-run this demo")


async def main():
    """Main entry point"""
    
    # Print header
    print("""
    ███████╗██╗    ██╗███████╗██████╗ ███████╗███╗   ██╗ ██████╗██╗  ██╗
    ██╔════╝██║    ██║██╔════╝██╔══██╗██╔════╝████╗  ██║██╔════╝██║  ██║
    ███████╗██║ █╗ ██║█████╗  ██████╔╝█████╗  ██╔██╗ ██║██║     ███████║
    ╚════██║██║███╗██║██╔══╝  ██╔══██╗██╔══╝  ██║╚██╗██║██║     ██╔══██║
    ███████║╚███╔███╔╝███████╗██████╔╝███████╗██║ ╚████║╚██████╗██║  ██║
    ╚══════╝ ╚══╝╚══╝ ╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═══╝ ╚═════╝╚═╝  ╚═╝
                        A2A Framework v0.1.0
    """)
    
    await demo_openai_integration()
    
    print("\n✨ Demo Complete!")
    print("\nNext Steps:")
    print("1. Set up your OPENAI_API_KEY")
    print("2. Run the full framework: python main.py")
    print("3. Deploy with Kubernetes: kubectl apply -k k8s/")
    print("\n📚 Documentation: https://github.com/swebench-a2a")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        logger.error("Fatal error", exc_info=True)