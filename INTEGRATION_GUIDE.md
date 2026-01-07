# A2A SWEbench Integration Guide

This guide explains how to integrate the **A2A SWEbench Framework** with the original SWE-bench evaluation system.

## Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Integration Methods](#integration-methods)
5. [Running with SWE-bench](#running-with-swe-bench)
6. [API Reference](#api-reference)
7. [Examples](#examples)

## Overview

The A2A SWEbench Framework enhances the original SWE-bench by:
- **Preventing memorization** through dynamic code mutations
- **Self-healing** broken evaluation environments
- **Full trajectory capture** for debugging
- **LLM-powered synthesis** for automatic fixes
- **Standard A2A protocol** for agent communication

## Prerequisites

### Required
- Python 3.9+
- Docker 20.10+
- Git

### Optional (for full features)
- OpenAI API key (for LLM synthesis)
- PostgreSQL (for production deployment)
- Redis (for caching and pub/sub)
- Kubernetes (for scalable deployment)

## Installation

### 1. Clone the Repository

```bash
# Clone A2A SWEbench
git clone https://github.com/yourusername/swebench-a2a.git
cd swebench-a2a

# Clone original SWE-bench (if needed)
git clone https://github.com/princeton-nlp/SWE-bench.git
```

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install A2A SWEbench
pip install -e .

# Install additional dependencies
pip install openai docker redis asyncio
```

### 3. Set Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your configurations
export OPENAI_API_KEY='your-openai-api-key'  # Optional but recommended
export DATABASE_URL='sqlite:///./swebench.db'  # Or PostgreSQL URL
export A2A_SERVER_PORT=8080
```

## Integration Methods

### Method 1: Drop-in Replacement

Replace SWE-bench evaluation with A2A SWEbench:

```python
# Original SWE-bench
from swebench.harness.run_evaluation import run_evaluation

# A2A SWEbench replacement
from swebench_a2a import run_evaluation_a2a

# Run with anti-memorization
results = await run_evaluation_a2a(
    dataset="princeton-nlp/SWE-bench",
    model="your-model",
    enable_mutations=True,  # Prevent memorization
    enable_synthesis=True,  # Self-healing environments
    capture_trajectory=True  # Full action logging
)
```

### Method 2: A2A Protocol Wrapper

Wrap existing SWE-bench agents with A2A protocol:

```python
from swebench_a2a.agents import PurpleAgentWrapper
from your_solver import YourSWEbenchSolver

# Wrap your solver
solver = YourSWEbenchSolver()
a2a_agent = PurpleAgentWrapper(
    solver=solver,
    port=8001,
    name="My SWE-bench Agent"
)

# Start agent server
await a2a_agent.start()
```

### Method 3: Standalone Service

Run A2A SWEbench as a separate evaluation service:

```bash
# Start the A2A SWEbench server
python -m swebench_a2a.server --port 8080

# Submit evaluations via API
curl -X POST http://localhost:8080/api/v1/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "dataset": "princeton-nlp/SWE-bench",
    "model": "gpt-4",
    "tasks": ["task-123", "task-456"],
    "options": {
      "enable_mutations": true,
      "mutation_rate": 0.3,
      "capture_trajectory": true
    }
  }'
```

## Running with SWE-bench

### Step 1: Start A2A SWEbench Server

```bash
# Start the framework
python demo_server.py

# Or with full features
python main.py serve --enable-all
```

Server will be available at http://localhost:8080

### Step 2: Configure SWE-bench Dataset

```python
from swebench_a2a import DatasetAdapter

# Load original SWE-bench data
adapter = DatasetAdapter()
dataset = adapter.load_swebench_dataset(
    path="princeton-nlp/SWE-bench",
    split="test"
)

# Apply anti-memorization mutations
mutated_dataset = adapter.apply_mutations(
    dataset,
    mutation_types=["variable_rename", "function_reorder", "ast_transform"]
)
```

### Step 3: Run Evaluation

```python
from swebench_a2a import EvaluationRunner

runner = EvaluationRunner(
    a2a_server="http://localhost:8080",
    enable_synthesis=True,
    enable_monitoring=True
)

# Evaluate a single task
result = await runner.evaluate_task(
    task_id="django__django-11133",
    agent_endpoint="http://localhost:8001",  # Your agent
    timeout=300
)

# Evaluate full dataset
results = await runner.evaluate_dataset(
    dataset=mutated_dataset,
    agent_endpoint="http://localhost:8001",
    max_workers=4
)
```

### Step 4: Analyze Results

```python
from swebench_a2a import ResultAnalyzer

analyzer = ResultAnalyzer()

# Get comprehensive metrics
metrics = analyzer.compute_metrics(results)
print(f"Success Rate: {metrics['success_rate']:.2%}")
print(f"Memorization Score: {metrics['memorization_score']:.2f}")
print(f"Average Time: {metrics['avg_time']:.2f}s")

# Export trajectories for debugging
analyzer.export_trajectories(
    results,
    output_dir="./trajectories",
    format="json"
)

# Generate leaderboard
leaderboard = analyzer.generate_leaderboard(results)
```

## API Reference

### Core Endpoints

#### Create Evaluation Task
```http
POST /api/v1/tasks
Content-Type: application/json

{
  "repo": "django/django",
  "issue": "11133",
  "description": "Fix template rendering bug",
  "enable_mutations": true
}
```

#### Submit Agent Solution
```http
POST /api/v1/tasks/{task_id}/submit
Content-Type: application/json

{
  "agent_id": "agent_0001",
  "patch": "diff --git...",
  "trajectory": [...]
}
```

#### Get Task Status
```http
GET /api/v1/tasks/{task_id}

Response:
{
  "id": "task_0001",
  "status": "completed",
  "score": 0.85,
  "memorization_detected": false
}
```

### A2A Protocol Endpoints

#### Agent Registration
```http
POST /api/v1/agents
Content-Type: application/json

{
  "name": "My Agent",
  "type": "purple",
  "capabilities": ["code_generation", "debugging"],
  "endpoint": "http://my-agent:8001"
}
```

#### Agent Card Discovery
```http
GET /.well-known/agent-card.json

Response:
{
  "name": "A2A SWEbench",
  "version": "0.1.0",
  "protocols": ["a2a/v1"],
  "capabilities": ["evaluation", "synthesis", "mutation"]
}
```

## Examples

### Example 1: Basic Evaluation

```python
import asyncio
from swebench_a2a import quick_evaluate

async def main():
    # Simple evaluation with anti-memorization
    result = await quick_evaluate(
        task="django__django-11133",
        agent="http://my-agent:8001",
        prevent_memorization=True
    )
    
    print(f"Success: {result['success']}")
    print(f"Time: {result['time_taken']}s")
    print(f"Mutations Applied: {result['mutations']}")

asyncio.run(main())
```

### Example 2: Custom Mutation Strategy

```python
from swebench_a2a.mutations import MutationEngine

# Configure custom mutations
engine = MutationEngine(
    strategies=[
        "variable_rename",      # Rename variables
        "function_reorder",     # Reorder functions
        "loop_transform",       # Transform loops
        "dead_code_injection",  # Add decoy code
    ],
    mutation_rate=0.4  # 40% of code mutated
)

# Apply to task
mutated_task = engine.mutate_task(original_task)
```

### Example 3: With OpenAI Synthesis

```python
from swebench_a2a.synthesis import SynthesisEngine

# Enable OpenAI-powered fixing
synthesis = SynthesisEngine(
    provider="openai",
    api_key=os.getenv("OPENAI_API_KEY"),
    auto_fix=True
)

# Run evaluation with auto-fixing
result = await runner.evaluate_with_synthesis(
    task=task,
    synthesis_engine=synthesis
)
```

### Example 4: Trajectory Analysis

```python
from swebench_a2a.trajectory import TrajectoryAnalyzer

analyzer = TrajectoryAnalyzer()

# Load trajectory
trajectory = analyzer.load_trajectory("task_0001.json")

# Detect memorization patterns
memorization = analyzer.detect_memorization(trajectory)
if memorization['detected']:
    print(f"Memorization detected: {memorization['confidence']:.2%}")
    print(f"Suspicious patterns: {memorization['patterns']}")

# Compute metrics
metrics = analyzer.compute_metrics(trajectory)
print(f"Total actions: {metrics['total_actions']}")
print(f"Unique actions: {metrics['unique_actions']}")
print(f"Efficiency: {metrics['efficiency']:.2f}")
```

## Docker Integration

### Using Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  a2a-swebench:
    image: swebench-a2a:latest
    ports:
      - "8080:8080"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DATABASE_URL=postgresql://user:pass@db:5432/swebench
    volumes:
      - ./data:/app/data
      - /var/run/docker.sock:/var/run/docker.sock
    
  your-agent:
    image: your-agent:latest
    ports:
      - "8001:8001"
    environment:
      - A2A_SERVER=http://a2a-swebench:8080
    
  db:
    image: postgres:15
    environment:
      - POSTGRES_DB=swebench
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### Building the Docker Image

```bash
# Build A2A SWEbench image
docker build -t swebench-a2a:latest .

# Run with Docker
docker run -d \
  -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  swebench-a2a:latest
```

## Kubernetes Deployment

For production deployment:

```bash
# Deploy to Kubernetes
kubectl apply -k k8s/

# Check status
kubectl get pods -n swebench-a2a

# Access service
kubectl port-forward -n swebench-a2a svc/a2a-server 8080:8080
```

## Monitoring

Access monitoring dashboards:

- **Metrics**: http://localhost:9090/metrics
- **Health**: http://localhost:9090/health
- **Grafana**: http://localhost:3000 (if deployed)

## Troubleshooting

### Common Issues

#### 1. Docker Permission Denied
```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in
```

#### 2. OpenAI API Errors
```bash
# Check API key
echo $OPENAI_API_KEY

# Test connection
python -c "from swebench_a2a import test_openai; test_openai()"
```

#### 3. Port Already in Use
```bash
# Change port in .env
A2A_SERVER_PORT=8081

# Or kill existing process
lsof -i :8080
kill -9 <PID>
```

## Performance Tuning

### Optimization Settings

```python
# Configure for performance
config = {
    "max_workers": 8,           # Parallel evaluations
    "cache_enabled": True,       # Redis caching
    "mutation_cache": True,      # Cache mutations
    "synthesis_timeout": 30,     # Synthesis timeout
    "docker_warm_pool": 5,       # Pre-warmed containers
}

runner = EvaluationRunner(**config)
```

## Support

- **Documentation**: https://github.com/swebench-a2a/docs
- **Issues**: https://github.com/swebench-a2a/issues
- **Discord**: https://discord.gg/swebench-a2a

## License

MIT License - See LICENSE file for details.