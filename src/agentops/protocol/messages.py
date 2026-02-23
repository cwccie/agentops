"""
A2A Protocol message types and structures.

Defines the message format for inter-agent communication including
task delegation, status updates, and data exchange.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    """A2A message types."""
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    STATUS_UPDATE = "status_update"
    DATA_EXCHANGE = "data_exchange"
    DISCOVERY = "discovery"
    HEARTBEAT = "heartbeat"
    ESCALATION = "escalation"
    KILL_SIGNAL = "kill_signal"


class TaskStatus(str, Enum):
    """Task lifecycle states in A2A protocol."""
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DELEGATED = "delegated"


class Priority(int, Enum):
    """Message priority levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 5
    LOW = 8
    BACKGROUND = 10


@dataclass
class Message:
    """Base A2A protocol message."""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: MessageType = MessageType.DATA_EXCHANGE
    source_agent_id: str = ""
    target_agent_id: str = ""
    priority: Priority = Priority.MEDIUM
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    correlation_id: str = ""  # links related messages
    ttl_seconds: int = 300  # time to live

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "type": self.type.value,
            "source_agent_id": self.source_agent_id,
            "target_agent_id": self.target_agent_id,
            "priority": self.priority.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            type=MessageType(data.get("type", "data_exchange")),
            source_agent_id=data.get("source_agent_id", ""),
            target_agent_id=data.get("target_agent_id", ""),
            priority=Priority(data.get("priority", 5)),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", time.time()),
            correlation_id=data.get("correlation_id", ""),
            ttl_seconds=data.get("ttl_seconds", 300),
        )

    def is_expired(self) -> bool:
        return (time.time() - self.timestamp) > self.ttl_seconds


@dataclass
class TaskMessage(Message):
    """Task-specific A2A message with delegation support."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""
    task_status: TaskStatus = TaskStatus.SUBMITTED
    task_params: dict[str, Any] = field(default_factory=dict)
    task_result: Any = None
    delegated_from: str = ""  # agent_id that delegated this task
    deadline: float | None = None  # unix timestamp deadline

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({
            "task_id": self.task_id,
            "task_type": self.task_type,
            "task_status": self.task_status.value,
            "task_params": self.task_params,
            "task_result": self.task_result,
            "delegated_from": self.delegated_from,
            "deadline": self.deadline,
        })
        return base
