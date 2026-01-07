FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/
COPY main.py .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -e .

# Create data directories
RUN mkdir -p /app/data /app/logs

# Expose ports
EXPOSE 8000 8001 8002 8003

# Default command
CMD ["python", "main.py", "--help"]