#!/usr/bin/env python3
"""Purple Agent starter for SWE-bench tasks - supports OpenAI and Anthropic"""

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


class MultiProviderPurpleAgent:
    """Purple Agent that supports multiple LLM providers"""
    
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        self.model = os.getenv("LLM_MODEL", self._default_model())
        
        green_agent_url = os.getenv("GREEN_AGENT_URL", "http://green-agent:8000")
        self.a2a_client = A2AClient(
            agent_id=f"{self.provider}-purple",
            base_url=green_agent_url
        )
        
        # Initialize the appropriate client
        if self.provider == "anthropic":
            import httpx
            self.api_key = os.getenv("ANTHROPIC_API_KEY")
            if not self.api_key:
                raise ValueError("ANTHROPIC_API_KEY required for Anthropic provider")
            self.api_url = "https://api.anthropic.com/v1/messages"
            self.headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
        elif self.provider == "openai":
            from openai import AsyncOpenAI
            self.api_key = os.getenv("OPENAI_API_KEY")
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY required for OpenAI provider")
            self.client = AsyncOpenAI(api_key=self.api_key)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
        
        logger.info(f"Initialized {self.provider} Purple Agent with model: {self.model}")
    
    def _default_model(self):
        """Get default model for provider"""
        if self.provider == "anthropic":
            return "claude-sonnet-4-5-20250929"
        else:
            return "gpt-4o"
    
    async def _call_llm(self, prompt: str, max_tokens: int = 4096) -> str:
        """Call the LLM API based on provider"""
        if self.provider == "anthropic":
            import httpx
            payload = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.api_url, 
                    headers=self.headers, 
                    json=payload, 
                    timeout=120.0
                )
                if resp.status_code != 200:
                    raise Exception(f"API error {resp.status_code}: {resp.text[:200]}")
                return resp.json()["content"][0]["text"]
        else:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert software engineer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            return response.choices[0].message.content
    
    async def solve_task(self, task) -> dict:
        """Solve a SWE-bench task"""
        problem = ""
        for part in task.parts:
            if hasattr(part, 'content'):
                problem += part.content + "\n"
        
        prompt = f"""You are an expert software engineer. Generate a minimal patch to fix this bug.

Problem:
{problem[:3000]}

Generate ONLY the unified diff patch (starting with --- and +++). No explanation."""

        try:
            patch = await self._call_llm(prompt)
            
            # Submit the patch
            from src.a2a.protocol import Artifact, Part, PartType
            artifact = Artifact(
                type="patch_submission",
                parts=[Part(type=PartType.FILE_DIFF, content=patch)]
            )
            await self.a2a_client.submit_artifact(task.id, artifact)
            
            return {"status": "completed", "patch_length": len(patch)}
        except Exception as e:
            logger.error(f"Error solving task: {e}")
            return {"status": "failed", "error": str(e)}


async def main():
    """Main entry point for Purple Agent"""
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o")
    
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║           Multi-Provider Purple Agent for SWE-bench           ║
║                  Provider: {provider.upper():^10}                       ║
║                  Model: {model[:20]:^20}               ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Initialize the agent
    agent = MultiProviderPurpleAgent()
    
    green_agent_url = os.getenv("GREEN_AGENT_URL", "http://green-agent:8000")
    print(f"Purple Agent connecting to {green_agent_url}")
    
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
  LLM_PROVIDER         LLM provider: "openai" or "anthropic" [default: openai]
  LLM_MODEL            Model name [default: gpt-4o or claude-sonnet-4-5-20250929]
  OPENAI_API_KEY       API key for OpenAI (required if provider=openai)
  ANTHROPIC_API_KEY    API key for Anthropic (required if provider=anthropic)

Examples:
  # Run with OpenAI GPT-4o
  LLM_PROVIDER=openai LLM_MODEL=gpt-4o python start_purple_agent.py
  
  # Run with Claude Sonnet
  LLM_PROVIDER=anthropic LLM_MODEL=claude-sonnet-4-5-20250929 python start_purple_agent.py
  
  # Run with GPT-5.2
  LLM_PROVIDER=openai LLM_MODEL=gpt-5.2 python start_purple_agent.py
        """)
        sys.exit(0)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Purple Agent shutdown.")
