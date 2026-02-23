"""Tests for VerifierAgent — verification, SLA checks, rollback recommendation."""

import pytest
from agentops.agents.verifier import VerifierAgent, VerificationResult


class TestVerifierAgent:
    def test_creation(self):
        agent = VerifierAgent()
        assert agent.name == "VerifierAgent"
        assert "metric_comparison" in agent.card.capabilities

    def test_verify_improvement(self):
        agent = VerifierAgent()
        report = agent.verify_remediation(
            plan_id="REM-1",
            incident_id="INC-1",
            pre_metrics={"cpu_percent": 95.0, "memory_percent": 50.0},
            post_metrics={"cpu_percent": 30.0, "memory_percent": 48.0},
        )
        assert report.overall_result == VerificationResult.PASSED
        assert not report.rollback_recommended

    def test_verify_degradation(self):
        agent = VerifierAgent()
        report = agent.verify_remediation(
            plan_id="REM-2",
            incident_id="INC-2",
            pre_metrics={"cpu_percent": 80.0, "memory_percent": 50.0, "disk_percent": 60.0},
            post_metrics={"cpu_percent": 95.0, "memory_percent": 90.0, "disk_percent": 85.0},
        )
        assert report.overall_result == VerificationResult.FAILED
        assert report.rollback_recommended

    def test_sla_compliance(self):
        agent = VerifierAgent()
        report = agent.verify_remediation(
            plan_id="REM-3",
            incident_id="INC-3",
            pre_metrics={"cpu_percent": 95.0, "response_time_ms": 3000.0},
            post_metrics={"cpu_percent": 40.0, "response_time_ms": 200.0},
        )
        assert report.sla_compliance.get("cpu_percent") is True
        assert report.sla_compliance.get("response_time_ms") is True

    def test_sla_violation(self):
        agent = VerifierAgent()
        report = agent.verify_remediation(
            plan_id="REM-4",
            incident_id="INC-4",
            pre_metrics={"cpu_percent": 90.0},
            post_metrics={"cpu_percent": 85.0},
        )
        # 85% > 80% SLA target
        assert report.sla_compliance.get("cpu_percent") is False

    def test_improvement_calculation(self):
        agent = VerifierAgent()
        report = agent.verify_remediation(
            plan_id="REM-5",
            incident_id="INC-5",
            pre_metrics={"cpu_percent": 100.0},
            post_metrics={"cpu_percent": 50.0},
        )
        assert report.improvement["cpu_percent"] == -50.0

    def test_link_state_verification(self):
        agent = VerifierAgent()
        report = agent.verify_remediation(
            plan_id="REM-6",
            incident_id="INC-6",
            pre_metrics={"link_state": 0.0},
            post_metrics={"link_state": 1.0},
        )
        # Link going from 0 to 1 is improvement
        checks = [c for c in report.checks if c.check_type == "metric_comparison" and "link_state" in c.description]
        assert any(c.result == VerificationResult.PASSED for c in checks)

    def test_verification_summary(self):
        agent = VerifierAgent()
        report = agent.verify_remediation(
            plan_id="REM-7",
            incident_id="INC-7",
            pre_metrics={"cpu_percent": 95.0},
            post_metrics={"cpu_percent": 30.0},
        )
        summary = agent.get_verification_summary(report.report_id)
        assert summary["report_id"] == report.report_id
        assert "checks" in summary

    def test_message_handler(self):
        agent = VerifierAgent()
        result = agent.receive_message({
            "type": "verify",
            "plan_id": "REM-8",
            "incident_id": "INC-8",
            "pre_metrics": {"cpu_percent": 95.0},
            "post_metrics": {"cpu_percent": 30.0},
        })
        assert result is not None
        assert result["result"] in ("passed", "failed", "degraded")
