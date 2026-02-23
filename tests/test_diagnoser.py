"""Tests for DiagnoserAgent — RCA, evidence collection, hypothesis ranking."""

import pytest
from agentops.agents.diagnoser import DiagnoserAgent, DIAGNOSTIC_RULES


class TestDiagnoserAgent:
    def test_creation(self):
        agent = DiagnoserAgent()
        assert agent.name == "DiagnoserAgent"
        assert "root_cause_analysis" in agent.card.capabilities

    def test_set_topology(self):
        agent = DiagnoserAgent()
        topo = {"dev-1": ["dev-2", "dev-3"], "dev-2": ["dev-1"]}
        agent.set_topology(topo)
        assert len(agent._topology) == 2

    def test_diagnose_cpu_spike(self):
        agent = DiagnoserAgent()
        report = agent.diagnose_incident(
            incident_id="INC-001",
            device_id="web-srv-01",
            alerts=[{"metric": "cpu_percent", "value": 97, "message": "CPU critical"}],
            metrics={"cpu_percent": 97.0, "response_time_ms": 4500.0},
        )
        assert report.report_id.startswith("DIAG-")
        assert report.primary_hypothesis is not None
        assert report.primary_hypothesis.confidence > 0.5
        assert report.confidence_level in ("high", "medium", "low")

    def test_diagnose_link_down(self):
        agent = DiagnoserAgent()
        report = agent.diagnose_incident(
            incident_id="INC-002",
            device_id="core-rtr-01",
            alerts=[{"metric": "link_state", "value": 0, "message": "Link down"}],
            metrics={"link_state": 0.0, "network_error_rate": 0.08},
        )
        assert report.primary_hypothesis is not None
        assert report.primary_hypothesis.category == "hardware"

    def test_diagnose_bgp_flap(self):
        agent = DiagnoserAgent()
        report = agent.diagnose_incident(
            incident_id="INC-003",
            device_id="core-rtr-02",
            alerts=[{"metric": "bgp_prefixes", "value": 45, "message": "BGP prefix drop"}],
            metrics={"bgp_prefixes": 45.0},
        )
        assert report.primary_hypothesis.category == "config"

    def test_diagnose_unknown(self):
        agent = DiagnoserAgent()
        report = agent.diagnose_incident(
            incident_id="INC-004",
            device_id="unknown-dev",
            alerts=[{"metric": "custom_metric", "value": 999, "message": "Unknown alert"}],
            metrics={"custom_metric": 999.0},
        )
        assert len(report.all_hypotheses) >= 1

    def test_evidence_collection(self):
        agent = DiagnoserAgent()
        agent.set_topology({"dev-1": ["dev-2", "dev-3"]})
        report = agent.diagnose_incident(
            incident_id="INC-005",
            device_id="dev-1",
            alerts=[{"metric": "cpu_percent", "value": 95, "message": "CPU high"}],
            metrics={"cpu_percent": 95.0},
        )
        assert len(report.evidence_collected) > 0
        categories = {e.category for e in report.evidence_collected}
        assert "metric" in categories

    def test_topology_context(self):
        agent = DiagnoserAgent()
        agent.set_topology({
            "dev-1": ["dev-2", "dev-3"],
            "dev-2": ["dev-1", "dev-4"],
            "dev-3": ["dev-1"],
        })
        report = agent.diagnose_incident(
            incident_id="INC-006",
            device_id="dev-1",
            alerts=[{"metric": "link_state", "value": 0, "message": "Down"}],
            metrics={"link_state": 0.0},
        )
        assert report.topology_context["device_id"] == "dev-1"
        assert len(report.topology_context["direct_neighbors"]) == 2

    def test_hypothesis_ranking(self):
        agent = DiagnoserAgent()
        report = agent.diagnose_incident(
            incident_id="INC-007",
            device_id="dev-1",
            alerts=[{"metric": "disk_percent", "value": 94, "message": "Disk full"}],
            metrics={"disk_percent": 94.0},
        )
        # Hypotheses should be sorted by confidence descending
        confidences = [h.confidence for h in report.all_hypotheses]
        assert confidences == sorted(confidences, reverse=True)

    def test_message_handler(self):
        agent = DiagnoserAgent()
        result = agent.receive_message({
            "type": "diagnose",
            "device_id": "dev-1",
            "alerts": [{"metric": "cpu_percent", "value": 95, "message": "High CPU"}],
            "metrics": {"cpu_percent": 95.0},
        })
        assert result is not None
        assert "report_id" in result
