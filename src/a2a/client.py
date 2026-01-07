"""A2A Client Implementation"""

import httpx
import asyncio
import json
from typing import Dict, Any, Optional, AsyncIterator, List
from .protocol import (
    A2AProtocol, Message, Task, TaskRequest, TaskUpdate,
    TaskResult, Artifact, AgentCard, MessageType
)
import logging

logger = logging.getLogger(__name__)


class A2AClient:
    """A2A Protocol Client implementation"""
    
    def __init__(self, agent_id: str, base_url: Optional[str] = None):
        self.agent_id = agent_id
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self._agent_card_cache: Dict[str, AgentCard] = {}
    
    async def discover_agent(self, url: str) -> Optional[AgentCard]:
        """Discover an agent via its well-known endpoint"""
        try:
            # Try to get agent card from well-known endpoint
            response = await self.client.get(f"{url}/.well-known/agent-card.json")
            
            if response.status_code == 200:
                data = response.json()
                agent_card = AgentCard(**data)
                self._agent_card_cache[url] = agent_card
                return agent_card
            
            logger.warning(f"Failed to discover agent at {url}: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error discovering agent at {url}: {e}")
            return None
    
    async def create_task(
        self,
        server_url: str,
        title: str,
        description: str,
        resources: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Create a task on a remote A2A server"""
        try:
            request = TaskRequest(
                title=title,
                description=description,
                resources=resources,
                constraints=constraints,
                metadata=metadata
            )
            
            response = await self.client.post(
                f"{server_url}/a2a/task",
                json=request.dict()
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("task_id")
            
            logger.error(f"Failed to create task: {response.status_code} - {response.text}")
            return None
            
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return None
    
    async def get_task_status(self, server_url: str, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a task"""
        try:
            response = await self.client.get(f"{server_url}/a2a/task/{task_id}")
            
            if response.status_code == 200:
                return response.json()
            
            logger.error(f"Failed to get task status: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            return None
    
    async def update_task(
        self,
        server_url: str,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        artifacts: Optional[List[Artifact]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update a task on the server"""
        try:
            update = TaskUpdate(
                task_id=task_id,
                status=status,
                progress=progress,
                message=message,
                artifacts=artifacts,
                metadata=metadata
            )
            
            response = await self.client.post(
                f"{server_url}/a2a/task/{task_id}/update",
                json=update.dict(exclude_none=True)
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error updating task: {e}")
            return False
    
    async def submit_artifact(
        self,
        server_url: str,
        task_id: str,
        artifact: Artifact
    ) -> Optional[str]:
        """Submit an artifact for a task"""
        try:
            response = await self.client.post(
                f"{server_url}/a2a/task/{task_id}/artifact",
                json=artifact.dict()
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("artifact_id")
            
            logger.error(f"Failed to submit artifact: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Error submitting artifact: {e}")
            return None
    
    async def stream_task_updates(
        self,
        server_url: str,
        task_id: str
    ) -> AsyncIterator[Message]:
        """Stream task updates via Server-Sent Events"""
        try:
            async with self.client.stream(
                "GET",
                f"{server_url}/a2a/task/{task_id}/stream"
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data.get("type") != "heartbeat":
                                yield Message(**data)
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse SSE data: {line}")
                        except Exception as e:
                            logger.error(f"Error processing SSE message: {e}")
                            
        except Exception as e:
            logger.error(f"Error streaming task updates: {e}")
    
    async def send_message(
        self,
        server_url: str,
        message: Message
    ) -> bool:
        """Send a message to another agent"""
        try:
            response = await self.client.post(
                f"{server_url}/a2a/message",
                json=message.dict()
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    async def wait_for_task_completion(
        self,
        server_url: str,
        task_id: str,
        timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Wait for a task to complete"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            status = await self.get_task_status(server_url, task_id)
            
            if not status:
                return None
            
            if status["status"] in ["completed", "failed", "cancelled"]:
                return status
            
            # Check timeout
            if timeout and (asyncio.get_event_loop().time() - start_time) > timeout:
                logger.warning(f"Task {task_id} timed out after {timeout} seconds")
                return None
            
            # Wait before polling again
            await asyncio.sleep(1)
    
    async def close(self):
        """Close the client"""
        await self.client.aclose()