"""Tests for Orchestrator — incident pipeline, DAG execution."""

import pytest
from agentops.orchestrator.engine import Orchestrator, IncidentStatus


class TestOrchestrator:
    def test_creation(self):
        orch = Orchestrator()
        assert len(orch._agents) == 4
        status = orch.get_status()
        assert all(s == "active" for s in status["agents"].values())

    def test_submit_incident(self):
        orch = Orchestrator()
        incident = orch.submit_incident("web-srv-01", "CPU spike", "cpu_spike")
        assert incident.incident_id.startswith("INC-")
        assert incident.status == IncidentStatus.DETECTED
        assert len(incident.dag_nodes) > 0

    def test_process_cpu_spike(self):
        orch = Orchestrator(auto_approve=True)
        incident = orch.submit_incident("web-srv-01", "CPU spike", "cpu_spike")
        incident = orch.process_incident(incident.incident_id)
        assert incident.status == IncidentStatus.RESOLVED
        assert incident.resolved_at is not None

    def test_process_link_down(self):
        orch = Orchestrator(auto_approve=True)
        incident = orch.submit_incident("core-rtr-01", "Link down", "link_down")
        incident = orch.process_incident(incident.incident_id)
        assert incident.status == IncidentStatus.RESOLVED

    def test_process_bgp_flap(self):
        orch = Orchestrator(auto_approve=True)
        incident = orch.submit_incident("core-rtr-02", "BGP flap", "bgp_flap")
        incident = orch.process_incident(incident.incident_id)
        assert incident.status == IncidentStatus.RESOLVED

    def test_process_disk_full(self):
        orch = Orchestrator(auto_approve=True)
        incident = orch.submit_incident("db-srv-01", "Disk full", "disk_full")
        incident = orch.process_incident(incident.incident_id)
        assert incident.status == IncidentStatus.RESOLVED

    def test_process_mem_leak(self):
        orch = Orchestrator(auto_approve=True)
        incident = orch.submit_incident("web-srv-02", "Memory leak", "mem_leak")
        incident = orch.process_incident(incident.incident_id)
        assert incident.status == IncidentStatus.RESOLVED

    def test_awaiting_approval_without_auto(self):
        orch = Orchestrator(auto_approve=False)
        incident = orch.submit_incident("web-srv-01", "CPU spike", "cpu_spike")
        incident = orch.process_incident(incident.incident_id)
        assert incident.status == IncidentStatus.AWAITING_APPROVAL

    def test_manual_approval(self):
        orch = Orchestrator(auto_approve=False)
        incident = orch.submit_incident("web-srv-01", "CPU spike", "cpu_spike")
        orch.process_incident(incident.incident_id)
        incident = orch.approve_incident(incident.incident_id, "test-op")
        assert incident.status == IncidentStatus.RESOLVED

    def test_timeline(self):
        orch = Orchestrator(auto_approve=True)
        incident = orch.submit_incident("web-srv-01", "CPU spike", "cpu_spike")
        orch.process_incident(incident.incident_id)
        timeline = orch.get_incident_timeline(incident.incident_id)
        assert len(timeline) > 5
        events = [e["event"] for e in timeline]
        assert "incident_created" in events
        assert "resolved" in events

    def test_unknown_incident(self):
        orch = Orchestrator()
        with pytest.raises(KeyError):
            orch.process_incident("nonexistent")

    def test_status_counts(self):
        orch = Orchestrator(auto_approve=True)
        orch.submit_incident("d1", "test", "cpu_spike")
        orch.submit_incident("d2", "test", "disk_full")
        status = orch.get_status()
        assert status["incidents"]["total"] == 2
