"""Integration tests — end-to-end pipeline for all scenarios."""

import pytest
from agentops.orchestrator.engine import Orchestrator, IncidentStatus


class TestEndToEndPipeline:
    """Full pipeline integration tests for each scenario."""

    @pytest.mark.parametrize("device,scenario,description", [
        ("core-rtr-01", "link_down", "Network link failure"),
        ("web-srv-01", "cpu_spike", "CPU utilization spike"),
        ("core-rtr-02", "bgp_flap", "BGP session instability"),
        ("db-srv-01", "disk_full", "Disk space critical"),
        ("web-srv-02", "mem_leak", "Memory leak detected"),
    ])
    def test_scenario_resolves(self, device, scenario, description):
        """Each scenario should resolve successfully with auto-approve."""
        orch = Orchestrator(auto_approve=True)
        incident = orch.submit_incident(device, description, scenario)
        incident = orch.process_incident(incident.incident_id)
        assert incident.status == IncidentStatus.RESOLVED, f"Scenario {scenario} did not resolve"
        assert incident.diagnosis_report is not None
        assert incident.remediation_plan is not None
        assert incident.verification_report is not None

    def test_multiple_incidents(self):
        """Process multiple incidents through the same orchestrator."""
        orch = Orchestrator(auto_approve=True)
        scenarios = [
            ("dev-1", "cpu_spike", "CPU spike"),
            ("dev-2", "disk_full", "Disk full"),
            ("dev-3", "link_down", "Link down"),
        ]
        for device, scenario, desc in scenarios:
            inc = orch.submit_incident(device, desc, scenario)
            orch.process_incident(inc.incident_id)

        assert len(orch.incidents) == 3
        resolved = [i for i in orch.incidents.values() if i.status == IncidentStatus.RESOLVED]
        assert len(resolved) == 3

    def test_diagnosis_has_evidence(self):
        """Verify diagnosis collects evidence."""
        orch = Orchestrator(auto_approve=True)
        inc = orch.submit_incident("dev-1", "CPU spike", "cpu_spike")
        inc = orch.process_incident(inc.incident_id)
        diag = inc.diagnosis_report
        assert len(diag.evidence_collected) > 0
        assert diag.primary_hypothesis is not None
        assert diag.primary_hypothesis.confidence > 0

    def test_remediation_has_steps(self):
        """Verify remediation plan contains actionable steps."""
        orch = Orchestrator(auto_approve=True)
        inc = orch.submit_incident("dev-1", "Disk full", "disk_full")
        inc = orch.process_incident(inc.incident_id)
        plan = inc.remediation_plan
        assert len(plan.steps) > 0
        assert all(s.executed for s in plan.steps)

    def test_verification_checks_sla(self):
        """Verify SLA compliance is checked."""
        orch = Orchestrator(auto_approve=True)
        inc = orch.submit_incident("dev-1", "CPU spike", "cpu_spike")
        inc = orch.process_incident(inc.incident_id)
        ver = inc.verification_report
        assert len(ver.sla_compliance) > 0

    def test_timeline_completeness(self):
        """Verify timeline captures all stages."""
        orch = Orchestrator(auto_approve=True)
        inc = orch.submit_incident("dev-1", "Link down", "link_down")
        inc = orch.process_incident(inc.incident_id)
        events = [e["event"] for e in inc.timeline]
        assert "incident_created" in events
        assert "detection_started" in events
        assert "diagnosis_started" in events
        assert "remediation_planning" in events
        assert "verification_started" in events
        assert "resolved" in events

    def test_hitl_approval_flow(self):
        """Test the full HITL approval workflow."""
        orch = Orchestrator(auto_approve=False)
        inc = orch.submit_incident("dev-1", "BGP flap", "bgp_flap")
        inc = orch.process_incident(inc.incident_id)
        assert inc.status == IncidentStatus.AWAITING_APPROVAL

        # Now approve
        inc = orch.approve_incident(inc.incident_id, "test-operator")
        assert inc.status == IncidentStatus.RESOLVED
