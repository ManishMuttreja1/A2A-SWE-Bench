# Plan to Run SWE-bench with A2A System

## Overview
This plan outlines the steps to run actual SWE-bench evaluations using our complete A2A implementation.

## Prerequisites Check

### System Requirements
- Python 3.9+
- Docker Desktop (for environment isolation)
- 16GB+ RAM recommended
- 50GB+ free disk space

### Required API Keys
- OpenAI API key (optional, for LLM features)
- GitHub token (optional, for private repos)

## Step-by-Step Execution Plan

### Phase 1: Environment Setup

#### 1.1 Install Dependencies
```bash
# Create and activate virtual environment
python3 -m venv venv_swebench
source venv_swebench/bin/activate

# Install core dependencies
pip install -r requirements.txt

# Install SWE-bench specific packages
pip install swebench datasets huggingface-hub
pip install docker gitpython
pip install pydantic fastapi uvicorn
pip install sqlalchemy aiofiles
```

#### 1.2 Download SWE-bench Dataset
```python
# Download from HuggingFace Hub
from datasets import load_dataset

# Start with SWE-bench Lite (300 instances) for testing
dataset = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")

# Save locally for offline use
dataset.save_to_disk("data/swebench_lite")
```

### Phase 2: Start A2A Infrastructure

#### 2.1 Start Green Agent Server
```python
# File: start_green_agent.py
import asyncio
from src.green_agent.service import GreenAgentService
from src.swebench.integration import SWEBenchIntegration

async def main():
    # Initialize SWE-bench integration
    swebench = SWEBenchIntegration(
        dataset_config="lite",  # Start with Lite dataset
        docker_enabled=True,
        cache_dir="data/cache"
    )
    await swebench.initialize()
    
    # Create Green Agent service
    green_agent = GreenAgentService(
        swebench_integration=swebench,
        enable_dialogue=True,
        enable_reproduction_gate=True,
        enable_code_review=True,
        enable_mutations=False  # Disable initially for testing
    )
    
    # Start A2A server on port 8000
    await green_agent.start_server(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    asyncio.run(main())
```

#### 2.2 Verify Server is Running
```bash
# Check agent card
curl http://localhost:8000/.well-known/agent-card.json

# Check health
curl http://localhost:8000/health
```

### Phase 3: Create Purple Agent Client

#### 3.1 Wrap Existing SWE-bench Solver
```python
# File: purple_agent_wrapper.py
from src.a2a.client import A2AClient
from src.purple_agent.controller import PurpleAgentController

class SWEBenchSolver:
    """Wrapper for existing SWE-bench solver"""
    
    def __init__(self, solver_type="swe-agent"):
        self.client = A2AClient(
            agent_id="purple_agent_001",
            base_url="http://localhost:8000"
        )
        self.controller = PurpleAgentController()
        
    async def solve_task(self, task_id=None):
        # 1. Request task from Green Agent
        task = await self.client.request_task(
            task_type="swe-bench-evaluation",
            instance_id=task_id  # Optional specific instance
        )
        
        # 2. Handle dialogue phase
        if task.requires_clarification:
            await self.handle_dialogue(task)
        
        # 3. Submit reproduction script
        if task.requires_reproduction:
            script = await self.generate_reproduction(task)
            await self.client.submit_reproduction(task.id, script)
        
        # 4. Generate and submit patch
        patch = await self.generate_patch(task)
        result = await self.client.submit_patch(task.id, patch)
        
        # 5. Handle code review feedback
        if result.requires_revision:
            await self.handle_review_feedback(result)
        
        return result
```

### Phase 4: Configure Docker Environments

#### 4.1 Pull SWE-bench Docker Images
```bash
# Pull official SWE-bench images
docker pull swebench/django:latest
docker pull swebench/scikit-learn:latest
docker pull swebench/flask:latest

# Or build custom images
docker build -t swebench/base -f docker/Dockerfile.base .
```

#### 4.2 Configure Environment Pool
```yaml
# docker-compose.swebench.yml
version: '3.8'

services:
  environment-pool:
    image: swebench/base
    deploy:
      replicas: 5  # Warm pool size
    volumes:
      - ./repos:/workspace/repos
      - ./cache:/workspace/cache
    networks:
      - swebench-net
    
  green-agent:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DOCKER_HOST=unix:///var/run/docker.sock
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - swebench-net

networks:
  swebench-net:
    driver: bridge
```

### Phase 5: Run Evaluation

#### 5.1 Simple Test Run
```python
# File: run_simple_evaluation.py
import asyncio
from purple_agent_wrapper import SWEBenchSolver

async def main():
    solver = SWEBenchSolver()
    
    # Test with a single known instance
    result = await solver.solve_task(task_id="django__django-11099")
    
    print(f"Result: {result.status}")
    print(f"Score: {result.comprehensive_score}")
    print(f"Grade: {result.grade}")

asyncio.run(main())
```

