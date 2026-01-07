"""Trajectory capture system for logging agent actions"""

import asyncio
import time
import json
import logging
from typing import Dict, Any, Optional, List, AsyncIterator
from datetime import datetime
from contextlib import asynccontextmanager

from ..database import get_session, Trajectory, Task
from .streaming import EventStreamer

logger = logging.getLogger(__name__)


class ActionLogger:
    """Logs individual actions to the trajectory"""
    
    def __init__(self, task_id: str, streamer: Optional[EventStreamer] = None):
        self.task_id = task_id
        self.sequence_number = 0
        self.streamer = streamer
        self.start_time = time.time()
        self.action_stack: List[Dict[str, Any]] = []
    
    async def log_action(
        self,
        action_type: str,
        action_target: Optional[str] = None,
        action_input: Optional[Any] = None,
        action_output: Optional[Any] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        tokens_used: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a single action to the trajectory.
        
        Args:
            action_type: Type of action (search, read, write, execute, think)
            action_target: Target of the action (file path, command, etc.)
            action_input: Input to the action
            action_output: Output from the action
            success: Whether the action succeeded
            error_message: Error message if failed
            tokens_used: Number of tokens used
            metadata: Additional metadata
            
        Returns:
            Trajectory entry ID
        """
        start_time = time.time()
        
        # Convert inputs/outputs to strings for storage
        if action_input is not None and not isinstance(action_input, str):
            action_input = json.dumps(action_input, default=str)
        if action_output is not None and not isinstance(action_output, str):
            action_output = json.dumps(action_output, default=str)
        
        # Create trajectory entry
        trajectory_entry = {
            "task_id": self.task_id,
            "sequence_number": self.sequence_number,
            "action_type": action_type,
            "action_target": action_target,
            "action_input": action_input[:10000] if action_input else None,  # Limit size
            "action_output": action_output[:10000] if action_output else None,  # Limit size
            "success": success,
            "error_message": error_message,
            "tokens_used": tokens_used,
            "timestamp": datetime.utcnow(),
            "metadata": metadata or {}
        }
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        trajectory_entry["duration_ms"] = duration_ms
        
        # Save to database
        trajectory_id = await self._save_to_database(trajectory_entry)
        
        # Stream event if streamer is available
        if self.streamer:
            await self.streamer.emit_event(
                event_type="trajectory.action",
                data=trajectory_entry
            )
        
        # Track in action stack for analysis
        self.action_stack.append({
            "id": trajectory_id,
            "type": action_type,
            "target": action_target,
            "timestamp": trajectory_entry["timestamp"]
        })
        
        self.sequence_number += 1
        
        logger.debug(f"Logged action {action_type} for task {self.task_id}")
        
        return trajectory_id
    
    async def _save_to_database(self, entry: Dict[str, Any]) -> str:
        """Save trajectory entry to database"""
        try:
            with get_session() as session:
                trajectory = Trajectory(**entry)
                session.add(trajectory)
                session.commit()
                return trajectory.id
        except Exception as e:
            logger.error(f"Failed to save trajectory entry: {e}")
            # Return a fallback ID even if save fails
            return f"fallback_{self.task_id}_{self.sequence_number}"
    
    @asynccontextmanager
    async def action_context(
        self,
        action_type: str,
        action_target: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Context manager for logging actions with automatic timing.
        
        Usage:
            async with logger.action_context("search", "views.py") as ctx:
                result = await search_file("views.py")
                ctx.set_output(result)
        """
        start_time = time.time()
        context = ActionContext()
        
        try:
            yield context
            
            # Log successful action
            await self.log_action(
                action_type=action_type,
                action_target=action_target,
                action_input=context.input,
                action_output=context.output,
                success=True,
                tokens_used=context.tokens_used,
                metadata={
                    **(metadata or {}),
                    "duration_ms": int((time.time() - start_time) * 1000)
                }
            )
            
        except Exception as e:
            # Log failed action
            await self.log_action(
                action_type=action_type,
                action_target=action_target,
                action_input=context.input,
                action_output=None,
                success=False,
                error_message=str(e),
                metadata={
                    **(metadata or {}),
                    "duration_ms": int((time.time() - start_time) * 1000)
                }
            )
            raise
    
    def get_action_summary(self) -> Dict[str, Any]:
        """Get summary of logged actions"""
        action_counts = {}
        for action in self.action_stack:
            action_type = action["type"]
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
        
        return {
            "total_actions": len(self.action_stack),
            "action_counts": action_counts,
            "duration_seconds": time.time() - self.start_time,
            "last_action": self.action_stack[-1] if self.action_stack else None
        }


class ActionContext:
    """Context for action logging"""
    
    def __init__(self):
        self.input = None
        self.output = None
        self.tokens_used = None
    
    def set_input(self, value: Any):
        """Set action input"""
        self.input = value
    
    def set_output(self, value: Any):
        """Set action output"""
        self.output = value
    
    def set_tokens(self, count: int):
        """Set tokens used"""
        self.tokens_used = count


class TrajectoryCapture:
    """Main trajectory capture system"""
    
    def __init__(self, enable_streaming: bool = True):
        self.enable_streaming = enable_streaming
        self.streamer = EventStreamer() if enable_streaming else None
        self.active_loggers: Dict[str, ActionLogger] = {}
    
    def create_logger(self, task_id: str) -> ActionLogger:
        """
        Create a new action logger for a task.
        
        Args:
            task_id: Task ID to log actions for
            
        Returns:
            ActionLogger instance
        """
        logger_instance = ActionLogger(task_id, self.streamer)
        self.active_loggers[task_id] = logger_instance
        
        logger.info(f"Created action logger for task {task_id}")
        
        return logger_instance
    
    def get_logger(self, task_id: str) -> Optional[ActionLogger]:
        """Get existing logger for a task"""
        return self.active_loggers.get(task_id)
    
    def remove_logger(self, task_id: str):
        """Remove logger when task is complete"""
        if task_id in self.active_loggers:
            del self.active_loggers[task_id]
            logger.info(f"Removed action logger for task {task_id}")
    
    async def get_task_trajectory(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get complete trajectory for a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            List of trajectory entries
        """
        try:
            with get_session() as session:
                trajectories = session.query(Trajectory).filter_by(
                    task_id=task_id
                ).order_by(Trajectory.sequence_number).all()
                
                return [
                    {
                        "id": t.id,
                        "sequence_number": t.sequence_number,
                        "action_type": t.action_type,
                        "action_target": t.action_target,
                        "action_input": t.action_input,
                        "action_output": t.action_output,
                        "success": t.success,
                        "error_message": t.error_message,
                        "duration_ms": t.duration_ms,
                        "tokens_used": t.tokens_used,
                        "timestamp": t.timestamp.isoformat() if t.timestamp else None,
                        "metadata": t.metadata
                    }
                    for t in trajectories
                ]
        except Exception as e:
            logger.error(f"Failed to get task trajectory: {e}")
            return []
    
    async def replay_trajectory(
        self,
        task_id: str,
        speed: float = 1.0
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Replay a task trajectory for analysis.
        
        Args:
            task_id: Task ID
            speed: Playback speed (1.0 = real-time)
            
        Yields:
            Trajectory entries with timing
        """
        trajectory = await self.get_task_trajectory(task_id)
        
        if not trajectory:
            logger.warning(f"No trajectory found for task {task_id}")
            return
        
        last_timestamp = None
        
        for entry in trajectory:
            # Calculate delay
            if last_timestamp and speed > 0:
                current_timestamp = datetime.fromisoformat(entry["timestamp"])
                time_diff = (current_timestamp - last_timestamp).total_seconds()
                await asyncio.sleep(time_diff / speed)
            
            yield entry
            
            if entry["timestamp"]:
                last_timestamp = datetime.fromisoformat(entry["timestamp"])
    
    async def export_trajectory(
        self,
        task_id: str,
        format: str = "json"
    ) -> str:
        """
        Export trajectory in various formats.
        
        Args:
            task_id: Task ID
            format: Export format (json, csv, markdown)
            
        Returns:
            Exported trajectory string
        """
        trajectory = await self.get_task_trajectory(task_id)
        
        if format == "json":
            return json.dumps(trajectory, indent=2, default=str)
        
        elif format == "csv":
            import csv
            import io
            
            output = io.StringIO()
            if trajectory:
                writer = csv.DictWriter(
                    output,
                    fieldnames=trajectory[0].keys()
                )
                writer.writeheader()
                writer.writerows(trajectory)
            
            return output.getvalue()
        
        elif format == "markdown":
            lines = ["# Task Trajectory\n"]
            
            for entry in trajectory:
                lines.append(f"\n## Action {entry['sequence_number']}")
                lines.append(f"- **Type**: {entry['action_type']}")
                lines.append(f"- **Target**: {entry['action_target'] or 'N/A'}")
                lines.append(f"- **Success**: {entry['success']}")
                lines.append(f"- **Duration**: {entry['duration_ms']}ms")
                
                if entry['error_message']:
                    lines.append(f"- **Error**: {entry['error_message']}")
                
                if entry['action_input']:
                    lines.append(f"\n### Input\n```\n{entry['action_input'][:500]}\n```")
                
                if entry['action_output']:
                    lines.append(f"\n### Output\n```\n{entry['action_output'][:500]}\n```")
            
            return "\n".join(lines)
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get capture system statistics"""
        return {
            "active_loggers": len(self.active_loggers),
            "streaming_enabled": self.enable_streaming,
            "streamer_stats": self.streamer.get_stats() if self.streamer else None
        }