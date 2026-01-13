#!/usr/bin/env python3
"""Main entry point for SWE-bench A2A implementation"""

import asyncio
import argparse
import logging
from pathlib import Path

from src.green_agent import GreenAgentService
from src.purple_agent import PurpleAgentWrapper, SimpleSolver, LLMSolver, MultiAgentTeam

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_green_agent(args):
    """Run the Green Agent Service"""
    logger.info("Starting Green Agent Service...")
    
    green_agent = GreenAgentService(
        name="SWE-bench Green Agent",
        version="1.0.0",
        host=args.host,
        port=args.port,
        enable_ambiguity=args.enable_ambiguity,
        enable_mutation=args.enable_mutation,
        purple_agent_url=args.purple_url,
        dataset_config=args.dataset_config,
    )
    
    # Initialize warm pool if using Docker
    if args.warm_pool:
        await green_agent.environment_orchestrator.initialize_warm_pool()
    
    # Load scenarios
    await green_agent.scenario_manager.load_scenarios()
    
    # Run the service
    await green_agent.run()


async def run_purple_agent(args):
    """Run a Purple Agent"""
    logger.info("Starting Purple Agent...")
    
    # Select solver
    if args.model == "simple-solver":
        solver = SimpleSolver(model_name=args.model)
    else:
        solver = LLMSolver(model_name=args.model)
    
    # Wrap it as a Purple Agent
    purple_agent = PurpleAgentWrapper(
        agent_name=f"Purple Agent - {args.model}",
        agent_version="1.0.0",
        solver_function=solver.solve,
        capabilities=["code-generation", "bug-fixing", "python"],
        host=args.host,
        port=args.port
    )
    
    # Run the agent
    await purple_agent.run()


async def run_multi_agent_team(args):
    """Run a multi-agent Purple Team"""
    logger.info("Starting Multi-Agent Team...")
    
    # Create the team
    team = MultiAgentTeam(
        team_name="Purple Team Alpha",
        architect_url=args.architect_url,
        developer_url=args.developer_url,
        reviewer_url=args.reviewer_url
    )
    
    # Discover agents
    await team.discover_agents()
    
    # Get team status
    status = await team.get_team_status()
    logger.info(f"Team status: {status}")
    
    # The team is now ready to receive tasks via A2A protocol


async def run_demo(args):
    """Run a demo evaluation"""
    logger.info("Running demo evaluation...")
    
    # Start Green Agent in background
    green_task = asyncio.create_task(run_green_agent(args))
    
    # Wait for Green Agent to start
    await asyncio.sleep(5)
    
    # Start Purple Agent in background
    purple_args = argparse.Namespace(
        host="0.0.0.0",
        port=8001,
        model="simple-solver"
    )
    purple_task = asyncio.create_task(run_purple_agent(purple_args))
    
    # Wait for Purple Agent to start
    await asyncio.sleep(5)
    
    # Now we would use A2A client to create a task
    from src.a2a import A2AClient
    
    client = A2AClient(agent_id="demo_client")
    
    # Create a task on the Green Agent
    task_id = await client.create_task(
        server_url="http://localhost:8000",
        title="Fix Django authentication bug",
        description="Users can access restricted content without proper authentication",
        resources={"scenario_id": "django__django-11099"},
        constraints={"ambiguity_level": "medium", "time_limit": 3600}
    )
    
    if task_id:
        logger.info(f"Created task: {task_id}")
        
        # Wait for completion
        result = await client.wait_for_task_completion(
            "http://localhost:8000",
            task_id,
            timeout=120
        )
        
        if result:
            logger.info(f"Task completed: {result}")
    
    # Clean up
    await client.close()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="SWE-bench A2A Implementation")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Green Agent command
    green_parser = subparsers.add_parser("green", help="Run Green Agent Service")
    green_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    green_parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    green_parser.add_argument("--enable-ambiguity", action="store_true", help="Enable ambiguity injection")
    green_parser.add_argument("--enable-mutation", action="store_true", help="Enable code mutation")
    green_parser.add_argument("--warm-pool", action="store_true", help="Initialize warm container pool")
    green_parser.add_argument("--purple-url", default=None, help="Purple agent base URL (e.g., http://localhost:8001)")
    green_parser.add_argument("--dataset-config", default="verified", help="SWE-bench dataset config (verified|lite|full|oracle)")
    
    # Purple Agent command
    purple_parser = subparsers.add_parser("purple", help="Run Purple Agent")
    purple_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    purple_parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    purple_parser.add_argument("--model", default="simple-solver", help="Model to use")
    
    # Multi-Agent Team command
    team_parser = subparsers.add_parser("team", help="Run Multi-Agent Team")
    team_parser.add_argument("--architect-url", default="http://localhost:8001", help="Architect agent URL")
    team_parser.add_argument("--developer-url", default="http://localhost:8002", help="Developer agent URL")
    team_parser.add_argument("--reviewer-url", default="http://localhost:8003", help="Reviewer agent URL")
    
    # Demo command
    demo_parser = subparsers.add_parser("demo", help="Run demo evaluation")
    
    args = parser.parse_args()
    
    if args.command == "green":
        asyncio.run(run_green_agent(args))
    elif args.command == "purple":
        asyncio.run(run_purple_agent(args))
    elif args.command == "team":
        asyncio.run(run_multi_agent_team(args))
    elif args.command == "demo":
        asyncio.run(run_demo(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()