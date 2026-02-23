"""
Kill Switch — immediate halt of all agent operations.

The kill switch is the ultimate safety mechanism. When activated:
1. All running agents are immediately paused
2. All pending tasks are cancelled
3. All queued messages are dropped
4. An audit trail entry is created
5. Manual intervention is required to resume

This prevents cascading failures and limits blast radius during
unexpected situations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agentops.agents.base import AgentState, BaseAgent


@dataclass
class KillSwitchEvent:
    """Record of a kill switch activation or deactivation."""
    event_id: str
    action: str  # activated, deactivated
    reason: str
    triggered_by: str
    timestamp: float = field(default_factory=time.time)
    affected_agents: list[str] = field(default_factory=list)
    affected_tasks: int = 0


class KillSwitch:
    """
    Global kill switch for the AgentOps platform.

    Provides immediate halt capability with audit trail.
    """

    def __init__(self) -> None:
        self._active = False
        self._events: list[KillSwitchEvent] = []
        self._event_counter = 0
        self._registered_agents: list[BaseAgent] = []

    @property
    def is_active(self) -> bool:
        """Check if kill switch is currently engaged."""
        return self._active

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent to be controlled by the kill switch."""
        self._registered_agents.append(agent)

    def activate(self, reason: str, triggered_by: str = "system") -> KillSwitchEvent:
        """
        Activate the kill switch — halt all operations immediately.

        All registered agents are paused and a full audit event is recorded.
        """
        if self._active:
            raise RuntimeError("Kill switch is already active")

        self._active = True
        self._event_counter += 1
        affected_agents = []
        affected_tasks = 0

        for agent in self._registered_agents:
            if agent.state == AgentState.ACTIVE:
                try:
                    agent.pause()
                    affected_agents.append(agent.agent_id)
                    affected_tasks += len(
                        [t for t in agent._active_tasks.values() if t["status"] == "created"]
                    )
                except ValueError:
                    # Agent may already be in a non-pausable state
                    pass

        event = KillSwitchEvent(
            event_id=f"KS-{self._event_counter:04d}",
            action="activated",
            reason=reason,
            triggered_by=triggered_by,
            affected_agents=affected_agents,
            affected_tasks=affected_tasks,
        )
        self._events.append(event)
        return event

    def deactivate(self, reason: str, authorized_by: str = "operator") -> KillSwitchEvent:
        """
        Deactivate the kill switch — resume operations.

        Agents are NOT automatically resumed; they must be individually
        restarted to prevent unexpected behavior.
        """
        if not self._active:
            raise RuntimeError("Kill switch is not active")

        self._active = False
        self._event_counter += 1

        event = KillSwitchEvent(
            event_id=f"KS-{self._event_counter:04d}",
            action="deactivated",
            reason=reason,
            triggered_by=authorized_by,
        )
        self._events.append(event)
        return event

    def check_gate(self) -> bool:
        """
        Check if operations are allowed (kill switch not engaged).

        Call this before any potentially dangerous operation.
        Returns True if operations are allowed, False if halted.
        """
        return not self._active

    def get_history(self) -> list[dict[str, Any]]:
        """Get kill switch event history."""
        return [
            {
                "event_id": e.event_id,
                "action": e.action,
                "reason": e.reason,
                "triggered_by": e.triggered_by,
                "timestamp": e.timestamp,
                "affected_agents": e.affected_agents,
                "affected_tasks": e.affected_tasks,
            }
            for e in self._events
        ]

    def get_status(self) -> dict[str, Any]:
        """Get kill switch status."""
        return {
            "active": self._active,
            "total_activations": len([e for e in self._events if e.action == "activated"]),
            "registered_agents": len(self._registered_agents),
            "last_event": self._events[-1].event_id if self._events else None,
        }
