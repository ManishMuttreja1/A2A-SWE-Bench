"""Health check system for A2A service components"""

import asyncio
import time
import logging
import psutil
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

import aiohttp
import asyncpg
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a component"""
    name: str
    status: HealthStatus
    message: str
    last_check: float
    response_time_ms: Optional[float] = None
    details: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data['last_check_iso'] = datetime.fromtimestamp(self.last_check).isoformat()
        return data


class HealthChecker:
    """
    Comprehensive health checking for all service components.
    Provides liveness and readiness probes for Kubernetes.
    """
    
    def __init__(
        self,
        check_interval: int = 30,
        timeout: int = 5,
        failure_threshold: int = 3
    ):
        self.check_interval = check_interval
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        
        # Component health status
        self.component_health: Dict[str, ComponentHealth] = {}
        
        # Failure tracking
        self.failure_counts: Dict[str, int] = {}
        
        # Custom health checks
        self.custom_checks: Dict[str, Callable] = {}
        
        # Service dependencies
        self.dependencies = {
            'database': None,
            'redis': None,
            'synthesis_engine': None,
            'a2a_server': None
        }
        
        # Background task
        self.health_check_task: Optional[asyncio.Task] = None
    
    def register_dependency(self, name: str, connection: Any):
        """Register a service dependency"""
        self.dependencies[name] = connection
    
    def register_custom_check(self, name: str, check_func: Callable):
        """Register custom health check function"""
        self.custom_checks[name] = check_func
    
    async def check_database(self) -> ComponentHealth:
        """Check database health"""
        name = "database"
        start = time.time()
        
        try:
            if not self.dependencies.get('database'):
                return ComponentHealth(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    message="Database connection not configured",
                    last_check=time.time()
                )
            
            # Execute simple query
            conn = self.dependencies['database']
            
            if hasattr(conn, 'execute'):  # SQLAlchemy
                result = await conn.execute("SELECT 1")
            else:  # asyncpg
                result = await conn.fetchval("SELECT 1")
            
            response_time = (time.time() - start) * 1000
            
            return ComponentHealth(
                name=name,
                status=HealthStatus.HEALTHY,
                message="Database responding normally",
                last_check=time.time(),
                response_time_ms=response_time,
                details={'query_result': result}
            )
        
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Database error: {str(e)}",
                last_check=time.time(),
                details={'error': str(e)}
            )
    
    async def check_redis(self) -> ComponentHealth:
        """Check Redis health"""
        name = "redis"
        start = time.time()
        
        try:
            if not self.dependencies.get('redis'):
                return ComponentHealth(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    message="Redis connection not configured",
                    last_check=time.time()
                )
            
            # Ping Redis
            conn = self.dependencies['redis']
            await conn.ping()
            
            # Check memory usage
            info = await conn.info('memory')
            used_memory = info.get('used_memory', 0)
            max_memory = info.get('maxmemory', 0)
            
            response_time = (time.time() - start) * 1000
            
            # Determine status based on memory usage
            status = HealthStatus.HEALTHY
            if max_memory > 0:
                usage_percent = (used_memory / max_memory) * 100
                if usage_percent > 90:
                    status = HealthStatus.UNHEALTHY
                elif usage_percent > 75:
                    status = HealthStatus.DEGRADED
            
            return ComponentHealth(
                name=name,
                status=status,
                message=f"Redis responding, memory usage: {used_memory / 1024 / 1024:.2f}MB",
                last_check=time.time(),
                response_time_ms=response_time,
                details={
                    'used_memory_mb': used_memory / 1024 / 1024,
                    'max_memory_mb': max_memory / 1024 / 1024 if max_memory > 0 else None
                }
            )
        
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Redis error: {str(e)}",
                last_check=time.time(),
                details={'error': str(e)}
            )
    
    async def check_synthesis_engine(self) -> ComponentHealth:
        """Check synthesis engine health"""
        name = "synthesis_engine"
        start = time.time()
        
        try:
            # Check if engine is available
            engine = self.dependencies.get('synthesis_engine')
            if not engine:
                return ComponentHealth(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    message="Synthesis engine not configured",
                    last_check=time.time()
                )
            
            # Check engine status
            if hasattr(engine, 'health_check'):
                result = await engine.health_check()
                status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
            else:
                status = HealthStatus.HEALTHY
            
            response_time = (time.time() - start) * 1000
            
            return ComponentHealth(
                name=name,
                status=status,
                message="Synthesis engine operational",
                last_check=time.time(),
                response_time_ms=response_time
            )
        
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Synthesis engine error: {str(e)}",
                last_check=time.time(),
                details={'error': str(e)}
            )
    
    async def check_a2a_server(self) -> ComponentHealth:
        """Check A2A server health"""
        name = "a2a_server"
        start = time.time()
        
        try:
            # Make HTTP request to server health endpoint
            server_url = self.dependencies.get('a2a_server', 'http://localhost:8080')
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{server_url}/health",
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response_time = (time.time() - start) * 1000
                    
                    if response.status == 200:
                        data = await response.json()
                        return ComponentHealth(
                            name=name,
                            status=HealthStatus.HEALTHY,
                            message="A2A server responding",
                            last_check=time.time(),
                            response_time_ms=response_time,
                            details=data
                        )
                    else:
                        return ComponentHealth(
                            name=name,
                            status=HealthStatus.UNHEALTHY,
                            message=f"A2A server returned status {response.status}",
                            last_check=time.time(),
                            response_time_ms=response_time
                        )
        
        except asyncio.TimeoutError:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="A2A server timeout",
                last_check=time.time()
            )
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"A2A server error: {str(e)}",
                last_check=time.time(),
                details={'error': str(e)}
            )
    
    async def check_system_resources(self) -> ComponentHealth:
        """Check system resource usage"""
        name = "system_resources"
        
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Determine overall status
            status = HealthStatus.HEALTHY
            issues = []
            
            if cpu_percent > 90:
                status = HealthStatus.UNHEALTHY
                issues.append(f"CPU usage critical: {cpu_percent}%")
            elif cpu_percent > 75:
                status = HealthStatus.DEGRADED
                issues.append(f"CPU usage high: {cpu_percent}%")
            
            if memory.percent > 90:
                status = HealthStatus.UNHEALTHY
                issues.append(f"Memory usage critical: {memory.percent}%")
            elif memory.percent > 75:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.DEGRADED
                issues.append(f"Memory usage high: {memory.percent}%")
            
            if disk.percent > 90:
                status = HealthStatus.UNHEALTHY
                issues.append(f"Disk usage critical: {disk.percent}%")
            elif disk.percent > 75:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.DEGRADED
                issues.append(f"Disk usage high: {disk.percent}%")
            
            message = "; ".join(issues) if issues else "System resources normal"
            
            return ComponentHealth(
                name=name,
                status=status,
                message=message,
                last_check=time.time(),
                details={
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_available_gb': memory.available / 1024 / 1024 / 1024,
                    'disk_percent': disk.percent,
                    'disk_free_gb': disk.free / 1024 / 1024 / 1024
                }
            )
        
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"Failed to check system resources: {str(e)}",
                last_check=time.time()
            )
    
    async def run_all_checks(self) -> Dict[str, ComponentHealth]:
        """Run all health checks"""
        checks = [
            self.check_database(),
            self.check_redis(),
            self.check_synthesis_engine(),
            self.check_a2a_server(),
            self.check_system_resources()
        ]
        
        # Add custom checks
        for name, check_func in self.custom_checks.items():
            if asyncio.iscoroutinefunction(check_func):
                checks.append(check_func())
            else:
                # Wrap sync function
                async def wrapper():
                    return check_func()
                checks.append(wrapper())
        
        # Run all checks concurrently
        results = await asyncio.gather(*checks, return_exceptions=True)
        
        # Process results
        health_status = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Handle check failure
                if i < 5:  # Standard checks
                    names = ['database', 'redis', 'synthesis_engine', 'a2a_server', 'system_resources']
                    name = names[i]
                else:  # Custom checks
                    name = list(self.custom_checks.keys())[i - 5]
                
                health_status[name] = ComponentHealth(
                    name=name,
                    status=HealthStatus.UNKNOWN,
                    message=f"Check failed: {str(result)}",
                    last_check=time.time()
                )
            else:
                health_status[result.name] = result
        
        # Update stored health status
        self.component_health = health_status
        
        # Update failure counts
        for name, health in health_status.items():
            if health.status in [HealthStatus.UNHEALTHY, HealthStatus.UNKNOWN]:
                self.failure_counts[name] = self.failure_counts.get(name, 0) + 1
            else:
                self.failure_counts[name] = 0
        
        return health_status
    
    async def start_background_checks(self):
        """Start background health checking"""
        async def check_loop():
            while True:
                try:
                    await self.run_all_checks()
                except Exception as e:
                    logger.error(f"Health check error: {e}")
                
                await asyncio.sleep(self.check_interval)
        
        self.health_check_task = asyncio.create_task(check_loop())
    
    def stop_background_checks(self):
        """Stop background health checking"""
        if self.health_check_task:
            self.health_check_task.cancel()
    
    def get_overall_status(self) -> HealthStatus:
        """Get overall system health status"""
        if not self.component_health:
            return HealthStatus.UNKNOWN
        
        statuses = [health.status for health in self.component_health.values()]
        
        if HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        elif HealthStatus.UNKNOWN in statuses:
            return HealthStatus.UNKNOWN
        else:
            return HealthStatus.HEALTHY
    
    def get_liveness_probe(self) -> Dict[str, Any]:
        """Get liveness probe response for Kubernetes"""
        overall = self.get_overall_status()
        
        # Liveness: system is running (even if degraded)
        is_alive = overall != HealthStatus.UNHEALTHY
        
        return {
            'status': 'ok' if is_alive else 'error',
            'timestamp': datetime.now().isoformat(),
            'overall_health': overall
        }
    
    def get_readiness_probe(self) -> Dict[str, Any]:
        """Get readiness probe response for Kubernetes"""
        overall = self.get_overall_status()
        
        # Readiness: system is fully operational
        is_ready = overall == HealthStatus.HEALTHY
        
        # Check critical components
        critical_components = ['database', 'a2a_server']
        critical_healthy = all(
            self.component_health.get(comp, ComponentHealth(
                name=comp,
                status=HealthStatus.UNKNOWN,
                message="Not checked",
                last_check=0
            )).status == HealthStatus.HEALTHY
            for comp in critical_components
        )
        
        return {
            'status': 'ok' if (is_ready and critical_healthy) else 'error',
            'timestamp': datetime.now().isoformat(),
            'overall_health': overall,
            'critical_components_healthy': critical_healthy,
            'components': {
                name: health.status
                for name, health in self.component_health.items()
            }
        }
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed health status"""
        return {
            'overall_status': self.get_overall_status(),
            'timestamp': datetime.now().isoformat(),
            'components': {
                name: health.to_dict()
                for name, health in self.component_health.items()
            },
            'failure_counts': self.failure_counts,
            'check_interval_seconds': self.check_interval,
            'failure_threshold': self.failure_threshold
        }


# Global health checker instance
health_checker = HealthChecker()