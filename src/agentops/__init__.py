"""
AgentOps — Multi-Agent Infrastructure Remediation Platform

Specialized AI agents coordinate via A2A protocol to detect, diagnose,
and fix infrastructure issues with human-in-the-loop approval and
automatic rollback safety guarantees.
"""

__version__ = "0.1.0"
__author__ = "Corey A. Wade"

from agentops.agents.base import BaseAgent, AgentCard, AgentState
from agentops.protocol.messages import Message, TaskMessage, MessageType
from agentops.protocol.a2a import A2AProtocol
from agentops.orchestrator.engine import Orchestrator
from agentops.safety.kill_switch import KillSwitch
from agentops.safety.rollback import RollbackManager
from agentops.observe.tracer import Tracer
from agentops.inventory.registry import DeviceRegistry

__all__ = [
    "BaseAgent",
    "AgentCard",
    "AgentState",
    "Message",
    "TaskMessage",
    "MessageType",
    "A2AProtocol",
    "Orchestrator",
    "KillSwitch",
    "RollbackManager",
    "Tracer",
    "DeviceRegistry",
]
