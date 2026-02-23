"""Tests for BaseAgent — lifecycle, messaging, task management."""

import pytest
from agentops.agents.base import BaseAgent, AgentCard, AgentState


class TestAgentCard:
    def test_card_creation(self):
        card = AgentCard(
            agent_id="test-001",
            name="TestAgent",
            description="A test agent",
            capabilities=["test", "mock"],
        )
        assert card.agent_id == "test-001"
        assert card.name == "TestAgent"
        assert "test" in card.capabilities

    def test_card_to_dict(self):
        card = AgentCard(agent_id="t1", name="T", description="D")
        d = card.to_dict()
        assert d["agent_id"] == "t1"
        assert isinstance(d["capabilities"], list)

    def test_card_defaults(self):
        card = AgentCard(agent_id="t1", name="T", description="D")
        assert card.priority == 5
        assert card.max_concurrent_tasks == 10
        assert card.version == "0.1.0"


class TestAgentLifecycle:
    def test_initial_state(self):
        agent = BaseAgent("test", "test agent")
        assert agent.state == AgentState.INIT

    def test_initialize(self):
        agent = BaseAgent("test", "test agent")
        agent.initialize()
        assert agent.state == AgentState.READY

    def test_start(self):
        agent = BaseAgent("test", "test agent")
        agent.start()
        assert agent.state == AgentState.ACTIVE

    def test_pause_resume(self):
        agent = BaseAgent("test", "test agent")
        agent.start()
        agent.pause()
        assert agent.state == AgentState.PAUSED
        agent.resume()
        assert agent.state == AgentState.ACTIVE

    def test_stop(self):
        agent = BaseAgent("test", "test agent")
        agent.start()
        agent.stop()
        assert agent.state == AgentState.STOPPED

    def test_invalid_transition(self):
        agent = BaseAgent("test", "test agent")
        with pytest.raises(ValueError, match="Invalid state transition"):
            agent.state = AgentState.ACTIVE  # Can't go INIT -> ACTIVE directly

    def test_error_recovery(self):
        agent = BaseAgent("test", "test agent")
        agent.state = AgentState.ERROR
        agent.state = AgentState.INIT
        assert agent.state == AgentState.INIT


class TestAgentMessaging:
    def test_register_handler(self):
        agent = BaseAgent("test", "test agent")
        handler_called = []
        agent.register_handler("ping", lambda m: handler_called.append(True))
        agent.receive_message({"type": "ping"})
        assert handler_called

    def test_handler_response(self):
        agent = BaseAgent("test", "test agent")
        agent.register_handler("echo", lambda m: {"echoed": m.get("data")})
        result = agent.receive_message({"type": "echo", "data": "hello"})
        assert result == {"echoed": "hello"}

    def test_unhandled_message(self):
        agent = BaseAgent("test", "test agent")
        result = agent.receive_message({"type": "unknown"})
        assert result is None

    def test_send_message(self):
        agent = BaseAgent("test", "test agent")
        agent.send_message("target-1", {"type": "test", "data": "payload"})
        assert len(agent._outbox) == 1
        assert agent._outbox[0]["target_agent_id"] == "target-1"

    def test_inbox_tracking(self):
        agent = BaseAgent("test", "test agent")
        agent.receive_message({"type": "a"})
        agent.receive_message({"type": "b"})
        assert len(agent._inbox) == 2


class TestAgentTasks:
    def test_create_task(self):
        agent = BaseAgent("test", "test agent")
        task_id = agent.create_task("test_task", {"key": "value"})
        assert task_id in agent._active_tasks
        assert agent._active_tasks[task_id]["status"] == "created"

    def test_complete_task(self):
        agent = BaseAgent("test", "test agent")
        task_id = agent.create_task("test_task", {})
        agent.complete_task(task_id, {"result": "success"})
        assert agent._active_tasks[task_id]["status"] == "completed"
        assert agent._active_tasks[task_id]["result"] == {"result": "success"}

    def test_fail_task(self):
        agent = BaseAgent("test", "test agent")
        task_id = agent.create_task("test_task", {})
        agent.fail_task(task_id, "something went wrong")
        assert agent._active_tasks[task_id]["status"] == "failed"

    def test_unknown_task(self):
        agent = BaseAgent("test", "test agent")
        with pytest.raises(KeyError):
            agent.complete_task("nonexistent", None)


class TestAgentStatus:
    def test_get_status(self):
        agent = BaseAgent("test", "test agent")
        agent.start()
        status = agent.get_status()
        assert status["name"] == "test"
        assert status["state"] == "active"
        assert "uptime" in status

    def test_action_log(self):
        agent = BaseAgent("test", "test agent")
        agent.start()
        log = agent.get_action_log()
        assert len(log) >= 1
        assert any(e["action"] == "state_change" for e in log)

    def test_repr(self):
        agent = BaseAgent("test", "test agent")
        assert "test" in repr(agent)
        assert "init" in repr(agent)
