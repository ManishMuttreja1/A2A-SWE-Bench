#!/bin/bash

# A2A SWE-bench Startup Script

set -e

echo "🚀 Starting A2A SWE-bench Evaluation System"
echo "=========================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install --quiet --upgrade pip
pip install --quiet aiohttp aiosqlite aiofiles astor redis prometheus-client psutil python-dotenv structlog

# Create necessary directories
mkdir -p logs
mkdir -p data
mkdir -p tmp/synthesis_cache

# Check for .env file
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file from example...${NC}"
    cp .env.example .env
fi

# Initialize database
echo -e "${YELLOW}Initializing database...${NC}"
python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')
from src.database.connection import init_database
asyncio.run(init_database())
print('Database initialized')
" || echo -e "${YELLOW}Database initialization skipped${NC}"

# Start services
echo -e "${GREEN}Starting services...${NC}"

# Start monitoring server in background
echo -e "${YELLOW}Starting monitoring server on port 9090...${NC}"
python3 -c "
import asyncio
import sys
sys.path.insert(0, '.')
from src.monitoring.server import MonitoringServer
server = MonitoringServer()
asyncio.run(server.start())
" &
MONITORING_PID=$!

# Start main server
echo -e "${GREEN}Starting A2A server on port 8080...${NC}"
echo -e "${GREEN}=========================================${NC}"
echo -e "📊 Monitoring: http://localhost:9090"
echo -e "🔌 API Server: http://localhost:8080"
echo -e "📝 Health Check: http://localhost:9090/health"
echo -e "${GREEN}=========================================${NC}"

# Run main application
python3 main.py

# Cleanup on exit
trap "kill $MONITORING_PID 2>/dev/null" EXIT