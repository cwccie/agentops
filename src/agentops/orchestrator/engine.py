"""
Orchestrator — DAG-based task decomposition, parallel execution,
dependency resolution, and timeout handling.

The Orchestrator is the brain of AgentOps. It takes an incident and
decomposes it into a directed acyclic graph (DAG) of tasks, then
executes them respecting dependencies, parallelism, and timeouts.

Pipeline: Monitor -> Diagnose -> Remediate -> Verify
         (with approval gate between Remediate and Execute)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentops.agents.base import BaseAgent
from agentops.agents.diagnoser import DiagnoserAgent
from agentops.agents.monitor import MonitorAgent
from agentops.agents.remediator import RemediatorAgent
from agentops.agents.verifier import VerifierAgent
from agentops.protocol.a2a import A2AProtocol


class IncidentStatus(str, Enum):
    """Incident lifecycle status."""
    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    DIAGNOSED = "diagnosed"
    REMEDIATING = "remediating"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    ROLLED_BACK = "rolled_back"
    ESCALATED = "escalated"
    FAILED = "failed"


@dataclass
class DAGNode:
    """A node in the task execution DAG."""
    node_id: str
    task_type: str
    agent_capability: str
    params: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # node_ids this depends on
    status: str = "pending"  # pending, running, completed, failed, skipped
    result: Any = None
    started_at: float | None = None
    completed_at: float | None = None
    timeout_seconds: int = 300


@dataclass
class Incident:
    """An infrastructure incident being processed by the orchestrator."""
    incident_id: str
    device_id: str
    description: str
    scenario: str
    status: IncidentStatus = IncidentStatus.DETECTED
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    dag_nodes: list[DAGNode] = field(default_factory=list)
    diagnosis_report: Any = None
    remediation_plan: Any = None
    verification_report: Any = None
    timeline: list[dict[str, Any]] = field(default_factory=list)
    auto_approve: bool = False


class Orchestrator:
    """
    Central orchestrator for the AgentOps incident resolution pipeline.

    Manages the full lifecycle:
    1. Detect (MonitorAgent collects metrics, triggers alerts)
    2. Diagnose (DiagnoserAgent performs RCA)
    3. Remediate (RemediatorAgent generates fix plan)
    4. Approve (HITL gate — human approves the plan)
    5. Execute (RemediatorAgent executes the approved plan)
    6. Verify (VerifierAgent confirms the fix)
    7. Rollback (if verification fails)
    """

    def __init__(self, auto_approve: bool = False) -> None:
        self.protocol = A2AProtocol()
        self.monitor = MonitorAgent()
        self.diagnoser = DiagnoserAgent()
        self.remediator = RemediatorAgent()
        self.verifier = VerifierAgent()
        self.auto_approve = auto_approve
        self.incidents: dict[str, Incident] = {}
        self._agents: list[BaseAgent] = []

        # Register all agents
        for agent in [self.monitor, self.diagnoser, self.remediator, self.verifier]:
            agent.start()
            self.protocol.register_agent(agent)
            self._agents.append(agent)

    def submit_incident(
        self, device_id: str, description: str, scenario: str = "unknown"
    ) -> Incident:
        """
        Submit a new incident for automated resolution.

        This creates the full DAG and begins execution.
        """
        incident_id = f"INC-{uuid.uuid4().hex[:8]}"

        incident = Incident(
            incident_id=incident_id,
            device_id=device_id,
            description=description,
            scenario=scenario,
            auto_approve=self.auto_approve,
        )

        # Build the execution DAG
        incident.dag_nodes = self._build_dag(incident_id, device_id, scenario)
        self.incidents[incident_id] = incident

        self._add_timeline(incident, "incident_created", {
            "description": description,
            "scenario": scenario,
        })

        return incident

    def process_incident(self, incident_id: str) -> Incident:
        """
        Process an incident through the full pipeline.

        Executes DAG nodes in dependency order, handling each stage
        of the detect -> diagnose -> remediate -> verify pipeline.
        """
        incident = self.incidents.get(incident_id)
        if not incident:
            raise KeyError(f"Unknown incident: {incident_id}")

        # Stage 1: Monitor / Detect
        incident.status = IncidentStatus.DETECTED
        self._add_timeline(incident, "detection_started", {})

        self.monitor.setup_mock_device(incident.device_id, incident.scenario)
        health_report = self.monitor.check_device(incident.device_id)
        pre_metrics = health_report["metrics"]

        self._add_timeline(incident, "detection_complete", {
            "alerts": len(health_report["alerts"]),
            "healthy": health_report["healthy"],
        })

        # Stage 2: Diagnose
        incident.status = IncidentStatus.DIAGNOSING
        self._add_timeline(incident, "diagnosis_started", {})

        diagnosis = self.diagnoser.diagnose_incident(
            incident_id=incident.incident_id,
            device_id=incident.device_id,
            alerts=health_report["alerts"],
            metrics=pre_metrics,
        )
        incident.diagnosis_report = diagnosis

        incident.status = IncidentStatus.DIAGNOSED
        self._add_timeline(incident, "diagnosis_complete", {
            "report_id": diagnosis.report_id,
            "primary_cause": (
                diagnosis.primary_hypothesis.description
                if diagnosis.primary_hypothesis
                else "unknown"
            ),
            "confidence": diagnosis.confidence_level,
        })

        # Determine incident type from diagnosis
        incident_type = incident.scenario
        if diagnosis.primary_hypothesis:
            incident_type = diagnosis.primary_hypothesis.category

        # Stage 3: Generate remediation plan
        incident.status = IncidentStatus.REMEDIATING
        self._add_timeline(incident, "remediation_planning", {})

        blast_radius = 1
        if diagnosis.primary_hypothesis:
            blast_radius = diagnosis.primary_hypothesis.blast_radius

        plan = self.remediator.generate_plan(
            incident_id=incident.incident_id,
            diagnosis_report_id=diagnosis.report_id,
            incident_type=incident.scenario,
            device_id=incident.device_id,
            blast_radius=blast_radius,
        )
        incident.remediation_plan = plan

        self._add_timeline(incident, "remediation_plan_generated", {
            "plan_id": plan.plan_id,
            "risk_level": plan.risk_level.value,
            "step_count": len(plan.steps),
        })

        # Stage 4: Approval gate
        incident.status = IncidentStatus.AWAITING_APPROVAL
        self._add_timeline(incident, "awaiting_approval", {
            "plan_id": plan.plan_id,
            "auto_approve": incident.auto_approve,
        })

        if incident.auto_approve:
            self.remediator.approve_plan(plan.plan_id, approved_by="auto-orchestrator")
            self._add_timeline(incident, "auto_approved", {"plan_id": plan.plan_id})
        else:
            # In non-auto mode, stop here and wait for manual approval
            return incident

        # Stage 5: Execute
        incident.status = IncidentStatus.EXECUTING
        self._add_timeline(incident, "execution_started", {"plan_id": plan.plan_id})

        self.remediator.execute_plan(plan.plan_id)

        self._add_timeline(incident, "execution_complete", {"plan_id": plan.plan_id})

        # Stage 6: Verify
        incident.status = IncidentStatus.VERIFYING
        self._add_timeline(incident, "verification_started", {})

        # Simulate post-remediation metrics (improved)
        post_metrics = self._simulate_post_remediation_metrics(pre_metrics, incident.scenario)

        verification = self.verifier.verify_remediation(
            plan_id=plan.plan_id,
            incident_id=incident.incident_id,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
        )
        incident.verification_report = verification

        self._add_timeline(incident, "verification_complete", {
            "report_id": verification.report_id,
            "result": verification.overall_result.value,
            "rollback_recommended": verification.rollback_recommended,
        })

        # Stage 7: Rollback or resolve
        if verification.rollback_recommended:
            self.remediator.rollback_plan(plan.plan_id, reason="verification_failed")
            incident.status = IncidentStatus.ROLLED_BACK
            self._add_timeline(incident, "rolled_back", {
                "reason": "Verification failed — metrics did not improve",
            })
        else:
            incident.status = IncidentStatus.RESOLVED
            incident.resolved_at = time.time()
            self._add_timeline(incident, "resolved", {
                "duration_seconds": round(incident.resolved_at - incident.created_at, 2),
            })

        return incident

    def approve_incident(self, incident_id: str, approved_by: str = "operator") -> Incident:
        """Manually approve an incident's remediation plan and continue processing."""
        incident = self.incidents.get(incident_id)
        if not incident:
            raise KeyError(f"Unknown incident: {incident_id}")
        if incident.status != IncidentStatus.AWAITING_APPROVAL:
            raise ValueError(f"Incident not awaiting approval: {incident.status.value}")

        plan = incident.remediation_plan
        self.remediator.approve_plan(plan.plan_id, approved_by=approved_by)
        incident.auto_approve = True  # Allow pipeline to continue

        # Re-process from approval point
        return self.process_incident(incident_id)

    def get_incident_timeline(self, incident_id: str) -> list[dict[str, Any]]:
        """Get the full timeline for an incident."""
        incident = self.incidents.get(incident_id)
        if not incident:
            return []
        return incident.timeline

    def get_status(self) -> dict[str, Any]:
        """Get orchestrator status summary."""
        return {
            "agents": {a.name: a.state.value for a in self._agents},
            "incidents": {
                "total": len(self.incidents),
                "by_status": self._count_by_status(),
            },
            "protocol": self.protocol.get_stats(),
        }

    def _build_dag(self, incident_id: str, device_id: str, scenario: str) -> list[DAGNode]:
        """Build the execution DAG for an incident."""
        return [
            DAGNode(
                node_id="detect",
                task_type="detect",
                agent_capability="metric_collection",
                params={"device_id": device_id, "scenario": scenario},
            ),
            DAGNode(
                node_id="diagnose",
                task_type="diagnose",
                agent_capability="root_cause_analysis",
                dependencies=["detect"],
            ),
            DAGNode(
                node_id="plan",
                task_type="generate_plan",
                agent_capability="fix_generation",
                dependencies=["diagnose"],
            ),
            DAGNode(
                node_id="approve",
                task_type="approve",
                agent_capability="change_execution",
                dependencies=["plan"],
            ),
            DAGNode(
                node_id="execute",
                task_type="execute",
                agent_capability="change_execution",
                dependencies=["approve"],
            ),
            DAGNode(
                node_id="verify",
                task_type="verify",
                agent_capability="metric_comparison",
                dependencies=["execute"],
            ),
        ]

    def _simulate_post_remediation_metrics(
        self, pre_metrics: dict[str, float], scenario: str
    ) -> dict[str, float]:
        """Simulate improved metrics after remediation."""
        post = dict(pre_metrics)

        # Remediation improves the problem metrics
        fixes = {
            "cpu_spike": {"cpu_percent": 35.0, "response_time_ms": 150.0},
            "mem_leak": {"memory_percent": 50.0},
            "disk_full": {"disk_percent": 55.0},
            "link_down": {"link_state": 1.0, "network_error_rate": 0.002},
            "bgp_flap": {"bgp_prefixes": 850.0, "network_error_rate": 0.001},
        }

        if scenario in fixes:
            post.update(fixes[scenario])

        return post

    def _add_timeline(
        self, incident: Incident, event: str, details: dict[str, Any]
    ) -> None:
        """Add an event to the incident timeline."""
        incident.timeline.append({
            "timestamp": time.time(),
            "event": event,
            "status": incident.status.value,
            "details": details,
        })

    def _count_by_status(self) -> dict[str, int]:
        """Count incidents by status."""
        counts: dict[str, int] = {}
        for inc in self.incidents.values():
            status = inc.status.value
            counts[status] = counts.get(status, 0) + 1
        return counts
