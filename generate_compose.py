#!/usr/bin/env python3
"""
Generate Docker Compose from AgentBeats scenario.toml
Based on: https://docs.agentbeats.dev/tutorial/
"""

import argparse
import json
import os
import sys

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Error: Neither tomllib nor tomli available", file=sys.stderr)
        sys.exit(1)


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


def dict_to_yaml(d: dict, indent: int = 0) -> str:
    """Convert dict to YAML format without external dependency."""
    lines = []
    prefix = "  " * indent
    
    for key, value in d.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(dict_to_yaml(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, dict):
                    # First key on same line as dash
                    first = True
                    for k, v in item.items():
                        if first:
                            lines.append(f"{prefix}  - {k}: {json.dumps(v) if isinstance(v, (dict, list)) else v}")
                            first = False
                        else:
                            lines.append(f"{prefix}    {k}: {json.dumps(v) if isinstance(v, (dict, list)) else v}")
                else:
                    lines.append(f"{prefix}  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{prefix}{key}: {str(value).lower()}")
        elif isinstance(value, (int, float)):
            lines.append(f"{prefix}{key}: {value}")
        elif value is None:
            lines.append(f"{prefix}{key}: null")
        else:
            # String - quote if contains special chars
            if any(c in str(value) for c in [':', '#', '{', '}', '[', ']', ',', '&', '*', '?', '|', '-', '<', '>', '=', '!', '%', '@', '`']):
                lines.append(f'{prefix}{key}: "{value}"')
            else:
                lines.append(f"{prefix}{key}: {value}")
    
    return "\n".join(lines)


def generate_compose(scenario_path: str) -> str:
    """Generate Docker Compose configuration from scenario.toml."""
    with open(scenario_path, "rb") as f:
        scenario = tomllib.load(f)
    
    green_agent = scenario.get("green_agent", {})
    participants = scenario.get("participants", [])
    
    # Get green agent image
    green_id = green_agent.get("agentbeats_id", "")
    green_image = green_agent.get("image", fetch_agent_image(green_id))
    green_env = expand_env_vars(green_agent.get("env", {}))
    
    # Build services section
    services = {}
    
    # Green agent service
    services["green-agent"] = {
        "image": green_image,
        "container_name": "swebench-green",
        "environment": green_env,
        "ports": ["8000:8000"],
        "volumes": ["./output:/app/output", "./data:/app/data"],
        "networks": ["swebench-network"]
    }
    
    # Add participant services
    for i, participant in enumerate(participants):
        name = participant.get("name", f"purple-agent-{i}")
        p_id = participant.get("agentbeats_id", "")
        p_image = participant.get("image", fetch_agent_image(p_id))
        p_env = expand_env_vars(participant.get("env", {}))
        p_env["GREEN_AGENT_URL"] = "http://swebench-green:8000"
        
        services[name] = {
            "image": p_image,
            "container_name": name,
            "environment": p_env,
            "depends_on": ["green-agent"],
            "networks": ["swebench-network"]
        }
    
    # Build compose dict
    compose = {
        "version": "3.8",
        "services": services,
        "networks": {
            "swebench-network": {
                "driver": "bridge"
            }
        }
    }
    
    return dict_to_yaml(compose)


def main():
    parser = argparse.ArgumentParser(description="Generate Docker Compose from scenario.toml")
    parser.add_argument("--scenario", default="scenario.toml", help="Path to scenario.toml")
    parser.add_argument("--output", default="docker-compose.yml", help="Output file path")
    args = parser.parse_args()
    
    if not os.path.exists(args.scenario):
        print(f"Error: Scenario file not found: {args.scenario}", file=sys.stderr)
        sys.exit(1)
    
    yaml_content = generate_compose(args.scenario)
    
    with open(args.output, "w") as f:
        f.write(yaml_content)
    
    print(f"Generated {args.output} from {args.scenario}")


if __name__ == "__main__":
    main()
