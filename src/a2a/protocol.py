"""A2A Protocol Core Components"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class TaskStatus(str, Enum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageType(str, Enum):
    TASK_REQUEST = "task_request"
    TASK_UPDATE = "task_update"
    TASK_RESULT = "task_result"
    RESOURCE_REQUEST = "resource_request"
    RESOURCE_RESPONSE = "resource_response"
    ARTIFACT_SUBMISSION = "artifact_submission"
    ERROR = "error"


class PartType(str, Enum):
    TEXT = "text"
    FILE_DIFF = "file_diff"
    JSON = "json"
    BINARY = "binary"
    CODE = "code"


class Part(BaseModel):
    """Represents a part of an artifact"""
    type: PartType
    content: Any
    metadata: Optional[Dict[str, Any]] = None
    encoding: Optional[str] = "utf-8"


class Artifact(BaseModel):
    """Represents an artifact exchanged between agents"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "artifact"
    parts: List[Part]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None


class Task(BaseModel):
    """Represents a task in the A2A protocol"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "task"
    status: TaskStatus = TaskStatus.CREATED
    title: str
    description: str
    resources: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    artifacts: List[Artifact] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None
    
    def update_status(self, status: TaskStatus):
        self.status = status
        self.updated_at = datetime.utcnow()
        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            self.completed_at = datetime.utcnow()


class Message(BaseModel):
    """Base message class for A2A communication"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType
    task_id: Optional[str] = None
    sender_id: str
    receiver_id: Optional[str] = None
    content: Optional[Any] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None


class AgentCard(BaseModel):
    """Agent discovery and capability declaration"""
    name: str
    version: str
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    capabilities: List[str]
    endpoints: Dict[str, str]
    authentication: Optional[str] = "Bearer"
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def to_wellknown(self) -> Dict[str, Any]:
        """Convert to .well-known/agent-card.json format"""
        return {
            "name": self.name,
            "version": self.version,
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
            "endpoints": self.endpoints,
            "authentication": self.authentication,
            "description": self.description,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }


class TaskRequest(BaseModel):
    """Request to create a new task"""
    title: str
    description: str
    resources: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskUpdate(BaseModel):
    """Update for an existing task"""
    task_id: str
    status: Optional[TaskStatus] = None
    progress: Optional[float] = None
    message: Optional[str] = None
    artifacts: Optional[List[Artifact]] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskResult(BaseModel):
    """Final result of a task"""
    task_id: str
    status: TaskStatus
    success: bool
    artifacts: Optional[List[Artifact]] = None
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class A2AProtocol:
    """A2A Protocol implementation"""
    
    VERSION = "1.0.0"
    
    @staticmethod
    def create_task(request: TaskRequest) -> Task:
        """Create a new task from request"""
        return Task(
            title=request.title,
            description=request.description,
            resources=request.resources,
            constraints=request.constraints,
            metadata=request.metadata
        )
    
    @staticmethod
    def create_message(
        type: MessageType,
        sender_id: str,
        content: Any = None,
        task_id: Optional[str] = None,
        receiver_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Message:
        """Create a new message"""
        return Message(
            type=type,
            sender_id=sender_id,
            receiver_id=receiver_id,
            task_id=task_id,
            content=content,
            metadata=metadata
        )
    
    @staticmethod
    def create_artifact(parts: List[Part], metadata: Optional[Dict[str, Any]] = None) -> Artifact:
        """Create a new artifact"""
        return Artifact(parts=parts, metadata=metadata)
    
    @staticmethod
    def create_file_diff_part(content: str, file_path: str) -> Part:
        """Create a file diff part"""
        return Part(
            type=PartType.FILE_DIFF,
            content=content,
            metadata={"file_path": file_path}
        )
    
    @staticmethod
    def create_text_part(content: str, metadata: Optional[Dict[str, Any]] = None) -> Part:
        """Create a text part"""
        return Part(
            type=PartType.TEXT,
            content=content,
            metadata=metadata
        )
    
    @staticmethod
    def validate_message(message: Dict[str, Any]) -> bool:
        """Validate a message against the protocol"""
        try:
            Message(**message)
            return True
        except Exception:
            return False