#### 5.2 Full Benchmark Run
```python
# File: run_full_benchmark.py
import asyncio
from tqdm import tqdm

async def run_benchmark():
    solver = SWEBenchSolver()
    
    # Get all instances
    instances = await solver.client.get_available_instances()
    
    results = []
    for instance in tqdm(instances, desc="Evaluating"):
        try:
            result = await solver.solve_task(task_id=instance["id"])
            results.append(result)
        except Exception as e:
            print(f"Failed on {instance['id']}: {e}")
    
    # Calculate aggregate metrics
    success_rate = sum(1 for r in results if r.passed) / len(results)
    avg_score = sum(r.comprehensive_score for r in results) / len(results)
    
    print(f"\n=== BENCHMARK RESULTS ===")
    print(f"Success Rate: {success_rate:.2%}")
    print(f"Average Score: {avg_score:.2%}")
    print(f"Total Evaluated: {len(results)}")

asyncio.run(run_benchmark())
```

### Phase 6: Enable Advanced Features

#### 6.1 Enable All Features
```python
# Update green_agent configuration
green_agent = GreenAgentService(
    swebench_integration=swebench,
    enable_dialogue=True,           # ✅ Interactive dialogue
    enable_reproduction_gate=True,   # ✅ Issue2Test
    enable_code_review=True,         # ✅ Senior Dev review
    enable_mutations=True,           # ✅ Retro-Holdout
    ambiguity_level="medium",        # Inject ambiguity
    review_strictness="medium",       # Review strictness
    mutation_rate=0.3                # 30% mutation rate
)
```

#### 6.2 Monitor with Dashboard
```bash
# Start monitoring dashboard
python demo_server.py

# Access at http://localhost:8080
# View real-time metrics, tasks, and scores
```

### Phase 7: Production Deployment

#### 7.1 Deploy to Kubernetes
```bash
# Apply Kubernetes manifests
kubectl apply -f k8s/

# Scale as needed
kubectl scale deployment green-agent --replicas=10
```

#### 7.2 Enable Metrics Collection
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'swebench-a2a'
    static_configs:
      - targets: ['green-agent:9090']
    metrics_path: '/metrics'
```

## Execution Commands

### Quick Start (Minimal)
```bash
# 1. Install dependencies
./venv_new/bin/pip install -r requirements.txt

# 2. Start Green Agent
python start_green_agent.py

# 3. Run simple evaluation
python run_simple_evaluation.py
```

### Full Benchmark
```bash
# 1. Start infrastructure
docker-compose -f docker-compose.swebench.yml up -d

# 2. Start Green Agent with all features
python start_green_agent.py --full-features

# 3. Run benchmark
python run_full_benchmark.py --dataset lite --output results.json
```

## Expected Output

### Per-Task Results
```json
{
  "task_id": "django__django-11099",
  "instance_id": "django__django-11099",
  "status": "completed",
  "scores": {
    "correctness": 0.85,
    "process": 0.90,
    "efficiency": 0.75,
    "collaboration": 0.88,
    "understanding": 0.92,
    "adaptation": 0.80
  },
  "comprehensive_score": 0.86,
  "grade": "B+",
  "dialogue_turns": 3,
  "reproduction_verified": true,
  "review_iterations": 2,
  "execution_time": 145.3
}
```

### Aggregate Metrics
```
=== BENCHMARK RESULTS ===
Dataset: SWE-bench Lite (300 instances)
Success Rate: 42.3%
Average Score: 78.5%
Grade Distribution:
  A+: 12%
  A:  18%
  B+: 25%
  B:  20%
  C:  15%
  F:  10%

Process Metrics:
  Avg Dialogue Quality: 82%
  Reproduction Success: 89%
  Feedback Incorporation: 76%
  Mutation Resistance: 71%
```

## Troubleshooting

### Common Issues

1. **Docker not running**
   ```bash
   # Start Docker Desktop
   open -a Docker
   ```

2. **Port already in use**
   ```bash
   # Kill existing process
   lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9
   ```

3. **Out of memory**
   ```bash
   # Increase Docker memory limit
   # Docker Desktop → Preferences → Resources → Memory: 8GB+
   ```

4. **Dataset download fails**
   ```bash
   # Use local cache
   export HF_DATASETS_OFFLINE=1
   ```

## Next Steps

1. **Optimize Performance**
   - Enable GPU acceleration
   - Implement result caching
   - Parallelize evaluations

2. **Enhance Metrics**
   - Add custom scoring rubrics
   - Implement trajectory replay
   - Create visualization dashboards

3. **Scale Up**
   - Move to SWE-bench Full (2,294 instances)
   - Deploy to cloud infrastructure
   - Enable distributed evaluation

This plan provides a complete pathway from setup to production deployment of the A2A SWE-bench evaluation system!