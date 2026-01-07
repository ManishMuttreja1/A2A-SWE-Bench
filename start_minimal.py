#!/usr/bin/env python3
"""
Minimal startup script for A2A SWE-bench
Runs with core functionality only, no external dependencies required
"""

import asyncio
import json
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import core components with fallbacks
try:
    from src.a2a.protocol import A2AProtocol, Task, TaskStatus
    from src.a2a.server import A2AServer
    protocol_available = True
except ImportError as e:
    logger.warning(f"A2A Protocol not available: {e}")
    protocol_available = False

try:
    from src.synthesis.engine import SynthesisEngine
    synthesis_available = True
except ImportError as e:
    logger.warning(f"Synthesis Engine not available: {e}")
    synthesis_available = False

try:
    from src.monitoring.metrics import metrics
    from src.monitoring.health import health_checker
    monitoring_available = True
except ImportError as e:
    logger.warning(f"Monitoring not available: {e}")
    monitoring_available = False


class MinimalA2AServer:
    """Minimal A2A server that works without external dependencies"""
    
    def __init__(self):
        self.tasks = {}
        self.agents = {}
        self.start_time = datetime.now()
        
    async def start(self):
        """Start minimal HTTP server"""
        import http.server
        import socketserver
        import threading
        
        class Handler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    html = """
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>A2A SWE-bench - Minimal Mode</title>
                        <style>
                            body { font-family: Arial, sans-serif; margin: 40px; }
                            .status { color: green; }
                            .warning { color: orange; }
                            .endpoint { margin: 10px 0; padding: 10px; background: #f0f0f0; }
                        </style>
                    </head>
                    <body>
                        <h1>🚀 A2A SWE-bench Evaluation System</h1>
                        <p class="status">✅ Running in Minimal Mode</p>
                        
                        <h2>System Status</h2>
                        <div class="endpoint">
                            <strong>Uptime:</strong> Running since """ + str(self.server.parent.start_time) + """
                        </div>
                        
                        <h2>Available Endpoints</h2>
                        <div class="endpoint">
                            <strong>GET /health</strong> - Health check
                        </div>
                        <div class="endpoint">
                            <strong>GET /api/v1/status</strong> - System status
                        </div>
                        <div class="endpoint">
                            <strong>POST /api/v1/tasks</strong> - Create task
                        </div>
                        
                        <h2>Component Status</h2>
                        <div class="endpoint">
                            <strong>A2A Protocol:</strong> """ + ("✅ Available" if protocol_available else "❌ Not Available") + """
                        </div>
                        <div class="endpoint">
                            <strong>Synthesis Engine:</strong> """ + ("✅ Available" if synthesis_available else "❌ Not Available") + """
                        </div>
                        <div class="endpoint">
                            <strong>Monitoring:</strong> """ + ("✅ Available" if monitoring_available else "❌ Not Available") + """
                        </div>
                        
                        <h2>Configuration</h2>
                        <div class="endpoint">
                            <strong>Database:</strong> SQLite (local)
                        </div>
                        <div class="endpoint">
                            <strong>Port:</strong> 8080
                        </div>
                        
                        <p class="warning">⚠️ Running without external dependencies. Some features may be limited.</p>
                    </body>
                    </html>
                    """
                    self.wfile.write(html.encode())
                    
                elif self.path == '/health':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    health = {
                        "status": "healthy",
                        "timestamp": datetime.now().isoformat(),
                        "uptime_seconds": (datetime.now() - self.server.parent.start_time).total_seconds(),
                        "components": {
                            "protocol": protocol_available,
                            "synthesis": synthesis_available,
                            "monitoring": monitoring_available
                        }
                    }
                    self.wfile.write(json.dumps(health).encode())
                    
                elif self.path == '/api/v1/status':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    status = {
                        "version": "0.1.0",
                        "mode": "minimal",
                        "tasks_count": len(self.server.parent.tasks),
                        "agents_count": len(self.server.parent.agents),
                        "uptime_seconds": (datetime.now() - self.server.parent.start_time).total_seconds()
                    }
                    self.wfile.write(json.dumps(status).encode())
                else:
                    self.send_error(404)
                    
            def do_POST(self):
                if self.path == '/api/v1/tasks':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    
                    try:
                        data = json.loads(post_data)
                        task_id = f"task_{len(self.server.parent.tasks) + 1}"
                        task = {
                            "id": task_id,
                            "status": "created",
                            "created_at": datetime.now().isoformat(),
                            **data
                        }
                        self.server.parent.tasks[task_id] = task
                        
                        self.send_response(201)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps(task).encode())
                    except json.JSONDecodeError:
                        self.send_error(400, "Invalid JSON")
                else:
                    self.send_error(404)
                    
            def log_message(self, format, *args):
                # Suppress default logging
                pass
        
        # Create custom HTTP server
        Handler.server.parent = self
        
        PORT = 8080
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            logger.info(f"Minimal A2A Server running on port {PORT}")
            logger.info(f"Open http://localhost:{PORT} in your browser")
            
            # Run server in thread
            server_thread = threading.Thread(target=httpd.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            
            # Keep main thread alive
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                httpd.shutdown()


async def main():
    """Main entry point"""
    print("""
    ╔═══════════════════════════════════════════════════════╗
    ║       A2A SWE-bench Evaluation System                ║
    ║       Minimal Mode (No External Dependencies)        ║
    ╚═══════════════════════════════════════════════════════╝
    """)
    
    # Check available components
    print("🔍 Checking components...")
    print(f"  Protocol: {'✅' if protocol_available else '❌'}")
    print(f"  Synthesis: {'✅' if synthesis_available else '❌'}")
    print(f"  Monitoring: {'✅' if monitoring_available else '❌'}")
    print()
    
    # Start server
    server = MinimalA2AServer()
    
    print("🚀 Starting server...")
    print("📡 Server will be available at: http://localhost:8080")
    print("📊 Health check: http://localhost:8080/health")
    print("🛑 Press Ctrl+C to stop")
    print()
    
    try:
        await server.start()
    except KeyboardInterrupt:
        print("\n👋 Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Server error: {e}")
        print(f"\n❌ Error: {e}")
        print("Please check the logs for details")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)