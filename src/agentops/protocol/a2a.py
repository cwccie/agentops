"""
A2A (Agent-to-Agent) Protocol implementation.

Provides agent discovery via Agent Cards, message routing with priority
queuing, conversation state tracking, and task delegation.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from agentops.agents.base import AgentCard, BaseAgent
from agentops.protocol.messages import (
    Message,
    MessageType,
    Priority,
    TaskMessage,
    TaskStatus,
)


class ConversationState:
    """Tracks the state of a multi-message conversation between agents."""

    def __init__(self, conversation_id: str, participants: list[str]):
        self.conversation_id = conversation_id
        self.participants = participants
        self.messages: list[Message] = []
        self.status: str = "active"  # active, completed, failed, timeout
        self.created_at = time.time()
        self.updated_at = time.time()

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = time.time()

    def complete(self) -> None:
        self.status = "completed"
        self.updated_at = time.time()

    def fail(self, reason: str = "") -> None:
        self.status = "failed"
        self.updated_at = time.time()


class A2AProtocol:
    """
    Agent-to-Agent protocol handler.

    Manages agent registration, capability discovery, message routing,
    and conversation state tracking.
    """

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}
        self._cards: dict[str, AgentCard] = {}
        self._conversations: dict[str, ConversationState] = {}
        self._message_queue: list[Message] = []
        self._delivered: list[Message] = []
        self._capability_index: dict[str, list[str]] = defaultdict(list)  # capability -> [agent_ids]
        self._message_log: list[dict[str, Any]] = []

    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent and index its capabilities."""
        self._agents[agent.agent_id] = agent
        self._cards[agent.agent_id] = agent.card
        for capability in agent.card.capabilities:
            self._capability_index[capability].append(agent.agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the registry."""
        if agent_id in self._agents:
            card = self._cards.get(agent_id)
            if card:
                for cap in card.capabilities:
                    if agent_id in self._capability_index[cap]:
                        self._capability_index[cap].remove(agent_id)
            del self._agents[agent_id]
            del self._cards[agent_id]

    def discover_agents(self, capability: str | None = None) -> list[AgentCard]:
        """Discover agents, optionally filtered by capability."""
        if capability:
            agent_ids = self._capability_index.get(capability, [])
            return [self._cards[aid] for aid in agent_ids if aid in self._cards]
        return list(self._cards.values())

    def find_best_agent(self, capability: str) -> str | None:
        """Find the best agent for a capability (lowest priority number = highest priority)."""
        candidates = self._capability_index.get(capability, [])
        if not candidates:
            return None

        # Sort by priority (lower number = higher priority) and active task count
        def score(agent_id: str) -> tuple[int, int]:
            card = self._cards[agent_id]
            agent = self._agents[agent_id]
            active = len([t for t in agent._active_tasks.values() if t["status"] == "created"])
            return (card.priority, active)

        candidates.sort(key=score)
        return candidates[0]

    def send_message(self, message: Message) -> str:
        """Queue a message for delivery."""
        self._message_queue.append(message)
        self._message_log.append({
            "action": "queued",
            "message_id": message.message_id,
            "type": message.type.value,
            "source": message.source_agent_id,
            "target": message.target_agent_id,
            "timestamp": time.time(),
        })
        return message.message_id

    def deliver_messages(self) -> list[dict[str, Any]]:
        """
        Deliver all queued messages to their target agents.

        Messages are delivered in priority order (lower number = higher priority).
        Returns a list of delivery results.
        """
        # Sort by priority
        self._message_queue.sort(key=lambda m: m.priority.value)

        results = []
        remaining = []

        for message in self._message_queue:
            if message.is_expired():
                results.append({
                    "message_id": message.message_id,
                    "status": "expired",
                })
                continue

            target = self._agents.get(message.target_agent_id)
            if not target:
                results.append({
                    "message_id": message.message_id,
                    "status": "undeliverable",
                    "reason": f"Agent {message.target_agent_id} not found",
                })
                continue

            # Deliver the message
            response = target.receive_message(message.to_dict())
            self._delivered.append(message)

            results.append({
                "message_id": message.message_id,
                "status": "delivered",
                "target": message.target_agent_id,
                "response": response,
            })

            # Track in conversation if correlation_id exists
            if message.correlation_id:
                if message.correlation_id not in self._conversations:
                    self._conversations[message.correlation_id] = ConversationState(
                        conversation_id=message.correlation_id,
                        participants=[message.source_agent_id, message.target_agent_id],
                    )
                self._conversations[message.correlation_id].add_message(message)

        self._message_queue = remaining  # Should be empty after processing all
        return results

    def delegate_task(
        self,
        from_agent_id: str,
        capability: str,
        task_type: str,
        params: dict[str, Any],
        priority: Priority = Priority.MEDIUM,
    ) -> TaskMessage | None:
        """
        Delegate a task to the best available agent with the required capability.

        Returns the task message if an agent was found, None otherwise.
        """
        target_id = self.find_best_agent(capability)
        if not target_id:
            return None

        task_msg = TaskMessage(
            type=MessageType.TASK_REQUEST,
            source_agent_id=from_agent_id,
            target_agent_id=target_id,
            priority=priority,
            task_type=task_type,
            task_params=params,
            delegated_from=from_agent_id,
            payload={"type": task_type, **params},
        )

        self.send_message(task_msg)
        return task_msg

    def broadcast(
        self, from_agent_id: str, message_type: MessageType, payload: dict[str, Any]
    ) -> int:
        """Broadcast a message to all registered agents."""
        count = 0
        for agent_id in self._agents:
            if agent_id != from_agent_id:
                msg = Message(
                    type=message_type,
                    source_agent_id=from_agent_id,
                    target_agent_id=agent_id,
                    payload=payload,
                )
                self.send_message(msg)
                count += 1
        return count

    def get_conversation(self, conversation_id: str) -> ConversationState | None:
        """Get a conversation by ID."""
        return self._conversations.get(conversation_id)

    def get_stats(self) -> dict[str, Any]:
        """Get protocol statistics."""
        return {
            "registered_agents": len(self._agents),
            "queued_messages": len(self._message_queue),
            "delivered_messages": len(self._delivered),
            "active_conversations": len(
                [c for c in self._conversations.values() if c.status == "active"]
            ),
            "indexed_capabilities": len(self._capability_index),
        }
