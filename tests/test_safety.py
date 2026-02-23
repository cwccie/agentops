"""Tests for safety mechanisms — kill switch, rollback, approval."""

import pytest
from agentops.agents.base import BaseAgent, AgentState
from agentops.safety.kill_switch import KillSwitch
from agentops.safety.rollback import RollbackManager, RollbackPolicy, RollbackTrigger
from agentops.safety.approval import ApprovalGate, ApprovalPolicy


class TestKillSwitch:
    def test_initial_state(self):
        ks = KillSwitch()
        assert not ks.is_active
        assert ks.check_gate() is True

    def test_activate(self):
        ks = KillSwitch()
        event = ks.activate("test emergency", "test-user")
        assert ks.is_active
        assert ks.check_gate() is False
        assert event.action == "activated"

    def test_deactivate(self):
        ks = KillSwitch()
        ks.activate("test")
        event = ks.deactivate("resolved", "operator")
        assert not ks.is_active
        assert event.action == "deactivated"

    def test_double_activate(self):
        ks = KillSwitch()
        ks.activate("test")
        with pytest.raises(RuntimeError):
            ks.activate("again")

    def test_pauses_agents(self):
        ks = KillSwitch()
        agent = BaseAgent("test", "test")
        agent.start()
        ks.register_agent(agent)
        event = ks.activate("emergency")
        assert agent.state == AgentState.PAUSED
        assert len(event.affected_agents) == 1

    def test_history(self):
        ks = KillSwitch()
        ks.activate("test")
        ks.deactivate("done")
        history = ks.get_history()
        assert len(history) == 2

    def test_status(self):
        ks = KillSwitch()
        status = ks.get_status()
        assert status["active"] is False
        assert status["total_activations"] == 0


class TestRollbackManager:
    def test_no_rollback_on_improvement(self):
        rm = RollbackManager()
        record = rm.evaluate(
            "REM-1", "INC-1",
            pre_metrics={"cpu_percent": 95.0},
            post_metrics={"cpu_percent": 30.0},
        )
        assert not record.executed

    def test_rollback_on_degradation(self):
        rm = RollbackManager()
        rolled_back = []
        rm.register_rollback_callback(lambda pid, r: rolled_back.append(pid))
        record = rm.evaluate(
            "REM-2", "INC-2",
            pre_metrics={"cpu_percent": 80.0},
            post_metrics={"cpu_percent": 95.0},
        )
        assert record.executed
        assert "REM-2" in rolled_back

    def test_force_rollback(self):
        rm = RollbackManager()
        record = rm.force_rollback("REM-3", "manual test")
        assert record.executed
        assert record.trigger == RollbackTrigger.MANUAL

    def test_policy_update(self):
        rm = RollbackManager()
        rm.update_policy(observation_window_seconds=600)
        assert rm.policy.observation_window_seconds == 600

    def test_history(self):
        rm = RollbackManager()
        rm.evaluate("REM-4", "INC-4", {"cpu_percent": 50.0}, {"cpu_percent": 40.0})
        history = rm.get_history()
        assert len(history) == 1


class TestApprovalGate:
    def test_always_require(self):
        gate = ApprovalGate(policy=ApprovalPolicy.ALWAYS_REQUIRE)
        req = gate.request_approval("REM-1", "INC-1", "medium", "Fix CPU spike")
        assert req.status == "pending"

    def test_auto_all(self):
        gate = ApprovalGate(policy=ApprovalPolicy.AUTO_ALL)
        req = gate.request_approval("REM-2", "INC-2", "high", "Fix link down")
        assert req.status == "approved"

    def test_auto_low_risk(self):
        gate = ApprovalGate(policy=ApprovalPolicy.AUTO_LOW_RISK)
        low = gate.request_approval("REM-3", "INC-3", "low", "Rotate logs")
        high = gate.request_approval("REM-4", "INC-4", "high", "BGP change")
        assert low.status == "approved"
        assert high.status == "pending"

    def test_manual_approve(self):
        gate = ApprovalGate()
        req = gate.request_approval("REM-5", "INC-5", "medium", "Test")
        gate.approve(req.request_id, "operator")
        assert req.status == "approved"
        assert gate.is_approved("REM-5")

    def test_reject(self):
        gate = ApprovalGate()
        req = gate.request_approval("REM-6", "INC-6", "high", "Test")
        gate.reject(req.request_id, "operator", "Too risky")
        assert req.status == "rejected"

    def test_pending_list(self):
        gate = ApprovalGate()
        gate.request_approval("REM-7", "INC-7", "medium", "Test 1")
        gate.request_approval("REM-8", "INC-8", "high", "Test 2")
        pending = gate.get_pending()
        assert len(pending) == 2

    def test_audit_log(self):
        gate = ApprovalGate()
        gate.request_approval("REM-9", "INC-9", "low", "Test")
        log = gate.get_audit_log()
        assert len(log) == 1
