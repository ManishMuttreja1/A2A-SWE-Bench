"""Prometheus metrics for A2A SWE-bench service"""

import time
import psutil
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from contextlib import contextmanager
from functools import wraps
from datetime import datetime

from prometheus_client import (
    Counter, Histogram, Gauge, Summary, Info,
    CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST,
    push_to_gateway
)
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Comprehensive metrics collection for A2A service.
    Tracks all critical system and business metrics.
    """
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        
        # System Metrics
        self.cpu_usage = Gauge(
            'system_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )
        
        self.memory_usage = Gauge(
            'system_memory_usage_bytes',
            'Memory usage in bytes',
            ['type'],  # type: used, available, percent
            registry=self.registry
        )
        
        self.disk_usage = Gauge(
            'system_disk_usage_bytes',
            'Disk usage in bytes',
            ['path', 'type'],  # type: used, free, total
            registry=self.registry
        )
        
        # A2A Protocol Metrics
        self.protocol_requests = Counter(
            'a2a_protocol_requests_total',
            'Total A2A protocol requests',
            ['method', 'status'],
            registry=self.registry
        )
        
        self.protocol_latency = Histogram(
            'a2a_protocol_request_duration_seconds',
            'A2A protocol request latency',
            ['method'],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self.registry
        )
        
        # Task Metrics
        self.tasks_created = Counter(
            'tasks_created_total',
            'Total tasks created',
            ['type', 'difficulty'],
            registry=self.registry
        )
        
        self.tasks_completed = Counter(
            'tasks_completed_total',
            'Total tasks completed',
            ['status', 'agent_type'],
            registry=self.registry
        )
        
        self.task_duration = Histogram(
            'task_duration_seconds',
            'Task completion duration',
            ['type'],
            buckets=(10, 30, 60, 120, 300, 600, 1200, 1800, 3600),
            registry=self.registry
        )
        
        self.active_tasks = Gauge(
            'active_tasks_count',
            'Number of active tasks',
            ['status'],
            registry=self.registry
        )
        
        # Agent Metrics
        self.agent_registrations = Counter(
            'agent_registrations_total',
            'Total agent registrations',
            ['type', 'version'],
            registry=self.registry
        )
        
        self.active_agents = Gauge(
            'active_agents_count',
            'Number of active agents',
            ['type', 'status'],
            registry=self.registry
        )
        
        self.agent_errors = Counter(
            'agent_errors_total',
            'Total agent errors',
            ['agent_id', 'error_type'],
            registry=self.registry
        )
        
        # Trajectory Metrics
        self.trajectory_actions = Counter(
            'trajectory_actions_total',
            'Total trajectory actions recorded',
            ['action_type', 'result'],
            registry=self.registry
        )
        
        self.trajectory_size = Histogram(
            'trajectory_size_bytes',
            'Size of trajectory data',
            buckets=(1024, 10240, 102400, 1048576, 10485760),
            registry=self.registry
        )
        
        # Synthesis Engine Metrics
        self.synthesis_attempts = Counter(
            'synthesis_attempts_total',
            'Total environment synthesis attempts',
            ['result', 'reason'],
            registry=self.registry
        )
        
        self.synthesis_duration = Histogram(
            'synthesis_duration_seconds',
            'Environment synthesis duration',
            buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
            registry=self.registry
        )
        
        self.synthesis_cache_hits = Counter(
            'synthesis_cache_hits_total',
            'Synthesis cache hits',
            ['cache_type'],
            registry=self.registry
        )
        
        # Mutation Metrics
        self.mutations_applied = Counter(
            'mutations_applied_total',
            'Total code mutations applied',
            ['mutation_type', 'success'],
            registry=self.registry
        )
        
        self.mutation_impact = Histogram(
            'mutation_impact_score',
            'Impact score of mutations',
            buckets=(0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0),
            registry=self.registry
        )
        
        # Scoring Metrics
        self.scores_calculated = Counter(
            'scores_calculated_total',
            'Total scores calculated',
            ['dimension'],
            registry=self.registry
        )
        
        self.score_distribution = Histogram(
            'score_distribution',
            'Distribution of scores',
            ['dimension'],
            buckets=(0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100),
            registry=self.registry
        )
        
        # Database Metrics
        self.db_queries = Counter(
            'database_queries_total',
            'Total database queries',
            ['operation', 'table'],
            registry=self.registry
        )
        
        self.db_query_duration = Histogram(
            'database_query_duration_seconds',
            'Database query duration',
            ['operation'],
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
            registry=self.registry
        )
        
        self.db_connections = Gauge(
            'database_connections_active',
            'Active database connections',
            ['pool'],
            registry=self.registry
        )
        
        # Cache Metrics
        self.cache_operations = Counter(
            'cache_operations_total',
            'Total cache operations',
            ['operation', 'cache_name', 'result'],
            registry=self.registry
        )
        
        self.cache_size = Gauge(
            'cache_size_bytes',
            'Cache size in bytes',
            ['cache_name'],
            registry=self.registry
        )
        
        # Error Metrics
        self.errors = Counter(
            'errors_total',
            'Total errors',
            ['component', 'error_type', 'severity'],
            registry=self.registry
        )
        
        self.error_rate = Gauge(
            'error_rate_per_minute',
            'Error rate per minute',
            ['component'],
            registry=self.registry
        )
        
        # Performance Metrics
        self.response_time = Summary(
            'response_time_seconds',
            'Response time summary',
            ['endpoint', 'method'],
            registry=self.registry
        )
        
        self.throughput = Gauge(
            'throughput_requests_per_second',
            'Request throughput',
            ['endpoint'],
            registry=self.registry
        )
        
        # Business Metrics
        self.memorization_detected = Counter(
            'memorization_detected_total',
            'Total memorization detections',
            ['detection_method', 'confidence'],
            registry=self.registry
        )
        
        self.leaderboard_updates = Counter(
            'leaderboard_updates_total',
            'Total leaderboard updates',
            ['update_type'],
            registry=self.registry
        )
        
        # Custom collectors
        self.custom_collectors = []
        
        # Error tracking
        self._error_window = {}
        self._last_error_calculation = time.time()
    
    def track_request(self, method: str, status: str, duration: float):
        """Track A2A protocol request"""
        self.protocol_requests.labels(method=method, status=status).inc()
        self.protocol_latency.labels(method=method).observe(duration)
    
    @contextmanager
    def track_duration(self, metric: Histogram, **labels):
        """Context manager to track operation duration"""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            metric.labels(**labels).observe(duration)
    
    def track_task_lifecycle(self, task_id: str, event: str, **metadata):
        """Track task lifecycle events"""
        if event == 'created':
            self.tasks_created.labels(
                type=metadata.get('type', 'unknown'),
                difficulty=metadata.get('difficulty', 'medium')
            ).inc()
            self.active_tasks.labels(status='pending').inc()
        
        elif event == 'started':
            self.active_tasks.labels(status='pending').dec()
            self.active_tasks.labels(status='running').inc()
        
        elif event == 'completed':
            self.tasks_completed.labels(
                status=metadata.get('status', 'success'),
                agent_type=metadata.get('agent_type', 'unknown')
            ).inc()
            self.active_tasks.labels(status='running').dec()
            
            if 'duration' in metadata:
                self.task_duration.labels(
                    type=metadata.get('type', 'unknown')
                ).observe(metadata['duration'])
    
    def track_agent_activity(self, agent_id: str, event: str, **metadata):
        """Track agent activity"""
        if event == 'registered':
            self.agent_registrations.labels(
                type=metadata.get('type', 'unknown'),
                version=metadata.get('version', 'unknown')
            ).inc()
            self.active_agents.labels(
                type=metadata.get('type', 'unknown'),
                status='active'
            ).inc()
        
        elif event == 'error':
            self.agent_errors.labels(
                agent_id=agent_id,
                error_type=metadata.get('error_type', 'unknown')
            ).inc()
            self.track_error(
                component='agent',
                error_type=metadata.get('error_type', 'unknown'),
                severity=metadata.get('severity', 'medium')
            )
        
        elif event == 'disconnected':
            self.active_agents.labels(
                type=metadata.get('type', 'unknown'),
                status='active'
            ).dec()
    
    def track_synthesis(self, event: str, **metadata):
        """Track synthesis engine events"""
        if event == 'attempt':
            self.synthesis_attempts.labels(
                result=metadata.get('result', 'unknown'),
                reason=metadata.get('reason', 'unknown')
            ).inc()
        
        elif event == 'cache_hit':
            self.synthesis_cache_hits.labels(
                cache_type=metadata.get('cache_type', 'memory')
            ).inc()
        
        elif event == 'duration':
            self.synthesis_duration.observe(metadata.get('duration', 0))
    
    def track_mutation(self, mutation_type: str, success: bool, impact: float = 0.0):
        """Track code mutation events"""
        self.mutations_applied.labels(
            mutation_type=mutation_type,
            success=str(success)
        ).inc()
        
        if impact > 0:
            self.mutation_impact.observe(impact)
    
    def track_score(self, dimension: str, score: float):
        """Track scoring events"""
        self.scores_calculated.labels(dimension=dimension).inc()
        self.score_distribution.labels(dimension=dimension).observe(score)
    
    def track_database(self, operation: str, table: str, duration: float):
        """Track database operations"""
        self.db_queries.labels(operation=operation, table=table).inc()
        self.db_query_duration.labels(operation=operation).observe(duration)
    
    def track_cache(self, cache_name: str, operation: str, hit: bool):
        """Track cache operations"""
        result = 'hit' if hit else 'miss'
        self.cache_operations.labels(
            operation=operation,
            cache_name=cache_name,
            result=result
        ).inc()
    
    def track_error(self, component: str, error_type: str, severity: str = 'medium'):
        """Track errors with rate calculation"""
        self.errors.labels(
            component=component,
            error_type=error_type,
            severity=severity
        ).inc()
        
        # Track for rate calculation
        key = f"{component}:{error_type}"
        current_time = time.time()
        
        if key not in self._error_window:
            self._error_window[key] = []
        
        self._error_window[key].append(current_time)
        
        # Clean old entries (older than 1 minute)
        cutoff = current_time - 60
        self._error_window[key] = [
            t for t in self._error_window[key] if t > cutoff
        ]
        
        # Update rate metric
        rate = len(self._error_window[key])
        self.error_rate.labels(component=component).set(rate)
    
    def track_memorization(self, method: str, confidence: float):
        """Track memorization detection"""
        confidence_bucket = 'high' if confidence > 0.8 else 'medium' if confidence > 0.5 else 'low'
        self.memorization_detected.labels(
            detection_method=method,
            confidence=confidence_bucket
        ).inc()
    
    def update_system_metrics(self):
        """Update system resource metrics"""
        # CPU metrics
        self.cpu_usage.set(psutil.cpu_percent(interval=1))
        
        # Memory metrics
        memory = psutil.virtual_memory()
        self.memory_usage.labels(type='used').set(memory.used)
        self.memory_usage.labels(type='available').set(memory.available)
        self.memory_usage.labels(type='percent').set(memory.percent)
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        self.disk_usage.labels(path='/', type='used').set(disk.used)
        self.disk_usage.labels(path='/', type='free').set(disk.free)
        self.disk_usage.labels(path='/', type='total').set(disk.total)
    
    async def start_system_metrics_collector(self, interval: int = 30):
        """Start background system metrics collection"""
        while True:
            try:
                self.update_system_metrics()
            except Exception as e:
                logger.error(f"Failed to collect system metrics: {e}")
            
            await asyncio.sleep(interval)
    
    def export_metrics(self) -> bytes:
        """Export metrics in Prometheus format"""
        return generate_latest(self.registry)
    
    def push_metrics(
        self,
        gateway: str,
        job: str,
        grouping_key: Optional[Dict[str, str]] = None
    ):
        """Push metrics to Prometheus Pushgateway"""
        try:
            push_to_gateway(
                gateway,
                job=job,
                registry=self.registry,
                grouping_key=grouping_key or {}
            )
        except Exception as e:
            logger.error(f"Failed to push metrics: {e}")
    
    def add_custom_collector(self, collector: Callable):
        """Add custom metric collector"""
        self.custom_collectors.append(collector)
        self.registry.register(collector)


def metrics_decorator(
    collector: MetricsCollector,
    component: str,
    operation: str
):
    """Decorator to automatically track metrics for functions"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            success = False
            error_type = None
            
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            
            except Exception as e:
                error_type = type(e).__name__
                collector.track_error(
                    component=component,
                    error_type=error_type,
                    severity='high'
                )
                raise
            
            finally:
                duration = time.time() - start
                collector.response_time.labels(
                    endpoint=operation,
                    method=component
                ).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            success = False
            error_type = None
            
            try:
                result = func(*args, **kwargs)
                success = True
                return result
            
            except Exception as e:
                error_type = type(e).__name__
                collector.track_error(
                    component=component,
                    error_type=error_type,
                    severity='high'
                )
                raise
            
            finally:
                duration = time.time() - start
                collector.response_time.labels(
                    endpoint=operation,
                    method=component
                ).observe(duration)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Global metrics instance
metrics = MetricsCollector()