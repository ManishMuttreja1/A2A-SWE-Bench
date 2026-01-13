"""A2A Server Implementation"""

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from typing import Dict, Any, Optional, Callable, List
import asyncio
import json
from datetime import datetime
import logging
from .protocol import (
    A2AProtocol, Message, Task, TaskStatus, MessageType,
    TaskRequest, TaskUpdate, TaskResult, AgentCard, Artifact
)

logger = logging.getLogger(__name__)


class A2AServer:
    """A2A Protocol Server implementation"""
    
    def __init__(
        self,
        agent_card: AgentCard,
        task_handler: Optional[Callable] = None,
        host: str = "0.0.0.0",
        port: int = 8000
    ):
        self.agent_card = agent_card
        self.task_handler = task_handler
        self.host = host
        self.port = port
        self.app = FastAPI(title=agent_card.name, version=agent_card.version)
        self.tasks: Dict[str, Task] = {}
        self.message_queue: Dict[str, asyncio.Queue] = {}
        self._setup_routes()
    
    def _setup_routes(self):
        """Setup FastAPI routes for A2A protocol"""
        
        @self.app.get("/.well-known/agent-card.json")
        async def get_agent_card():
            """Return agent card for discovery"""
            return self.agent_card.to_wellknown()
        
        @self.app.post("/a2a/task")
        async def create_task(request: TaskRequest):
            """Create a new task"""
            task = A2AProtocol.create_task(request)
            self.tasks[task.id] = task
            
            # Create message queue for this task
            self.message_queue[task.id] = asyncio.Queue()
            
            # Start task handler in background if provided
            if self.task_handler:
                asyncio.create_task(self._handle_task(task))
            
            return {"task_id": task.id, "status": task.status}
        
        @self.app.get("/a2a/task/{task_id}")
        async def get_task(task_id: str):
            """Get task status"""
            if task_id not in self.tasks:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task = self.tasks[task_id]
            def _part_to_safe_dict(part):
                content = part.content
                if isinstance(content, (str, int, float, bool)) or content is None:
                    safe_content = content
                else:
                    # Avoid recursive/non-serializable structures by stringifying
                    safe_content = repr(content)
                return {
                    # Always emit enum value (e.g., "code") instead of repr (e.g., "PartType.CODE")
                    "type": part.type.value if hasattr(part.type, "value") else str(part.type),
                    "content": safe_content,
                    "metadata": part.metadata,
                    "encoding": part.encoding,
                }

            def _artifact_to_safe_dict(artifact):
                return {
                    "id": artifact.id,
                    "type": artifact.type,
                    "created_at": artifact.created_at.isoformat(),
                    "metadata": artifact.metadata,
                    "parts": [_part_to_safe_dict(p) for p in artifact.parts],
                }

            response_data = {
                "task_id": task.id,
                "status": task.status,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "artifacts": [_artifact_to_safe_dict(a) for a in task.artifacts],
            }
            return JSONResponse(content=response_data)
        
        @self.app.post("/a2a/task/{task_id}/update")
        async def update_task(task_id: str, update: TaskUpdate):
            """Update task status"""
            if task_id not in self.tasks:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task = self.tasks[task_id]
            
            if update.status:
                task.update_status(update.status)
            
            if update.artifacts:
                task.artifacts.extend(update.artifacts)
            
            # Queue update message
            message = A2AProtocol.create_message(
                type=MessageType.TASK_UPDATE,
                sender_id=self.agent_card.agent_id,
                task_id=task_id,
                content=update.dict()
            )
            
            if task_id in self.message_queue:
                await self.message_queue[task_id].put(message)
            
            return {"status": "updated", "task_status": task.status}
        
        @self.app.post("/a2a/task/{task_id}/artifact")
        async def submit_artifact(task_id: str, artifact: Artifact):
            """Submit an artifact for a task"""
            if task_id not in self.tasks:
                raise HTTPException(status_code=404, detail="Task not found")
            
            task = self.tasks[task_id]
            task.artifacts.append(artifact)
            
            # Queue artifact message
            message = A2AProtocol.create_message(
                type=MessageType.ARTIFACT_SUBMISSION,
                sender_id=self.agent_card.agent_id,
                task_id=task_id,
                content=artifact.dict()
            )
            
            if task_id in self.message_queue:
                await self.message_queue[task_id].put(message)
            
            return {"status": "accepted", "artifact_id": artifact.id}
        
        @self.app.get("/a2a/task/{task_id}/stream")
        async def stream_task_updates(task_id: str):
            """Stream task updates via Server-Sent Events"""
            if task_id not in self.tasks:
                raise HTTPException(status_code=404, detail="Task not found")
            
            async def event_generator():
                queue = self.message_queue.get(task_id)
                if not queue:
                    return
                
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=30)
                        data = json.dumps(message.dict())
                        yield f"data: {data}\n\n"
                    except asyncio.TimeoutError:
                        # Send heartbeat
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    except Exception as e:
                        logger.error(f"Error in event stream: {e}")
                        break
            
            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        
        @self.app.post("/a2a/message")
        async def receive_message(message: Message):
            """Receive a message from another agent"""
            # Validate message
            if not A2AProtocol.validate_message(message.dict()):
                raise HTTPException(status_code=400, detail="Invalid message format")
            
            # Process based on message type
            if message.type == MessageType.TASK_REQUEST and message.content:
                request = TaskRequest(**message.content)
                task = A2AProtocol.create_task(request)
                self.tasks[task.id] = task
                
                if self.task_handler:
                    asyncio.create_task(self._handle_task(task))
                
                return {"task_id": task.id, "status": "accepted"}
            
            return {"status": "received", "message_id": message.id}
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {
                "status": "healthy",
                "agent": self.agent_card.name,
                "version": self.agent_card.version,
                "tasks_active": len([t for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS])
            }
    
    async def _handle_task(self, task: Task):
        """Handle task execution"""
        try:
            # Update task status to in progress
            task.update_status(TaskStatus.IN_PROGRESS)
            
            # Call the task handler if provided
            if self.task_handler:
                result = await self.task_handler(task)
                
                # Update task based on result
                if result.get("success"):
                    task.update_status(TaskStatus.COMPLETED)
                else:
                    task.update_status(TaskStatus.FAILED)
                
                # Add result artifacts if any
                if result.get("artifacts"):
                    task.artifacts.extend(result["artifacts"])
                
                # Send final result message
                message = A2AProtocol.create_message(
                    type=MessageType.TASK_RESULT,
                    sender_id=self.agent_card.agent_id,
                    task_id=task.id,
                    content=TaskResult(
                        task_id=task.id,
                        status=task.status,
                        success=result.get("success", False),
                        artifacts=task.artifacts,
                        error=result.get("error"),
                        metrics=result.get("metrics")
                    ).dict()
                )
                
                if task.id in self.message_queue:
                    await self.message_queue[task.id].put(message)
        
        except Exception as e:
            logger.error(f"Error handling task {task.id}: {e}")
            task.update_status(TaskStatus.FAILED)
            
            # Send error message
            message = A2AProtocol.create_message(
                type=MessageType.ERROR,
                sender_id=self.agent_card.agent_id,
                task_id=task.id,
                content={"error": str(e)}
            )
            
            if task.id in self.message_queue:
                await self.message_queue[task.id].put(message)
    
    def run(self):
        """Run the A2A server"""
        import uvicorn
        uvicorn.run(self.app, host=self.host, port=self.port)

    async def run_async(self):
        """Run the A2A server inside an existing event loop"""
        import uvicorn
        config = uvicorn.Config(self.app, host=self.host, port=self.port, loop="asyncio")
        server = uvicorn.Server(config)
        await server.serve()