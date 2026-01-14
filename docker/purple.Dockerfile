FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy purple agent code
COPY src/purple_agent /app/src/purple_agent
COPY src/a2a /app/src/a2a
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV PYTHONPATH=/app

# Expose port for A2A protocol
EXPOSE 8001

# Start purple agent
CMD ["python", "-m", "src.purple_agent.service"]