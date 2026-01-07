"""Grafana dashboard configurations for A2A monitoring"""

import json
from typing import Dict, Any, List


class DashboardBuilder:
    """Build Grafana dashboards programmatically"""
    
    @staticmethod
    def create_overview_dashboard() -> Dict[str, Any]:
        """Create main overview dashboard"""
        return {
            "dashboard": {
                "title": "A2A SWE-bench Overview",
                "tags": ["a2a", "overview"],
                "timezone": "browser",
                "panels": [
                    # System metrics row
                    {
                        "id": 1,
                        "type": "graph",
                        "title": "CPU Usage",
                        "gridPos": {"h": 8, "w": 8, "x": 0, "y": 0},
                        "targets": [{
                            "expr": "system_cpu_usage_percent",
                            "legendFormat": "CPU %"
                        }]
                    },
                    {
                        "id": 2,
                        "type": "graph",
                        "title": "Memory Usage",
                        "gridPos": {"h": 8, "w": 8, "x": 8, "y": 0},
                        "targets": [{
                            "expr": "system_memory_usage_bytes{type='percent'}",
                            "legendFormat": "Memory %"
                        }]
                    },
                    {
                        "id": 3,
                        "type": "stat",
                        "title": "Disk Usage",
                        "gridPos": {"h": 8, "w": 8, "x": 16, "y": 0},
                        "targets": [{
                            "expr": "(system_disk_usage_bytes{type='used'} / system_disk_usage_bytes{type='total'}) * 100",
                            "legendFormat": "Disk %"
                        }]
                    },
                    
                    # Task metrics row
                    {
                        "id": 4,
                        "type": "stat",
                        "title": "Active Tasks",
                        "gridPos": {"h": 4, "w": 6, "x": 0, "y": 8},
                        "targets": [{
                            "expr": "sum(active_tasks_count)"
                        }]
                    },
                    {
                        "id": 5,
                        "type": "graph",
                        "title": "Task Completion Rate",
                        "gridPos": {"h": 8, "w": 12, "x": 6, "y": 8},
                        "targets": [{
                            "expr": "rate(tasks_completed_total[5m])",
                            "legendFormat": "{{status}}"
                        }]
                    },
                    {
                        "id": 6,
                        "type": "heatmap",
                        "title": "Task Duration Heatmap",
                        "gridPos": {"h": 8, "w": 6, "x": 18, "y": 8},
                        "targets": [{
                            "expr": "task_duration_seconds",
                            "format": "heatmap"
                        }]
                    },
                    
                    # Agent metrics row
                    {
                        "id": 7,
                        "type": "stat",
                        "title": "Active Agents",
                        "gridPos": {"h": 4, "w": 6, "x": 0, "y": 16},
                        "targets": [{
                            "expr": "sum(active_agents_count{status='active'})"
                        }]
                    },
                    {
                        "id": 8,
                        "type": "graph",
                        "title": "Agent Error Rate",
                        "gridPos": {"h": 8, "w": 18, "x": 6, "y": 16},
                        "targets": [{
                            "expr": "rate(agent_errors_total[5m])",
                            "legendFormat": "{{error_type}}"
                        }]
                    },
                    
                    # Performance metrics row
                    {
                        "id": 9,
                        "type": "graph",
                        "title": "Request Latency",
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 24},
                        "targets": [{
                            "expr": "histogram_quantile(0.95, rate(a2a_protocol_request_duration_seconds_bucket[5m]))",
                            "legendFormat": "p95 {{method}}"
                        }]
                    },
                    {
                        "id": 10,
                        "type": "graph",
                        "title": "Throughput",
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 24},
                        "targets": [{
                            "expr": "rate(a2a_protocol_requests_total[1m])",
                            "legendFormat": "{{method}}"
                        }]
                    }
                ],
                "refresh": "10s",
                "time": {"from": "now-1h", "to": "now"}
            }
        }
    
    @staticmethod
    def create_synthesis_dashboard() -> Dict[str, Any]:
        """Create synthesis engine dashboard"""
        return {
            "dashboard": {
                "title": "Synthesis Engine Monitoring",
                "tags": ["a2a", "synthesis"],
                "panels": [
                    {
                        "id": 1,
                        "type": "graph",
                        "title": "Synthesis Success Rate",
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                        "targets": [{
                            "expr": "rate(synthesis_attempts_total{result='success'}[5m]) / rate(synthesis_attempts_total[5m])",
                            "legendFormat": "Success Rate"
                        }]
                    },
                    {
                        "id": 2,
                        "type": "heatmap",
                        "title": "Synthesis Duration",
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
                        "targets": [{
                            "expr": "synthesis_duration_seconds",
                            "format": "heatmap"
                        }]
                    },
                    {
                        "id": 3,
                        "type": "stat",
                        "title": "Cache Hit Rate",
                        "gridPos": {"h": 4, "w": 6, "x": 0, "y": 8},
                        "targets": [{
                            "expr": "sum(rate(synthesis_cache_hits_total[5m])) / sum(rate(synthesis_attempts_total[5m]))",
                            "legendFormat": "Hit Rate"
                        }]
                    },
                    {
                        "id": 4,
                        "type": "graph",
                        "title": "Mutation Impact",
                        "gridPos": {"h": 8, "w": 18, "x": 6, "y": 8},
                        "targets": [{
                            "expr": "histogram_quantile(0.5, mutation_impact_score_bucket)",
                            "legendFormat": "Median Impact"
                        }]
                    }
                ]
            }
        }
    
    @staticmethod
    def create_scoring_dashboard() -> Dict[str, Any]:
        """Create scoring and evaluation dashboard"""
        return {
            "dashboard": {
                "title": "Scoring & Evaluation",
                "tags": ["a2a", "scoring"],
                "panels": [
                    {
                        "id": 1,
                        "type": "graph",
                        "title": "Score Distribution",
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
                        "targets": [{
                            "expr": "histogram_quantile(0.5, score_distribution_bucket)",
                            "legendFormat": "{{dimension}}"
                        }]
                    },
                    {
                        "id": 2,
                        "type": "stat",
                        "title": "Memorization Detections",
                        "gridPos": {"h": 4, "w": 6, "x": 12, "y": 0},
                        "targets": [{
                            "expr": "sum(rate(memorization_detected_total[1h]))",
                            "legendFormat": "Detections/hour"
                        }]
                    },
                    {
                        "id": 3,
                        "type": "table",
                        "title": "Top Agents by Score",
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
                        "targets": [{
                            "expr": "topk(10, avg by(agent_id) (score_distribution))",
                            "format": "table"
                        }]
                    }
                ]
            }
        }
    
    @staticmethod
    def export_prometheus_rules() -> str:
        """Export Prometheus alert rules"""
        rules = {
            "groups": [{
                "name": "a2a_alerts",
                "interval": "30s",
                "rules": [
                    {
                        "alert": "HighCPUUsage",
                        "expr": "system_cpu_usage_percent > 90",
                        "for": "5m",
                        "labels": {
                            "severity": "critical",
                            "component": "system"
                        },
                        "annotations": {
                            "summary": "High CPU usage detected",
                            "description": "CPU usage is {{ $value }}%"
                        }
                    },
                    {
                        "alert": "HighMemoryUsage",
                        "expr": "system_memory_usage_bytes{type='percent'} > 90",
                        "for": "5m",
                        "labels": {
                            "severity": "critical",
                            "component": "system"
                        },
                        "annotations": {
                            "summary": "High memory usage detected",
                            "description": "Memory usage is {{ $value }}%"
                        }
                    },
                    {
                        "alert": "HighErrorRate",
                        "expr": "rate(errors_total[5m]) > 0.05",
                        "for": "5m",
                        "labels": {
                            "severity": "warning",
                            "component": "application"
                        },
                        "annotations": {
                            "summary": "High error rate",
                            "description": "Error rate is {{ $value }} per second"
                        }
                    },
                    {
                        "alert": "DatabaseConnectionLost",
                        "expr": "database_connections_active == 0",
                        "for": "1m",
                        "labels": {
                            "severity": "critical",
                            "component": "database"
                        },
                        "annotations": {
                            "summary": "Database connection lost",
                            "description": "No active database connections"
                        }
                    },
                    {
                        "alert": "SynthesisFailureHigh",
                        "expr": "rate(synthesis_attempts_total{result='failure'}[5m]) > 0.3",
                        "for": "5m",
                        "labels": {
                            "severity": "warning",
                            "component": "synthesis"
                        },
                        "annotations": {
                            "summary": "High synthesis failure rate",
                            "description": "Synthesis failure rate is {{ $value }}"
                        }
                    },
                    {
                        "alert": "AgentDisconnections",
                        "expr": "rate(agent_errors_total{error_type='disconnection'}[5m]) > 5",
                        "for": "5m",
                        "labels": {
                            "severity": "warning",
                            "component": "agents"
                        },
                        "annotations": {
                            "summary": "Multiple agent disconnections",
                            "description": "{{ $value }} disconnections per minute"
                        }
                    }
                ]
            }]
        }
        
        return json.dumps(rules, indent=2)
    
    @staticmethod
    def export_grafana_provisioning() -> Dict[str, Any]:
        """Export Grafana provisioning configuration"""
        return {
            "apiVersion": 1,
            "datasources": [{
                "name": "Prometheus",
                "type": "prometheus",
                "access": "proxy",
                "url": "http://prometheus:9090",
                "isDefault": True,
                "editable": False
            }],
            "providers": [{
                "name": "A2A Dashboards",
                "orgId": 1,
                "folder": "A2A",
                "type": "file",
                "disableDeletion": False,
                "updateIntervalSeconds": 10,
                "allowUiUpdates": False,
                "options": {
                    "path": "/var/lib/grafana/dashboards"
                }
            }]
        }


# Dashboard builder instance
dashboard_builder = DashboardBuilder()