# SWE-bench A2A Deployment Guide

## Overview
This guide provides instructions for deploying and running the enhanced SWE-bench A2A system with support for running 50+ tests in parallel.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.10+ 
- 16GB+ RAM recommended
- 100GB+ free disk space
- API keys for LLM providers (Anthropic or OpenAI)

## Quick Start

### 1. Set Environment Variables

Create a `.env` file with your API keys:

```bash
# LLM Provider Settings
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENAI_API_KEY=sk-your-key-here
LLM_PROVIDER=anthropic  # or "openai"

# Database Settings
DATABASE_URL=postgresql://swebench:swebench_secure_pass_2024@localhost:5432/swebench
REDIS_URL=redis://localhost:6379
```

### 2. Start Infrastructure with PostgreSQL

```bash
# Start all services (PostgreSQL, Redis, Agents)
docker compose -f docker-compose-with-postgres.yml up -d

# Wait for services to be healthy
docker compose -f docker-compose-with-postgres.yml ps

# Check logs
docker compose -f docker-compose-with-postgres.yml logs -f
```

### 3. Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv_new
source venv_new/bin/activate  # On Windows: venv_new\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Run Tests

#### Small Test Batch (10 tests)
```bash
# Run original benchmark script
./venv_new/bin/python run_benchmark.py
```

#### Parallel Test Execution (50+ tests)
```bash
# Run 50 tests with 5 parallel workers
./venv_new/bin/python run_parallel_benchmark.py --count 50 --workers 5

# Run with balanced strategy (mix of difficulties)
./venv_new/bin/python run_parallel_benchmark.py --count 50 --strategy balanced

# Run easy tests first
./venv_new/bin/python run_parallel_benchmark.py --count 50 --strategy easy_first

# Resume from checkpoint
./venv_new/bin/python run_parallel_benchmark.py --resume checkpoints/checkpoint_20260113_150000.pkl
```

## Architecture Components

### 1. Purple Agent (Port 8001)
- **Enhanced LLM Integration**: Real Anthropic/OpenAI API support
- **Location**: `src/purple_agent/wrapper.py`, `src/purple_agent/llm_solver.py`
- **Features**:
  - Automatic retry with exponential backoff
  - Token usage tracking
  - Cost estimation
  - Multiple LLM provider support

### 2. Green Agent (Port 8002) 
- **Async Verification Engine**: Non-blocking Docker operations
- **Location**: `src/green_agent/async_orchestrator.py`
- **Features**:
  - Timeout protection for all operations
  - Parallel container management
  - Resource limits (2GB RAM, 50% CPU per container)

### 3. PostgreSQL Database
- **Connection Pooling**: 5-20 connections
- **Async Support**: Using asyncpg
- **Tables**:
  - `tasks`: Task tracking
  - `evaluations`: Test results
  - `metrics`: Performance metrics
  - `agent_sessions`: Agent activity tracking

### 4. Redis Cache
- **Purpose**: Task queue and result caching
- **Port**: 6379

## Performance Optimizations

### Parallel Execution
- **Default Workers**: 5 concurrent tests
- **Adjustable**: `--workers` parameter (max recommended: 10)
- **Resource Usage**: ~2GB RAM per worker

### Checkpoint/Resume
- **Auto-save**: Every 10 completed tests
- **Location**: `checkpoints/` directory
- **Resume Command**: `--resume checkpoint_file.pkl`

### Test Selection Strategies
1. **Balanced**: Mix of easy/medium/hard tests
2. **Easy First**: Start with simpler tests
3. **By Repository**: Focus on specific repos (e.g., Django)
4. **Random**: Random selection

## Monitoring

### Check Agent Health
```bash
# Purple Agent
curl http://localhost:8001/health

# Green Agent  
curl http://localhost:8002/health
```

### View Logs
```bash
# All services
docker compose -f docker-compose-with-postgres.yml logs

# Specific service
docker compose -f docker-compose-with-postgres.yml logs green-agent -f
```

### Database Queries
```bash
# Connect to PostgreSQL
docker exec -it swebench-postgres psql -U swebench -d swebench

# Check task stats
SELECT status, COUNT(*) FROM tasks GROUP BY status;

# Check evaluation results
SELECT passed, COUNT(*) FROM evaluations GROUP BY passed;
```

## Troubleshooting

### Issue: Tests Timing Out
**Solution**: Increase timeout or reduce parallel workers
```bash
./venv_new/bin/python run_parallel_benchmark.py --timeout 900 --workers 3
```

### Issue: Database Connection Errors
**Solution**: Ensure PostgreSQL is running
```bash
docker compose -f docker-compose-with-postgres.yml restart postgres
```

### Issue: High Memory Usage
**Solution**: Reduce parallel workers and container limits
- Edit `docker-compose-with-postgres.yml`
- Reduce `mem_limit` for agents
- Restart services

### Issue: LLM API Errors
**Solution**: Check API keys and rate limits
```bash
# Verify API keys are set
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY

# Check agent logs for API errors
docker logs swebench-purple-agent
```

## Results Analysis

### Generated Reports Location
- `test_results/parallel_report_*.json`: Detailed test results
- `test_results/swebench_report_*.json`: Standard benchmark results

### Report Contents
- Pass/fail rates by repository
- Average execution times
- Detailed error messages
- Token usage and costs (if using LLM)

### Example Report Analysis
```python
import json
from pathlib import Path

# Load latest report
reports = sorted(Path("test_results").glob("parallel_report_*.json"))
with open(reports[-1]) as f:
    report = json.load(f)

# Print summary
print(f"Pass Rate: {report['summary']['pass_rate']:.1f}%")
print(f"Average Time: {report['summary']['average_time']:.1f}s")

# By repository
for repo, stats in report['by_repository'].items():
    print(f"{repo}: {stats['passed']}/{stats['total']}")
```

## Scaling to 500+ Tests

### Recommended Configuration
```bash
# Use checkpoint/resume for large batches
./venv_new/bin/python run_parallel_benchmark.py \
  --count 100 \
  --workers 8 \
  --strategy balanced

# Continue with next batch
./venv_new/bin/python run_parallel_benchmark.py \
  --count 100 \
  --workers 8 \
  --resume checkpoints/latest.pkl
```

### Resource Requirements for 500 Tests
- **RAM**: 32GB minimum
- **CPU**: 8+ cores
- **Disk**: 200GB+ for Docker images and test repos
- **Time**: ~12-24 hours depending on workers

## Clean Up

```bash
# Stop all services
docker compose -f docker-compose-with-postgres.yml down

# Remove volumes (warning: deletes data)
docker compose -f docker-compose-with-postgres.yml down -v

# Clean Docker system
docker system prune -a
```

## Support

For issues or questions:
1. Check agent logs: `docker logs <container-name>`
2. Review checkpoint files in `checkpoints/`
3. Examine database: `docker exec -it swebench-postgres psql -U swebench`
4. Check API rate limits and quotas