"""
Base agent class with Agent Card, lifecycle management, and message handling.

Every agent in AgentOps inherits from BaseAgent, which provides:
- Agent Card: a machine-readable capability declaration (A2A standard)
- Lifecycle: init -> ready -> active -> paused -> stopped
- Message bus: async-compatible send/receive with priority routing
- Observability: automatic tracing of all agent actions
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class AgentState(str, Enum):
    """Agent lifecycle states."""
    INIT = "init"
    READY = "ready"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class AgentCard:
    """
    A2A Agent Card — machine-readable capability declaration.

    Every agent publishes a card describing what it can do, what inputs
    it accepts, and how to reach it. Other agents use cards to discover
    capabilities and route tasks.
    """
    agent_id: str
    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    input_schemas: dict[str, Any] = field(default_factory=dict)
    output_schemas: dict[str, Any] = field(default_factory=dict)
    endpoint: str = ""
    version: str = "0.1.0"
    priority: int = 5  # 1 = highest, 10 = lowest
    max_concurrent_tasks: int = 10
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize card for A2A discovery."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "input_schemas": self.input_schemas,
            "output_schemas": self.output_schemas,
            "endpoint": self.endpoint,
            "version": self.version,
            "priority": self.priority,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "tags": self.tags,
        }


class BaseAgent:
    """
    Base class for all AgentOps agents.

    Provides lifecycle management, message handling, and Agent Card
    publication for A2A protocol discovery.
    """

    def __init__(self, name: str, description: str, capabilities: list[str] | None = None):
        self.agent_id = str(uuid.uuid4())
        self.name = name
        self.description = description
        self._state = AgentState.INIT
        self._message_handlers: dict[str, Callable] = {}
        self._inbox: list[dict[str, Any]] = []
        self._outbox: list[dict[str, Any]] = []
        self._action_log: list[dict[str, Any]] = []
        self._created_at = time.time()
        self._last_active = time.time()
        self._active_tasks: dict[str, dict[str, Any]] = {}

        self.card = AgentCard(
            agent_id=self.agent_id,
            name=name,
            description=description,
            capabilities=capabilities or [],
        )

    @property
    def state(self) -> AgentState:
        """Current agent state."""
        return self._state

    @state.setter
    def state(self, new_state: AgentState) -> None:
        old_state = self._state
        valid_transitions = {
            AgentState.INIT: {AgentState.READY, AgentState.ERROR},
            AgentState.READY: {AgentState.ACTIVE, AgentState.STOPPED, AgentState.ERROR},
            AgentState.ACTIVE: {AgentState.PAUSED, AgentState.READY, AgentState.STOPPED, AgentState.ERROR},
            AgentState.PAUSED: {AgentState.ACTIVE, AgentState.STOPPED, AgentState.ERROR},
            AgentState.STOPPED: {AgentState.INIT},
            AgentState.ERROR: {AgentState.INIT, AgentState.STOPPED},
        }
        if new_state not in valid_transitions.get(old_state, set()):
            raise ValueError(
                f"Invalid state transition: {old_state.value} -> {new_state.value}"
            )
        self._state = new_state
        self._log_action("state_change", {"from": old_state.value, "to": new_state.value})

    def initialize(self) -> None:
        """Initialize the agent — override for custom setup."""
        self.state = AgentState.READY

    def start(self) -> None:
        """Start processing tasks."""
        if self._state == AgentState.INIT:
            self.initialize()
        self.state = AgentState.ACTIVE
        self._last_active = time.time()

    def pause(self) -> None:
        """Pause task processing (can resume)."""
        self.state = AgentState.PAUSED

    def resume(self) -> None:
        """Resume from paused state."""
        self.state = AgentState.ACTIVE
        self._last_active = time.time()

    def stop(self) -> None:
        """Stop the agent gracefully."""
        self.state = AgentState.STOPPED

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self._message_handlers[message_type] = handler

    def receive_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """
        Receive and process an incoming message.

        Returns the handler's response, or None if no handler matched.
        """
        self._inbox.append(message)
        self._last_active = time.time()
        msg_type = message.get("type", "unknown")
        handler = self._message_handlers.get(msg_type)

        if handler:
            self._log_action("message_received", {"type": msg_type, "id": message.get("id")})
            result = handler(message)
            return result

        self._log_action("message_unhandled", {"type": msg_type})
        return None

    def send_message(self, target_id: str, message: dict[str, Any]) -> None:
        """Queue a message for delivery to another agent."""
        message["source_agent_id"] = self.agent_id
        message["target_agent_id"] = target_id
        message["timestamp"] = time.time()
        self._outbox.append(message)
        self._log_action("message_sent", {"target": target_id, "type": message.get("type")})

    def create_task(self, task_type: str, params: dict[str, Any]) -> str:
        """Create a new task tracked by this agent."""
        task_id = str(uuid.uuid4())
        task = {
            "task_id": task_id,
            "type": task_type,
            "params": params,
            "status": "created",
            "created_at": time.time(),
            "updated_at": time.time(),
            "result": None,
        }
        self._active_tasks[task_id] = task
        self._log_action("task_created", {"task_id": task_id, "type": task_type})
        return task_id

    def complete_task(self, task_id: str, result: Any) -> None:
        """Mark a task as completed with its result."""
        if task_id not in self._active_tasks:
            raise KeyError(f"Unknown task: {task_id}")
        self._active_tasks[task_id]["status"] = "completed"
        self._active_tasks[task_id]["result"] = result
        self._active_tasks[task_id]["updated_at"] = time.time()
        self._log_action("task_completed", {"task_id": task_id})

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        if task_id not in self._active_tasks:
            raise KeyError(f"Unknown task: {task_id}")
        self._active_tasks[task_id]["status"] = "failed"
        self._active_tasks[task_id]["error"] = error
        self._active_tasks[task_id]["updated_at"] = time.time()
        self._log_action("task_failed", {"task_id": task_id, "error": error})

    def get_status(self) -> dict[str, Any]:
        """Return current agent status summary."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self._state.value,
            "active_tasks": len([t for t in self._active_tasks.values() if t["status"] == "created"]),
            "completed_tasks": len([t for t in self._active_tasks.values() if t["status"] == "completed"]),
            "failed_tasks": len([t for t in self._active_tasks.values() if t["status"] == "failed"]),
            "messages_received": len(self._inbox),
            "messages_sent": len(self._outbox),
            "last_active": self._last_active,
            "uptime": time.time() - self._created_at,
        }

    def get_action_log(self) -> list[dict[str, Any]]:
        """Return the full action log for audit."""
        return list(self._action_log)

    def _log_action(self, action: str, details: dict[str, Any] | None = None) -> None:
        """Log an agent action for observability."""
        entry = {
            "timestamp": time.time(),
            "agent_id": self.agent_id,
            "agent_name": self.name,
            "action": action,
            "details": details or {},
        }
        self._action_log.append(entry)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} state={self._state.value}>"
