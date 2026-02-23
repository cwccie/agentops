"""Tests for RemediatorAgent — plan generation, approval, execution, rollback."""

import pytest
from agentops.agents.remediator import RemediatorAgent, RemediationStatus, RiskLevel


class TestRemediatorAgent:
    def test_creation(self):
        agent = RemediatorAgent()
        assert agent.name == "RemediatorAgent"
        assert "fix_generation" in agent.card.capabilities

    def test_generate_plan_cpu(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-1", "DIAG-1", "cpu_spike", "web-srv-01")
        assert plan.plan_id.startswith("REM-")
        assert plan.risk_level == RiskLevel.MEDIUM
        assert len(plan.steps) > 0
        assert plan.status == RemediationStatus.AWAITING_APPROVAL

    def test_generate_plan_link_down(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-2", "DIAG-2", "link_down", "core-rtr-01")
        assert plan.risk_level == RiskLevel.HIGH

    def test_generate_plan_disk_full(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-3", "DIAG-3", "disk_full", "db-srv-01")
        assert plan.risk_level == RiskLevel.LOW

    def test_blast_radius_limit(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-4", "DIAG-4", "cpu_spike", "web-srv-01", blast_radius=50)
        assert plan.status == RemediationStatus.REJECTED

    def test_approve_plan(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-5", "DIAG-5", "cpu_spike", "web-srv-01")
        approved = agent.approve_plan(plan.plan_id, "test-operator")
        assert approved.status == RemediationStatus.APPROVED
        assert approved.approved_by == "test-operator"

    def test_reject_plan(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-6", "DIAG-6", "cpu_spike", "web-srv-01")
        rejected = agent.reject_plan(plan.plan_id, "Too risky")
        assert rejected.status == RemediationStatus.REJECTED

    def test_cannot_approve_twice(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-7", "DIAG-7", "cpu_spike", "web-srv-01")
        agent.approve_plan(plan.plan_id)
        with pytest.raises(ValueError):
            agent.approve_plan(plan.plan_id)

    def test_execute_plan(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-8", "DIAG-8", "cpu_spike", "web-srv-01")
        agent.approve_plan(plan.plan_id)
        executed = agent.execute_plan(plan.plan_id)
        assert executed.status == RemediationStatus.COMPLETED
        assert all(s.executed for s in executed.steps)

    def test_execute_unapproved(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-9", "DIAG-9", "cpu_spike", "web-srv-01")
        with pytest.raises(ValueError):
            agent.execute_plan(plan.plan_id)

    def test_rollback_plan(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-10", "DIAG-10", "cpu_spike", "web-srv-01")
        agent.approve_plan(plan.plan_id)
        agent.execute_plan(plan.plan_id)
        rolled_back = agent.rollback_plan(plan.plan_id)
        assert rolled_back.status == RemediationStatus.ROLLED_BACK
        assert rolled_back.rollback_triggered

    def test_get_pending_approvals(self):
        agent = RemediatorAgent()
        agent.generate_plan("INC-11", "DIAG-11", "cpu_spike", "web-srv-01")
        agent.generate_plan("INC-12", "DIAG-12", "disk_full", "db-srv-01")
        pending = agent.get_pending_approvals()
        assert len(pending) == 2

    def test_plan_summary(self):
        agent = RemediatorAgent()
        plan = agent.generate_plan("INC-13", "DIAG-13", "cpu_spike", "web-srv-01")
        summary = agent.get_plan_summary(plan.plan_id)
        assert summary["plan_id"] == plan.plan_id
        assert "steps" in summary
        assert "blast_radius" in summary

    def test_unknown_plan(self):
        agent = RemediatorAgent()
        with pytest.raises(KeyError):
            agent.approve_plan("nonexistent")
