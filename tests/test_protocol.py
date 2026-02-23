"""Tests for A2A protocol — discovery, routing, conversations."""

import pytest
from agentops.agents.base import BaseAgent
from agentops.protocol.a2a import A2AProtocol
from agentops.protocol.messages import Message, TaskMessage, MessageType, Priority, TaskStatus


class TestMessages:
    def test_message_creation(self):
        msg = Message(type=MessageType.DATA_EXCHANGE, payload={"key": "value"})
        assert msg.message_id
        assert msg.type == MessageType.DATA_EXCHANGE

    def test_message_serialization(self):
        msg = Message(type=MessageType.HEARTBEAT, payload={"alive": True})
        d = msg.to_dict()
        assert d["type"] == "heartbeat"
        assert d["payload"]["alive"] is True

    def test_message_deserialization(self):
        data = {"type": "task_request", "payload": {"task": "test"}, "priority": 2}
        msg = Message.from_dict(data)
        assert msg.type == MessageType.TASK_REQUEST
        assert msg.priority == Priority.HIGH

    def test_message_expiry(self):
        msg = Message(ttl_seconds=0)
        import time
        time.sleep(0.01)
        assert msg.is_expired()

    def test_task_message(self):
        task = TaskMessage(
            task_type="diagnose",
            task_params={"device_id": "dev-1"},
            task_status=TaskStatus.SUBMITTED,
        )
        assert task.task_type == "diagnose"
        d = task.to_dict()
        assert "task_id" in d


class TestA2AProtocol:
    def test_register_agent(self):
        proto = A2AProtocol()
        agent = BaseAgent("test", "test agent", ["cap1", "cap2"])
        proto.register_agent(agent)
        assert agent.agent_id in proto._agents

    def test_discover_all(self):
        proto = A2AProtocol()
        a1 = BaseAgent("a1", "Agent 1", ["cap1"])
        a2 = BaseAgent("a2", "Agent 2", ["cap2"])
        proto.register_agent(a1)
        proto.register_agent(a2)
        cards = proto.discover_agents()
        assert len(cards) == 2

    def test_discover_by_capability(self):
        proto = A2AProtocol()
        a1 = BaseAgent("monitor", "Monitor", ["monitoring", "alerting"])
        a2 = BaseAgent("diag", "Diagnoser", ["rca"])
        proto.register_agent(a1)
        proto.register_agent(a2)
        cards = proto.discover_agents("monitoring")
        assert len(cards) == 1
        assert cards[0].name == "monitor"

    def test_find_best_agent(self):
        proto = A2AProtocol()
        a1 = BaseAgent("a1", "Agent 1", ["shared_cap"])
        proto.register_agent(a1)
        best = proto.find_best_agent("shared_cap")
        assert best == a1.agent_id

    def test_find_no_agent(self):
        proto = A2AProtocol()
        assert proto.find_best_agent("nonexistent") is None

    def test_send_and_deliver(self):
        proto = A2AProtocol()
        agent = BaseAgent("target", "Target", ["test"])
        agent.register_handler("data_exchange", lambda m: {"received": True})
        proto.register_agent(agent)

        msg = Message(
            type=MessageType.DATA_EXCHANGE,
            source_agent_id="sender",
            target_agent_id=agent.agent_id,
            payload={"data": "test"},
        )
        proto.send_message(msg)
        results = proto.deliver_messages()
        assert len(results) == 1
        assert results[0]["status"] == "delivered"

    def test_delegate_task(self):
        proto = A2AProtocol()
        agent = BaseAgent("worker", "Worker", ["compute"])
        proto.register_agent(agent)

        task = proto.delegate_task("requester", "compute", "calculate", {"x": 42})
        assert task is not None
        assert task.task_type == "calculate"

    def test_broadcast(self):
        proto = A2AProtocol()
        a1 = BaseAgent("a1", "A1", [])
        a2 = BaseAgent("a2", "A2", [])
        proto.register_agent(a1)
        proto.register_agent(a2)
        count = proto.broadcast(a1.agent_id, MessageType.HEARTBEAT, {"alive": True})
        assert count == 1  # broadcasts to all except sender

    def test_unregister_agent(self):
        proto = A2AProtocol()
        agent = BaseAgent("temp", "Temp", ["cap1"])
        proto.register_agent(agent)
        proto.unregister_agent(agent.agent_id)
        assert agent.agent_id not in proto._agents
        assert proto.find_best_agent("cap1") is None

    def test_stats(self):
        proto = A2AProtocol()
        a1 = BaseAgent("a1", "A1", ["cap1"])
        proto.register_agent(a1)
        stats = proto.get_stats()
        assert stats["registered_agents"] == 1
