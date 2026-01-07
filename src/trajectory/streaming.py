"""Event streaming for real-time trajectory capture"""

import asyncio
import json
import time
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from collections import deque
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class EventStreamer:
    """Stream events for real-time monitoring and analysis"""
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        buffer_size: int = 1000,
        enable_redis: bool = True
    ):
        self.redis_url = redis_url
        self.buffer_size = buffer_size
        self.enable_redis = enable_redis
        
        # Local buffer for events
        self.event_buffer = deque(maxlen=buffer_size)
        
        # Subscribers for different event types
        self.subscribers: Dict[str, List[Callable]] = {}
        
        # Redis connection
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub: Optional[redis.client.PubSub] = None
        
        # Statistics
        self.stats = {
            "events_emitted": 0,
            "events_buffered": 0,
            "subscribers_count": 0,
            "start_time": time.time()
        }
        
        # Initialize Redis if enabled
        if enable_redis:
            asyncio.create_task(self._init_redis())
    
    async def _init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = await redis.from_url(self.redis_url)
            self.pubsub = self.redis_client.pubsub()
            logger.info("Redis connection established for event streaming")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Using local buffer only.")
            self.enable_redis = False
    
    async def emit_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        task_id: Optional[str] = None
    ):
        """
        Emit an event to all subscribers.
        
        Args:
            event_type: Type of event (e.g., "trajectory.action", "task.status")
            data: Event data
            task_id: Optional task ID for routing
        """
        event = {
            "type": event_type,
            "data": data,
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat(),
            "sequence": self.stats["events_emitted"]
        }
        
        # Add to local buffer
        self.event_buffer.append(event)
        self.stats["events_buffered"] = len(self.event_buffer)
        
        # Publish to Redis if available
        if self.enable_redis and self.redis_client:
            try:
                channel = f"swebench:{event_type}"
                if task_id:
                    channel = f"{channel}:{task_id}"
                
                await self.redis_client.publish(
                    channel,
                    json.dumps(event, default=str)
                )
            except Exception as e:
                logger.error(f"Failed to publish event to Redis: {e}")
        
        # Call local subscribers
        if event_type in self.subscribers:
            for callback in self.subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Subscriber callback error: {e}")
        
        # Call wildcard subscribers
        if "*" in self.subscribers:
            for callback in self.subscribers["*"]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Wildcard subscriber callback error: {e}")
        
        self.stats["events_emitted"] += 1
    
    def subscribe(
        self,
        event_type: str,
        callback: Callable
    ):
        """
        Subscribe to events of a specific type.
        
        Args:
            event_type: Event type to subscribe to (use "*" for all)
            callback: Function to call when event is emitted
        """
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        
        self.subscribers[event_type].append(callback)
        self.stats["subscribers_count"] = sum(len(subs) for subs in self.subscribers.values())
        
        logger.debug(f"Added subscriber for {event_type}")
    
    def unsubscribe(
        self,
        event_type: str,
        callback: Callable
    ):
        """Unsubscribe from events"""
        if event_type in self.subscribers:
            if callback in self.subscribers[event_type]:
                self.subscribers[event_type].remove(callback)
                self.stats["subscribers_count"] = sum(len(subs) for subs in self.subscribers.values())
                logger.debug(f"Removed subscriber for {event_type}")
    
    async def subscribe_redis(
        self,
        pattern: str,
        callback: Callable
    ):
        """
        Subscribe to Redis pub/sub channel.
        
        Args:
            pattern: Channel pattern to subscribe to
            callback: Async function to handle messages
        """
        if not self.pubsub:
            logger.warning("Redis not available for subscription")
            return
        
        await self.pubsub.psubscribe(pattern)
        
        # Start listening in background
        asyncio.create_task(self._redis_listener(pattern, callback))
    
    async def _redis_listener(
        self,
        pattern: str,
        callback: Callable
    ):
        """Listen for Redis pub/sub messages"""
        try:
            async for message in self.pubsub.listen():
                if message["type"] in ["pmessage", "message"]:
                    try:
                        event = json.loads(message["data"])
                        await callback(event)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in Redis message: {message['data']}")
                    except Exception as e:
                        logger.error(f"Error processing Redis message: {e}")
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
    
    def get_recent_events(
        self,
        event_type: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get recent events from buffer.
        
        Args:
            event_type: Filter by event type
            task_id: Filter by task ID
            limit: Maximum number of events to return
            
        Returns:
            List of recent events
        """
        events = list(self.event_buffer)
        
        # Apply filters
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        
        if task_id:
            events = [e for e in events if e.get("task_id") == task_id]
        
        # Return most recent events
        return events[-limit:]
    
    async def stream_events(
        self,
        event_type: Optional[str] = None,
        task_id: Optional[str] = None
    ):
        """
        Async generator for streaming events.
        
        Args:
            event_type: Filter by event type
            task_id: Filter by task ID
            
        Yields:
            Events as they arrive
        """
        # Queue for this stream
        queue = asyncio.Queue()
        
        # Subscribe to events
        def handler(event):
            # Apply filters
            if event_type and event["type"] != event_type:
                return
            if task_id and event.get("task_id") != task_id:
                return
            
            # Add to queue
            asyncio.create_task(queue.put(event))
        
        # Subscribe
        self.subscribe(event_type or "*", handler)
        
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            # Unsubscribe
            self.unsubscribe(event_type or "*", handler)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics"""
        uptime = time.time() - self.stats["start_time"]
        
        return {
            **self.stats,
            "uptime_seconds": uptime,
            "events_per_second": self.stats["events_emitted"] / uptime if uptime > 0 else 0,
            "redis_connected": self.redis_client is not None,
            "buffer_usage": len(self.event_buffer) / self.buffer_size
        }
    
    async def close(self):
        """Close connections and clean up"""
        if self.pubsub:
            await self.pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Event streamer closed")


class EventAggregator:
    """Aggregate events for batch processing"""
    
    def __init__(
        self,
        batch_size: int = 100,
        batch_timeout: float = 5.0
    ):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.current_batch: List[Dict[str, Any]] = []
        self.batch_callbacks: List[Callable] = []
        self.last_flush = time.time()
        
        # Start flush timer
        asyncio.create_task(self._flush_timer())
    
    async def add_event(self, event: Dict[str, Any]):
        """Add event to current batch"""
        self.current_batch.append(event)
        
        # Flush if batch is full
        if len(self.current_batch) >= self.batch_size:
            await self.flush()
    
    async def flush(self):
        """Flush current batch"""
        if not self.current_batch:
            return
        
        batch = self.current_batch
        self.current_batch = []
        self.last_flush = time.time()
        
        # Process batch
        for callback in self.batch_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(batch)
                else:
                    callback(batch)
            except Exception as e:
                logger.error(f"Batch callback error: {e}")
    
    async def _flush_timer(self):
        """Periodic flush based on timeout"""
        while True:
            await asyncio.sleep(self.batch_timeout)
            
            # Flush if timeout exceeded
            if time.time() - self.last_flush >= self.batch_timeout:
                await self.flush()
    
    def on_batch(self, callback: Callable):
        """Register callback for batch processing"""
        self.batch_callbacks.append(callback)