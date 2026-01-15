#!/usr/bin/env python3
"""
Start the A2A Green Agent Server for SWE-bench Evaluation

This server acts as the evaluator that:
1. Serves SWE-bench tasks to Purple Agents
2. Manages Docker environments
3. Enforces reproduction gates
4. Conducts dialogue and code review
5. Calculates comprehensive scores
"""

import asyncio
import logging
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def start_green_agent_server():
    """Start the Green Agent A2A server"""
    
    print("""
╔═══════════════════════════════════════════════════════════════╗
║           A2A Green Agent Server for SWE-bench               ║
║           Complete Evaluation System Starting...             ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Import components
    from src.a2a.server import A2AServer
    from src.a2a.protocol import AgentCard
    from src.swebench.integration import SWEBenchIntegration
    from src.green_agent.reproduction_gate import ReproductionGate
    from src.green_agent.dialogue_manager import DialogueManager
    from src.green_agent.code_reviewer import SeniorDeveloperReviewer
    from src.mutation.retro_holdout import RetroHoldoutGenerator
    from src.scoring.advanced_metrics import AdvancedMetrics
    
    # Configuration
    config = {
        "dataset": os.getenv("SWEBENCH_DATASET", "verified"),
        "docker_enabled": os.getenv("DOCKER_ENABLED", "false").lower() == "true",
        "enable_dialogue": os.getenv("ENABLE_DIALOGUE", "true").lower() == "true",
        "enable_reproduction": os.getenv("ENABLE_REPRODUCTION", "true").lower() == "true",
        "enable_review": os.getenv("ENABLE_REVIEW", "true").lower() == "true",
        "enable_mutations": os.getenv("ENABLE_MUTATIONS", "false").lower() == "true",
        "port": int(os.getenv("PORT", "8000"))
    }
    
    print("Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    
    # Initialize SWE-bench integration
    print("\n📚 Initializing SWE-bench integration...")
    swebench = SWEBenchIntegration(
        dataset_config=config["dataset"],
        docker_enabled=config["docker_enabled"],
        cache_dir=Path("data/cache")
    )
    
    try:
        await swebench.initialize()
        stats = await swebench.get_statistics()
        print(f"✅ Loaded {stats['dataset']['total_instances']} instances")
    except Exception as e:
        print(f"⚠️  Using fallback data: {e}")
    
    # Initialize evaluation components
    components = {
        "reproduction_gate": ReproductionGate(strict_mode=config["enable_reproduction"]),
        "dialogue_manager": DialogueManager() if config["enable_dialogue"] else None,
        "code_reviewer": SeniorDeveloperReviewer() if config["enable_review"] else None,
        "retro_holdout": RetroHoldoutGenerator() if config["enable_mutations"] else None,
        "metrics": AdvancedMetrics()
    }
    
    # Create agent card
    agent_card = AgentCard(
        name="SWE-bench Green Agent",
        version="1.0.0",
        capabilities=[
            "swe-bench-evaluation",
            "issue2test-reproduction",
            "interactive-dialogue",
            "code-review",
            "anti-contamination",
            "comprehensive-scoring"
        ],
        endpoints={
            "task": "/a2a/task",
            "status": "/a2a/task/{task_id}",
            "submit": "/a2a/task/{task_id}/submit",
            "stream": "/a2a/task/{task_id}/stream"
        },
        description="A2A-compliant evaluator for SWE-bench with advanced features"
    )
    
    # Define task handler
    async def handle_task(task):
        """Handle incoming task requests"""
        logger.info(f"Handling task: {task.id}")
        
        try:
            # Create SWE-bench task
            swe_task = await swebench.create_task_from_instance(
                random_selection=True
            )
            
            # Apply dialogue if enabled
            if config["enable_dialogue"] and components["dialogue_manager"]:
                dialogue_result = await components["dialogue_manager"].initiate_dialogue(
                    task.id,
                    swe_task.description,
                    ambiguity_level="medium"
                )
                task.description = dialogue_result["description"]
            
            # Return task configuration
            return {
                "success": True,
                "task": swe_task,
                "features_enabled": {
                    "dialogue": config["enable_dialogue"],
                    "reproduction": config["enable_reproduction"],
                    "review": config["enable_review"],
                    "mutations": config["enable_mutations"]
                }
            }
            
        except Exception as e:
            logger.error(f"Error handling task: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # Create A2A server
    print("\n🚀 Starting A2A server...")
    server = A2AServer(
        agent_card=agent_card,
        task_handler=handle_task,
        port=config["port"]
    )
    
    # Store components for access
    server.components = components
    server.swebench = swebench
    
    print(f"""
✅ Green Agent Server Ready!

📡 Endpoints:
   Agent Card: http://localhost:{config["port"]}/.well-known/agent-card.json
   Health:     http://localhost:{config["port"]}/health
   Tasks:      http://localhost:{config["port"]}/a2a/task

🎯 Features Enabled:
   Dialogue:      {'✅' if config['enable_dialogue'] else '❌'}
   Reproduction:  {'✅' if config['enable_reproduction'] else '❌'}
   Code Review:   {'✅' if config['enable_review'] else '❌'}
   Mutations:     {'✅' if config['enable_mutations'] else '❌'}

💡 To connect a Purple Agent:
   python start_purple_agent.py --server http://localhost:{config["port"]}

Press Ctrl+C to stop the server.
    """)
    
    # Run server (use run_async since we're already in an async context)
    await server.run_async()


async def main():
    """Main entry point"""
    try:
        await start_green_agent_server()
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down Green Agent server...")
    except Exception as e:
        logger.error(f"Server error: {e}")
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    # Check for help
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
Usage: python start_green_agent.py [OPTIONS]

Environment Variables:
  SWEBENCH_DATASET     Dataset to use (verified, lite, full) [default: verified]
  DOCKER_ENABLED        Enable Docker environments (true/false) [default: false]
  ENABLE_DIALOGUE       Enable dialogue system (true/false) [default: true]
  ENABLE_REPRODUCTION   Enable reproduction gate (true/false) [default: true]
  ENABLE_REVIEW         Enable code review (true/false) [default: true]
  ENABLE_MUTATIONS      Enable mutations (true/false) [default: false]
  PORT                  Server port [default: 8000]

Examples:
  # Basic start
  python start_green_agent.py
  
  # With Docker and all features
  DOCKER_ENABLED=true ENABLE_MUTATIONS=true python start_green_agent.py
  
  # Use Lite dataset on different port
  SWEBENCH_DATASET=lite PORT=8080 python start_green_agent.py
        """)
        sys.exit(0)
    
    asyncio.run(main())