#!/usr/bin/env python3
"""
Generate Docker Compose from AgentBeats scenario.toml
Based on: https://docs.agentbeats.dev/tutorial/
"""

import argparse
import os
import sys

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import yaml


def fetch_agent_image(agentbeats_id: str) -> str:
    """Fetch Docker image for an AgentBeats agent ID."""
    # Map agent IDs to their Docker images
    # Green Agent: 019bbe88-b868-7bf2-8e98-fe4e71a03e35
    # Purple Agent: 019bbec8-5656-7792-b572-21fcf6cc36fb
    if agentbeats_id == "019bbe88-b868-7bf2-8e98-fe4e71a03e35":
        return "ghcr.io/manishmuttreja1/a2a-swe-bench-green:latest"
    elif agentbeats_id == "019bbec8-5656-7792-b572-21fcf6cc36fb":
        return "ghcr.io/manishmuttreja1/a2a-swe-bench-purple:latest"
    elif "green" in agentbeats_id.lower():
        return "ghcr.io/manishmuttreja1/a2a-swe-bench-green:latest"
    else:
        return "ghcr.io/manishmuttreja1/a2a-swe-bench-purple:latest"


def expand_env_vars(env_dict: dict) -> dict:
    """Expand environment variable references like ${VAR}."""
    result = {}
    for key, value in env_dict.items():
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            result[key] = os.environ.get(env_var, "")
        else:
            result[key] = value
    return result


def generate_compose(scenario_path: str) -> dict:
    """Generate Docker Compose configuration from scenario.toml."""
    with open(scenario_path, "rb") as f:
        scenario = tomllib.load(f)
    
    green_agent = scenario.get("green_agent", {})
    participants = scenario.get("participants", [])
    config = scenario.get("config", {})
    
    # Get green agent image
    green_id = green_agent.get("agentbeats_id", "")
    green_image = green_agent.get("image", fetch_agent_image(green_id))
    green_env = green_agent.get("env", {})
    
    services = {
        "green-agent": {
            "image": green_image,
            "container_name": "swebench-green",
            "environment": expand_env_vars(green_env),
            "ports": ["8000:8000"],
            "volumes": [
                "./output:/app/output",
                "./data:/app/data"
            ],
            "networks": ["swebench-network"]
        }
    }
    
    # Add participant services
    for i, participant in enumerate(participants):
        name = participant.get("name", f"purple-agent-{i}")
        p_id = participant.get("agentbeats_id", "")
        p_image = participant.get("image", fetch_agent_image(p_id))
        p_env = participant.get("env", {})
        p_env["GREEN_AGENT_URL"] = "http://swebench-green:8000"
        
        services[name] = {
            "image": p_image,
            "container_name": name,
            "environment": expand_env_vars(p_env),
            "depends_on": ["green-agent"],
            "networks": ["swebench-network"]
        }
    
    compose = {
        "version": "3.8",
        "services": services,
        "networks": {
            "swebench-network": {
                "driver": "bridge"
            }
        }
    }
    
    return compose


def main():
    parser = argparse.ArgumentParser(description="Generate Docker Compose from scenario.toml")
    parser.add_argument("--scenario", default="scenario.toml", help="Path to scenario.toml")
    parser.add_argument("--output", default="docker-compose.yml", help="Output file path")
    args = parser.parse_args()
    
    if not os.path.exists(args.scenario):
        print(f"Error: Scenario file not found: {args.scenario}", file=sys.stderr)
        sys.exit(1)
    
    compose = generate_compose(args.scenario)
    
    with open(args.output, "w") as f:
        yaml.dump(compose, f, default_flow_style=False, sort_keys=False)
    
    print(f"Generated {args.output} from {args.scenario}")


if __name__ == "__main__":
    main()
