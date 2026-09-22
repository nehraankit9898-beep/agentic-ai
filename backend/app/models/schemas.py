from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    """Role of a message in conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    """A single message in a conversation."""

    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[dict[str, Any]] = None


class ConversationState(BaseModel):
    """Current state of a conversation session."""

    session_id: str
    messages: list[Message] = []
    current_task: Optional[str] = None
    task_status: str = "idle"  # idle, planning, executing, completed, failed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ToolCall(BaseModel):
    """Represents a tool call request."""

    tool_name: str
    arguments: dict[str, Any]
    call_id: Optional[str] = None


class ToolResult(BaseModel):
    """Result from a tool execution."""

    success: bool
    output: Any
    error: Optional[str] = None
    call_id: Optional[str] = None


class TaskPlan(BaseModel):
    """A plan for executing a multi-step task."""

    steps: list[str]
    current_step: int = 0
    status: str = "pending"  # pending, in_progress, completed, failed


class AgentResponse(BaseModel):
    """Response from the agent after processing a request."""

    message: str
    tool_calls: list[ToolCall] = []
    task_plan: Optional[TaskPlan] = None
    requires_confirmation: bool = False
    status: str = "success"  # success, error, needs_confirmation
