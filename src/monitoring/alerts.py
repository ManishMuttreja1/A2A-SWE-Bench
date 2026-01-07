"""Alert definitions and notification system"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import aiohttp

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertChannel(str, Enum):
    """Alert notification channels"""
    SLACK = "slack"
    EMAIL = "email"
    WEBHOOK = "webhook"
    PAGERDUTY = "pagerduty"
    PROMETHEUS_ALERTMANAGER = "prometheus_alertmanager"


@dataclass
class AlertRule:
    """Alert rule definition"""
    name: str
    description: str
    condition: str  # Prometheus query
    threshold: float
    severity: AlertSeverity
    duration: int  # seconds
    channels: List[AlertChannel]
    labels: Dict[str, str]
    annotations: Dict[str, str]


@dataclass
class Alert:
    """Active alert instance"""
    rule_name: str
    severity: AlertSeverity
    message: str
    value: float
    started_at: datetime
    labels: Dict[str, str]
    annotations: Dict[str, str]
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['started_at'] = self.started_at.isoformat()
        data['duration_seconds'] = (datetime.now() - self.started_at).total_seconds()
        return data


class AlertManager:
    """
    Alert management system with multi-channel notifications.
    Integrates with Prometheus Alertmanager and other services.
    """
    
    def __init__(self):
        # Alert rules
        self.rules: Dict[str, AlertRule] = {}
        
        # Active alerts
        self.active_alerts: Dict[str, Alert] = {}
        
        # Alert history
        self.alert_history: List[Dict[str, Any]] = []
        
        # Notification channels
        self.channels: Dict[AlertChannel, Dict[str, Any]] = {}
        
        # Silence rules
        self.silenced_alerts: Dict[str, datetime] = {}
        
        # Initialize default rules
        self._init_default_rules()
    
    def _init_default_rules(self):
        """Initialize default alert rules"""
        
        # System alerts
        self.add_rule(AlertRule(
            name="high_cpu_usage",
            description="CPU usage is above 90%",
            condition="system_cpu_usage_percent > 90",
            threshold=90,
            severity=AlertSeverity.CRITICAL,
            duration=300,  # 5 minutes
            channels=[AlertChannel.SLACK, AlertChannel.PAGERDUTY],
            labels={"component": "system", "resource": "cpu"},
            annotations={"summary": "High CPU usage detected"}
        ))
        
        self.add_rule(AlertRule(
            name="high_memory_usage",
            description="Memory usage is above 90%",
            condition="system_memory_usage_percent > 90",
            threshold=90,
            severity=AlertSeverity.CRITICAL,
            duration=300,
            channels=[AlertChannel.SLACK, AlertChannel.PAGERDUTY],
            labels={"component": "system", "resource": "memory"},
            annotations={"summary": "High memory usage detected"}
        ))
        
        self.add_rule(AlertRule(
            name="disk_space_low",
            description="Disk space is below 10%",
            condition="(system_disk_usage_bytes{type='free'} / system_disk_usage_bytes{type='total'}) < 0.1",
            threshold=0.1,
            severity=AlertSeverity.WARNING,
            duration=600,
            channels=[AlertChannel.SLACK],
            labels={"component": "system", "resource": "disk"},
            annotations={"summary": "Low disk space"}
        ))
        
        # Service alerts
        self.add_rule(AlertRule(
            name="high_error_rate",
            description="Error rate is above 5%",
            condition="rate(errors_total[5m]) > 0.05",
            threshold=0.05,
            severity=AlertSeverity.WARNING,
            duration=300,
            channels=[AlertChannel.SLACK],
            labels={"component": "application"},
            annotations={"summary": "High error rate detected"}
        ))
        
        self.add_rule(AlertRule(
            name="task_processing_slow",
            description="Task processing time above 5 minutes",
            condition="task_duration_seconds > 300",
            threshold=300,
            severity=AlertSeverity.WARNING,
            duration=600,
            channels=[AlertChannel.SLACK],
            labels={"component": "tasks"},
            annotations={"summary": "Slow task processing"}
        ))
        
        self.add_rule(AlertRule(
            name="database_connection_failed",
            description="Database connection failures",
            condition="database_connections_active == 0",
            threshold=0,
            severity=AlertSeverity.CRITICAL,
            duration=60,
            channels=[AlertChannel.SLACK, AlertChannel.PAGERDUTY],
            labels={"component": "database"},
            annotations={"summary": "Database connection lost"}
        ))
        
        self.add_rule(AlertRule(
            name="synthesis_failures_high",
            description="High synthesis failure rate",
            condition="rate(synthesis_attempts_total{result='failure'}[5m]) > 0.3",
            threshold=0.3,
            severity=AlertSeverity.WARNING,
            duration=300,
            channels=[AlertChannel.SLACK],
            labels={"component": "synthesis"},
            annotations={"summary": "High synthesis failure rate"}
        ))
        
        self.add_rule(AlertRule(
            name="memorization_spike",
            description="Spike in memorization detections",
            condition="rate(memorization_detected_total[5m]) > 10",
            threshold=10,
            severity=AlertSeverity.INFO,
            duration=300,
            channels=[AlertChannel.SLACK],
            labels={"component": "evaluation"},
            annotations={"summary": "Memorization spike detected"}
        ))
        
        self.add_rule(AlertRule(
            name="agent_disconnections",
            description="Multiple agent disconnections",
            condition="rate(agent_errors_total{error_type='disconnection'}[5m]) > 5",
            threshold=5,
            severity=AlertSeverity.WARNING,
            duration=300,
            channels=[AlertChannel.SLACK],
            labels={"component": "agents"},
            annotations={"summary": "Multiple agent disconnections"}
        ))
        
        self.add_rule(AlertRule(
            name="cache_hit_rate_low",
            description="Cache hit rate below 50%",
            condition="(cache_operations_total{result='hit'} / cache_operations_total) < 0.5",
            threshold=0.5,
            severity=AlertSeverity.INFO,
            duration=1800,
            channels=[AlertChannel.SLACK],
            labels={"component": "cache"},
            annotations={"summary": "Low cache hit rate"}
        ))
    
    def add_rule(self, rule: AlertRule):
        """Add alert rule"""
        self.rules[rule.name] = rule
    
    def configure_channel(
        self,
        channel: AlertChannel,
        config: Dict[str, Any]
    ):
        """Configure notification channel"""
        self.channels[channel] = config
    
    async def check_rule(
        self,
        rule: AlertRule,
        current_value: float
    ) -> Optional[Alert]:
        """Check if alert rule is triggered"""
        # Simple threshold check (in production, would query Prometheus)
        if current_value > rule.threshold:
            # Check if already active
            if rule.name not in self.active_alerts:
                # Create new alert
                alert = Alert(
                    rule_name=rule.name,
                    severity=rule.severity,
                    message=rule.description,
                    value=current_value,
                    started_at=datetime.now(),
                    labels=rule.labels,
                    annotations=rule.annotations
                )
                
                # Check if silenced
                if not self.is_silenced(rule.name):
                    await self.trigger_alert(alert, rule)
                
                return alert
        else:
            # Clear alert if exists
            if rule.name in self.active_alerts:
                await self.clear_alert(rule.name)
        
        return None
    
    async def trigger_alert(self, alert: Alert, rule: AlertRule):
        """Trigger alert and send notifications"""
        logger.warning(f"Alert triggered: {alert.rule_name} - {alert.message}")
        
        # Store active alert
        self.active_alerts[alert.rule_name] = alert
        
        # Add to history
        self.alert_history.append({
            **alert.to_dict(),
            'triggered_at': datetime.now().isoformat()
        })
        
        # Send notifications
        for channel in rule.channels:
            await self.send_notification(channel, alert)
    
    async def clear_alert(self, rule_name: str):
        """Clear active alert"""
        if rule_name in self.active_alerts:
            alert = self.active_alerts[rule_name]
            logger.info(f"Alert cleared: {rule_name}")
            
            # Remove from active
            del self.active_alerts[rule_name]
            
            # Add resolution to history
            self.alert_history.append({
                'rule_name': rule_name,
                'event': 'resolved',
                'resolved_at': datetime.now().isoformat(),
                'duration_seconds': (datetime.now() - alert.started_at).total_seconds()
            })
            
            # Send resolution notification
            await self.send_resolution_notification(alert)
    
    async def send_notification(
        self,
        channel: AlertChannel,
        alert: Alert
    ):
        """Send alert notification to channel"""
        config = self.channels.get(channel, {})
        
        try:
            if channel == AlertChannel.SLACK:
                await self._send_slack_notification(alert, config)
            elif channel == AlertChannel.WEBHOOK:
                await self._send_webhook_notification(alert, config)
            elif channel == AlertChannel.PAGERDUTY:
                await self._send_pagerduty_notification(alert, config)
            elif channel == AlertChannel.PROMETHEUS_ALERTMANAGER:
                await self._send_alertmanager_notification(alert, config)
            else:
                logger.warning(f"Unsupported channel: {channel}")
        
        except Exception as e:
            logger.error(f"Failed to send {channel} notification: {e}")
    
    async def _send_slack_notification(
        self,
        alert: Alert,
        config: Dict[str, Any]
    ):
        """Send Slack notification"""
        webhook_url = config.get('webhook_url')
        if not webhook_url:
            return
        
        # Format message
        color = {
            AlertSeverity.CRITICAL: "danger",
            AlertSeverity.WARNING: "warning",
            AlertSeverity.INFO: "good"
        }.get(alert.severity, "warning")
        
        payload = {
            "attachments": [{
                "color": color,
                "title": f":warning: {alert.rule_name}",
                "text": alert.message,
                "fields": [
                    {"title": "Severity", "value": alert.severity, "short": True},
                    {"title": "Value", "value": str(alert.value), "short": True},
                    {"title": "Started", "value": alert.started_at.isoformat(), "short": True}
                ],
                "footer": "A2A Alert System",
                "ts": int(alert.started_at.timestamp())
            }]
        }
        
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json=payload)
    
    async def _send_webhook_notification(
        self,
        alert: Alert,
        config: Dict[str, Any]
    ):
        """Send generic webhook notification"""
        url = config.get('url')
        if not url:
            return
        
        payload = alert.to_dict()
        
        async with aiohttp.ClientSession() as session:
            headers = config.get('headers', {})
            await session.post(url, json=payload, headers=headers)
    
    async def _send_pagerduty_notification(
        self,
        alert: Alert,
        config: Dict[str, Any]
    ):
        """Send PagerDuty notification"""
        integration_key = config.get('integration_key')
        if not integration_key:
            return
        
        payload = {
            "routing_key": integration_key,
            "event_action": "trigger",
            "payload": {
                "summary": alert.message,
                "severity": alert.severity,
                "source": "a2a-monitoring",
                "component": alert.labels.get('component', 'unknown'),
                "custom_details": {
                    "value": alert.value,
                    "started_at": alert.started_at.isoformat(),
                    **alert.annotations
                }
            }
        }
        
        async with aiohttp.ClientSession() as session:
            await session.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload
            )
    
    async def _send_alertmanager_notification(
        self,
        alert: Alert,
        config: Dict[str, Any]
    ):
        """Send to Prometheus Alertmanager"""
        url = config.get('url', 'http://localhost:9093')
        
        payload = [{
            "labels": {
                **alert.labels,
                "alertname": alert.rule_name,
                "severity": alert.severity
            },
            "annotations": alert.annotations,
            "startsAt": alert.started_at.isoformat(),
            "generatorURL": config.get('generator_url', 'http://localhost:8080')
        }]
        
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"{url}/api/v1/alerts",
                json=payload
            )
    
    async def send_resolution_notification(self, alert: Alert):
        """Send alert resolution notification"""
        # Send to configured channels
        for channel in [AlertChannel.SLACK, AlertChannel.PAGERDUTY]:
            if channel in self.channels:
                if channel == AlertChannel.SLACK:
                    await self._send_slack_resolution(alert)
                elif channel == AlertChannel.PAGERDUTY:
                    await self._send_pagerduty_resolution(alert)
    
    async def _send_slack_resolution(self, alert: Alert):
        """Send Slack resolution notification"""
        config = self.channels.get(AlertChannel.SLACK, {})
        webhook_url = config.get('webhook_url')
        if not webhook_url:
            return
        
        payload = {
            "attachments": [{
                "color": "good",
                "title": f":white_check_mark: {alert.rule_name} - Resolved",
                "text": f"Alert has been resolved",
                "fields": [
                    {"title": "Duration", "value": f"{(datetime.now() - alert.started_at).total_seconds():.0f}s", "short": True}
                ],
                "footer": "A2A Alert System",
                "ts": int(datetime.now().timestamp())
            }]
        }
        
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json=payload)
    
    async def _send_pagerduty_resolution(self, alert: Alert):
        """Send PagerDuty resolution"""
        config = self.channels.get(AlertChannel.PAGERDUTY, {})
        integration_key = config.get('integration_key')
        if not integration_key:
            return
        
        payload = {
            "routing_key": integration_key,
            "event_action": "resolve",
            "dedup_key": alert.rule_name
        }
        
        async with aiohttp.ClientSession() as session:
            await session.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload
            )
    
    def silence_alert(self, rule_name: str, duration_hours: int = 1):
        """Silence alert for specified duration"""
        self.silenced_alerts[rule_name] = datetime.now() + timedelta(hours=duration_hours)
        logger.info(f"Alert {rule_name} silenced for {duration_hours} hours")
    
    def is_silenced(self, rule_name: str) -> bool:
        """Check if alert is silenced"""
        if rule_name in self.silenced_alerts:
            if datetime.now() < self.silenced_alerts[rule_name]:
                return True
            else:
                # Silence expired
                del self.silenced_alerts[rule_name]
        return False
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        return [alert.to_dict() for alert in self.active_alerts.values()]
    
    def get_alert_history(
        self,
        hours: int = 24,
        severity: Optional[AlertSeverity] = None
    ) -> List[Dict[str, Any]]:
        """Get alert history"""
        cutoff = datetime.now() - timedelta(hours=hours)
        
        filtered = []
        for entry in self.alert_history:
            # Parse timestamp
            if 'triggered_at' in entry:
                timestamp = datetime.fromisoformat(entry['triggered_at'])
            elif 'resolved_at' in entry:
                timestamp = datetime.fromisoformat(entry['resolved_at'])
            else:
                continue
            
            if timestamp >= cutoff:
                if severity is None or entry.get('severity') == severity:
                    filtered.append(entry)
        
        return filtered


# Global alert manager instance
alert_manager = AlertManager()