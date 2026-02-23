"""
Diagnosis Agent — root cause analysis, topology-aware correlation, evidence collection.

The DiagnoserAgent receives alerts and health reports from MonitorAgent,
then performs structured root cause analysis:

1. Gather evidence from affected and neighboring devices
2. Correlate symptoms across the topology graph
3. Apply diagnostic rules to identify probable root causes
4. Produce a ranked list of hypotheses with confidence scores
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from agentops.agents.base import BaseAgent


@dataclass
class DiagnosticEvidence:
    """A piece of evidence collected during diagnosis."""
    evidence_id: str
    source: str  # device_id or system component
    category: str  # metric, log, config, topology
    description: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    relevance_score: float = 0.5  # 0.0 to 1.0


@dataclass
class RootCauseHypothesis:
    """A ranked hypothesis about the root cause."""
    hypothesis_id: str
    description: str
    confidence: float  # 0.0 to 1.0
    category: str  # hardware, software, config, capacity, external
    affected_devices: list[str] = field(default_factory=list)
    evidence: list[DiagnosticEvidence] = field(default_factory=list)
    recommended_action: str = ""
    blast_radius: int = 1  # estimated number of affected services


@dataclass
class DiagnosisReport:
    """Complete diagnosis report for an incident."""
    report_id: str
    incident_id: str
    timestamp: float
    primary_hypothesis: RootCauseHypothesis | None
    all_hypotheses: list[RootCauseHypothesis]
    evidence_collected: list[DiagnosticEvidence]
    topology_context: dict[str, Any]
    duration_seconds: float
    confidence_level: str  # high, medium, low


# Diagnostic rule templates for common infrastructure issues
DIAGNOSTIC_RULES: dict[str, dict[str, Any]] = {
    "cpu_spike": {
        "indicators": ["cpu_percent > 90", "response_time_ms > 1000"],
        "correlations": ["Check process table", "Review cron jobs", "Check for runaway queries"],
        "category": "capacity",
        "common_causes": [
            "Runaway process consuming CPU",
            "Insufficient capacity for current load",
            "Cryptominer or unauthorized workload",
            "Kernel compilation or heavy build job",
        ],
    },
    "memory_leak": {
        "indicators": ["memory_percent > 85", "memory_percent trending up"],
        "correlations": ["Check process RSS growth", "Review OOM killer logs"],
        "category": "software",
        "common_causes": [
            "Application memory leak (no GC/free)",
            "Cache not bounded",
            "Connection pool exhaustion",
            "JVM heap misconfiguration",
        ],
    },
    "disk_full": {
        "indicators": ["disk_percent > 90"],
        "correlations": ["Check log rotation", "Review large files", "Check temp directories"],
        "category": "capacity",
        "common_causes": [
            "Log files consuming disk space",
            "Database WAL/binlog growth",
            "Failed backup cleanup",
            "Core dump accumulation",
        ],
    },
    "link_down": {
        "indicators": ["link_state == 0", "network_error_rate > 0.05"],
        "correlations": ["Check physical layer", "Review spanning tree", "Check LACP"],
        "category": "hardware",
        "common_causes": [
            "Physical cable disconnected or damaged",
            "Transceiver/SFP failure",
            "Switch port error-disabled",
            "Spanning tree topology change",
        ],
    },
    "bgp_flap": {
        "indicators": ["bgp_prefixes < 100", "bgp_prefixes fluctuating"],
        "correlations": ["Check BGP neighbor state", "Review route policies", "Check MTU"],
        "category": "config",
        "common_causes": [
            "BGP neighbor configuration mismatch",
            "Route policy rejecting prefixes",
            "MTU mismatch causing TCP session drops",
            "Upstream provider maintenance",
        ],
    },
}


class DiagnoserAgent(BaseAgent):
    """
    Root cause analysis agent.

    Correlates alerts, collects evidence from topology-aware neighbors,
    and produces ranked hypotheses about the root cause of incidents.
    """

    def __init__(self) -> None:
        super().__init__(
            name="DiagnoserAgent",
            description="Root cause analysis with topology-aware correlation",
            capabilities=[
                "root_cause_analysis",
                "topology_correlation",
                "evidence_collection",
                "hypothesis_ranking",
            ],
        )
        self.diagnosis_reports: list[DiagnosisReport] = []
        self._topology: dict[str, list[str]] = {}  # device_id -> [neighbor_ids]

        self.register_handler("diagnose", self._handle_diagnose)
        self.register_handler("set_topology", self._handle_set_topology)

    def set_topology(self, topology: dict[str, list[str]]) -> None:
        """Set the network topology graph for correlation."""
        self._topology = topology
        self._log_action("topology_updated", {"devices": len(topology)})

    def diagnose_incident(
        self,
        incident_id: str,
        device_id: str,
        alerts: list[dict[str, Any]],
        metrics: dict[str, float] | None = None,
    ) -> DiagnosisReport:
        """
        Perform full root cause analysis for an incident.

        Steps:
        1. Classify the incident type from alert patterns
        2. Collect evidence from the device and its neighbors
        3. Apply diagnostic rules
        4. Generate and rank hypotheses
        5. Produce a diagnosis report
        """
        start_time = time.time()
        task_id = self.create_task("diagnosis", {
            "incident_id": incident_id,
            "device_id": device_id,
        })

        # Step 1: Classify incident type
        incident_type = self._classify_incident(alerts, metrics or {})

        # Step 2: Collect evidence
        evidence = self._collect_evidence(device_id, alerts, metrics or {}, incident_type)

        # Step 3: Get topology context
        topology_context = self._get_topology_context(device_id)

        # Step 4: Generate hypotheses
        hypotheses = self._generate_hypotheses(
            incident_type, device_id, evidence, topology_context
        )

        # Step 5: Rank hypotheses by confidence
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)

        # Determine overall confidence level
        top_confidence = hypotheses[0].confidence if hypotheses else 0
        if top_confidence > 0.8:
            confidence_level = "high"
        elif top_confidence > 0.5:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        duration = time.time() - start_time

        report = DiagnosisReport(
            report_id=f"DIAG-{uuid.uuid4().hex[:8]}",
            incident_id=incident_id,
            timestamp=time.time(),
            primary_hypothesis=hypotheses[0] if hypotheses else None,
            all_hypotheses=hypotheses,
            evidence_collected=evidence,
            topology_context=topology_context,
            duration_seconds=round(duration, 3),
            confidence_level=confidence_level,
        )

        self.diagnosis_reports.append(report)
        self.complete_task(task_id, {
            "report_id": report.report_id,
            "confidence": confidence_level,
            "hypothesis_count": len(hypotheses),
        })

        self._log_action("diagnosis_complete", {
            "report_id": report.report_id,
            "incident_id": incident_id,
            "primary_cause": hypotheses[0].description if hypotheses else "unknown",
            "confidence": confidence_level,
        })

        return report

    def _classify_incident(
        self, alerts: list[dict[str, Any]], metrics: dict[str, float]
    ) -> str:
        """Classify the incident type based on alert patterns."""
        alert_metrics = {a.get("metric", "") for a in alerts}

        if "link_state" in alert_metrics or metrics.get("link_state", 1) < 0.5:
            return "link_down"
        if "bgp_prefixes" in alert_metrics or metrics.get("bgp_prefixes", 999) < 100:
            return "bgp_flap"
        if "cpu_percent" in alert_metrics or metrics.get("cpu_percent", 0) > 90:
            return "cpu_spike"
        if "memory_percent" in alert_metrics or metrics.get("memory_percent", 0) > 85:
            return "memory_leak"
        if "disk_percent" in alert_metrics or metrics.get("disk_percent", 0) > 90:
            return "disk_full"
        return "unknown"

    def _collect_evidence(
        self,
        device_id: str,
        alerts: list[dict[str, Any]],
        metrics: dict[str, float],
        incident_type: str,
    ) -> list[DiagnosticEvidence]:
        """Collect diagnostic evidence from multiple sources."""
        evidence = []

        # Alert evidence
        for alert in alerts:
            evidence.append(DiagnosticEvidence(
                evidence_id=f"EV-{uuid.uuid4().hex[:6]}",
                source=device_id,
                category="metric",
                description=f"Alert: {alert.get('message', 'Unknown alert')}",
                data=alert,
                relevance_score=0.9,
            ))

        # Metric evidence
        for metric_name, value in metrics.items():
            evidence.append(DiagnosticEvidence(
                evidence_id=f"EV-{uuid.uuid4().hex[:6]}",
                source=device_id,
                category="metric",
                description=f"Current {metric_name} = {value}",
                data={"metric": metric_name, "value": value},
                relevance_score=0.7,
            ))

        # Simulated log evidence
        if incident_type in DIAGNOSTIC_RULES:
            rules = DIAGNOSTIC_RULES[incident_type]
            for correlation in rules["correlations"]:
                evidence.append(DiagnosticEvidence(
                    evidence_id=f"EV-{uuid.uuid4().hex[:6]}",
                    source=device_id,
                    category="log",
                    description=f"Investigation: {correlation}",
                    data={"check": correlation, "result": "anomaly_detected"},
                    relevance_score=0.6,
                ))

        # Topology neighbor evidence
        neighbors = self._topology.get(device_id, [])
        for neighbor in neighbors[:3]:  # Check first 3 neighbors
            evidence.append(DiagnosticEvidence(
                evidence_id=f"EV-{uuid.uuid4().hex[:6]}",
                source=neighbor,
                category="topology",
                description=f"Neighbor {neighbor} status checked",
                data={"neighbor_id": neighbor, "reachable": True},
                relevance_score=0.5,
            ))

        return evidence

    def _get_topology_context(self, device_id: str) -> dict[str, Any]:
        """Get topology context around the affected device."""
        neighbors = self._topology.get(device_id, [])
        second_hop = set()
        for n in neighbors:
            for nn in self._topology.get(n, []):
                if nn != device_id:
                    second_hop.add(nn)

        return {
            "device_id": device_id,
            "direct_neighbors": neighbors,
            "second_hop_neighbors": list(second_hop),
            "neighbor_count": len(neighbors),
            "potential_blast_radius": len(neighbors) + len(second_hop) + 1,
        }

    def _generate_hypotheses(
        self,
        incident_type: str,
        device_id: str,
        evidence: list[DiagnosticEvidence],
        topology_context: dict[str, Any],
    ) -> list[RootCauseHypothesis]:
        """Generate ranked root cause hypotheses."""
        hypotheses = []

        if incident_type in DIAGNOSTIC_RULES:
            rules = DIAGNOSTIC_RULES[incident_type]
            causes = rules["common_causes"]

            for i, cause in enumerate(causes):
                # Primary cause gets highest confidence
                confidence = max(0.3, 0.95 - (i * 0.15))
                relevant_evidence = [e for e in evidence if e.relevance_score > 0.5]

                hypotheses.append(RootCauseHypothesis(
                    hypothesis_id=f"HYP-{uuid.uuid4().hex[:6]}",
                    description=cause,
                    confidence=round(confidence, 2),
                    category=rules["category"],
                    affected_devices=[device_id] + topology_context.get("direct_neighbors", [])[:2],
                    evidence=relevant_evidence[:3],
                    recommended_action=f"Investigate: {cause}",
                    blast_radius=topology_context.get("potential_blast_radius", 1),
                ))
        else:
            hypotheses.append(RootCauseHypothesis(
                hypothesis_id=f"HYP-{uuid.uuid4().hex[:6]}",
                description="Unclassified incident — manual investigation required",
                confidence=0.3,
                category="unknown",
                affected_devices=[device_id],
                recommended_action="Escalate to on-call engineer",
            ))

        return hypotheses

    # Message handlers
    def _handle_diagnose(self, message: dict[str, Any]) -> dict[str, Any]:
        incident_id = message.get("incident_id", f"INC-{uuid.uuid4().hex[:6]}")
        device_id = message.get("device_id", "unknown")
        alerts = message.get("alerts", [])
        metrics = message.get("metrics")
        report = self.diagnose_incident(incident_id, device_id, alerts, metrics)
        return {
            "type": "diagnosis_report",
            "report_id": report.report_id,
            "primary_cause": report.primary_hypothesis.description if report.primary_hypothesis else "unknown",
            "confidence": report.confidence_level,
            "hypothesis_count": len(report.all_hypotheses),
        }

    def _handle_set_topology(self, message: dict[str, Any]) -> dict[str, Any]:
        topology = message.get("topology", {})
        self.set_topology(topology)
        return {"type": "topology_set", "device_count": len(topology)}
