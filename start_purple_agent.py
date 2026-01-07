#!/usr/bin/env python3
"""Purple Agent starter for SWE-bench tasks using Claude Sonnet"""

import asyncio
import os
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.a2a.client import A2AClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for Purple Agent"""
    green_agent_url = os.getenv("GREEN_AGENT_URL", "http://green-agent:8000")
    
    # Import the Claude Purple Agent
    from claude_purple_agent import ClaudeSonnetAgent
    
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║           Claude Sonnet Purple Agent for SWE-bench           ║
║                  Starting connection...                       ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Initialize the agent
    agent = ClaudeSonnetAgent()
    
    print(f"Purple Agent connecting to {green_agent_url}")
    
    # Set the correct URL
    agent.a2a_client.base_url = green_agent_url
    
    # Request and solve tasks in a loop
    while True:
        try:
            # Request a task from the Green Agent
            task = await agent.a2a_client.request_task()
            print(f"Received task: {task.id}")
            print(f"Description: {task.description[:100]}...")
            
            # Solve the task
            result = await agent.solve_task(task)
            print(f"Task {task.id} completed with status: {result.get('status', 'unknown')}")
            
            # Small delay between tasks
            await asyncio.sleep(2)
            
        except KeyboardInterrupt:
            print("\nShutting down Purple Agent...")
            break
        except Exception as e:
            logger.error(f"Error processing task: {e}")
            print(f"Error: {e}")
            print("Retrying in 5 seconds...")
            await asyncio.sleep(5)
    
    print("Purple Agent shutdown complete.")


if __name__ == "__main__":
    # Check for help
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
Usage: python start_purple_agent.py [OPTIONS]

Environment Variables:
  GREEN_AGENT_URL      URL of the Green Agent server [default: http://green-agent:8000]
  ANTHROPIC_API_KEY    API key for Claude Sonnet (optional, uses mock if not provided)

Examples:
  # Connect to local Green Agent
  GREEN_AGENT_URL=http://localhost:8000 python start_purple_agent.py
  
  # Connect to docker Green Agent
  python start_purple_agent.py
  
  # With Anthropic API key
  ANTHROPIC_API_KEY=sk-ant-... python start_purple_agent.py
        """)
        sys.exit(0)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Purple Agent shutdown.")