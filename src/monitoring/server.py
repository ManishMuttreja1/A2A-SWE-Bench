"""Monitoring server with metrics and health endpoints"""

import asyncio
import logging
from typing import Optional
from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST

from .metrics import metrics
from .health import health_checker
from .alerts import alert_manager

logger = logging.getLogger(__name__)


class MonitoringServer:
    """
    HTTP server for monitoring endpoints.
    Provides Prometheus metrics, health checks, and alert status.
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9090,
        metrics_path: str = "/metrics",
        health_path: str = "/health",
        ready_path: str = "/ready",
        live_path: str = "/healthz"
    ):
        self.host = host
        self.port = port
        self.metrics_path = metrics_path
        self.health_path = health_path
        self.ready_path = ready_path
        self.live_path = live_path
        
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_get(self.metrics_path, self.handle_metrics)
        self.app.router.add_get(self.health_path, self.handle_health)
        self.app.router.add_get(self.ready_path, self.handle_readiness)
        self.app.router.add_get(self.live_path, self.handle_liveness)
        self.app.router.add_get("/alerts", self.handle_alerts)
        self.app.router.add_get("/alerts/history", self.handle_alert_history)
        self.app.router.add_post("/alerts/silence", self.handle_silence_alert)
        self.app.router.add_get("/", self.handle_index)
    
    async def handle_metrics(self, request: web.Request) -> web.Response:
        """Handle Prometheus metrics endpoint"""
        try:
            # Update system metrics before export
            metrics.update_system_metrics()
            
            # Export metrics
            metrics_data = metrics.export_metrics()
            
            return web.Response(
                body=metrics_data,
                content_type=CONTENT_TYPE_LATEST
            )
        except Exception as e:
            logger.error(f"Error exporting metrics: {e}")
            return web.Response(
                text=f"Error: {str(e)}",
                status=500
            )
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """Handle detailed health check endpoint"""
        try:
            # Run health checks
            await health_checker.run_all_checks()
            
            # Get detailed status
            status = health_checker.get_detailed_status()
            
            # Determine HTTP status code
            overall = health_checker.get_overall_status()
            http_status = 200 if overall == "healthy" else 503
            
            return web.json_response(status, status=http_status)
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return web.json_response(
                {"error": str(e), "status": "unknown"},
                status=500
            )
    
    async def handle_readiness(self, request: web.Request) -> web.Response:
        """Handle Kubernetes readiness probe"""
        try:
            probe = health_checker.get_readiness_probe()
            status = 200 if probe['status'] == 'ok' else 503
            
            return web.json_response(probe, status=status)
        except Exception as e:
            return web.json_response(
                {"status": "error", "error": str(e)},
                status=500
            )
    
    async def handle_liveness(self, request: web.Request) -> web.Response:
        """Handle Kubernetes liveness probe"""
        try:
            probe = health_checker.get_liveness_probe()
            status = 200 if probe['status'] == 'ok' else 503
            
            return web.json_response(probe, status=status)
        except Exception as e:
            return web.json_response(
                {"status": "error", "error": str(e)},
                status=500
            )
    
    async def handle_alerts(self, request: web.Request) -> web.Response:
        """Handle active alerts endpoint"""
        try:
            alerts = alert_manager.get_active_alerts()
            
            return web.json_response({
                "active_count": len(alerts),
                "alerts": alerts
            })
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    async def handle_alert_history(self, request: web.Request) -> web.Response:
        """Handle alert history endpoint"""
        try:
            # Get query parameters
            hours = int(request.query.get('hours', 24))
            severity = request.query.get('severity')
            
            history = alert_manager.get_alert_history(
                hours=hours,
                severity=severity
            )
            
            return web.json_response({
                "hours": hours,
                "count": len(history),
                "history": history
            })
        except Exception as e:
            logger.error(f"Error getting alert history: {e}")
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    async def handle_silence_alert(self, request: web.Request) -> web.Response:
        """Handle alert silencing"""
        try:
            data = await request.json()
            rule_name = data.get('rule_name')
            duration_hours = data.get('duration_hours', 1)
            
            if not rule_name:
                return web.json_response(
                    {"error": "rule_name required"},
                    status=400
                )
            
            alert_manager.silence_alert(rule_name, duration_hours)
            
            return web.json_response({
                "status": "silenced",
                "rule_name": rule_name,
                "duration_hours": duration_hours
            })
        except Exception as e:
            logger.error(f"Error silencing alert: {e}")
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    async def handle_index(self, request: web.Request) -> web.Response:
        """Handle index page with links"""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>A2A Monitoring</title>
            <style>
                body { font-family: sans-serif; margin: 40px; }
                h1 { color: #333; }
                ul { line-height: 1.8; }
                a { color: #0066cc; text-decoration: none; }
                a:hover { text-decoration: underline; }
                .status { 
                    padding: 10px; 
                    margin: 20px 0; 
                    border-radius: 5px;
                    background: #f0f0f0;
                }
            </style>
        </head>
        <body>
            <h1>A2A SWE-bench Monitoring</h1>
            
            <div class="status">
                <h2>Endpoints</h2>
                <ul>
                    <li><a href="/metrics">Prometheus Metrics</a> - Metrics for scraping</li>
                    <li><a href="/health">Health Status</a> - Detailed component health</li>
                    <li><a href="/ready">Readiness Probe</a> - Kubernetes readiness</li>
                    <li><a href="/healthz">Liveness Probe</a> - Kubernetes liveness</li>
                    <li><a href="/alerts">Active Alerts</a> - Current alerts</li>
                    <li><a href="/alerts/history">Alert History</a> - Past alerts</li>
                </ul>
            </div>
            
            <div class="status">
                <h2>External Links</h2>
                <ul>
                    <li><a href="http://localhost:3000">Grafana Dashboards</a></li>
                    <li><a href="http://localhost:9090">Prometheus UI</a></li>
                    <li><a href="http://localhost:9093">Alertmanager UI</a></li>
                </ul>
            </div>
        </body>
        </html>
        """
        
        return web.Response(text=html, content_type='text/html')
    
    async def start(self):
        """Start monitoring server"""
        logger.info(f"Starting monitoring server on {self.host}:{self.port}")
        
        # Start background tasks
        asyncio.create_task(metrics.start_system_metrics_collector())
        await health_checker.start_background_checks()
        
        # Setup runner
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        # Start site
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        
        logger.info(f"Monitoring server started - http://{self.host}:{self.port}")
    
    async def stop(self):
        """Stop monitoring server"""
        logger.info("Stopping monitoring server")
        
        # Stop background tasks
        health_checker.stop_background_checks()
        
        # Cleanup runner
        if self.runner:
            await self.runner.cleanup()
        
        logger.info("Monitoring server stopped")


async def main():
    """Run monitoring server standalone"""
    logging.basicConfig(level=logging.INFO)
    
    server = MonitoringServer()
    await server.start()
    
    try:
        # Keep running
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())