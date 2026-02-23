"""
Remediation Agent — fix generation, config change proposals, rollback preparation.

The RemediatorAgent takes diagnosis reports and generates remediation plans.
Every plan includes:
- Pre-flight checks (verify current state)
- Change steps (atomic, ordered operations)
- Rollback plan (automatic if verification fails)
- Blast radius assessment (scope of impact)
- HITL approval gate (human must approve before execution)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentops.agents.base import BaseAgent


class RemediationStatus(str, Enum):
    """Status of a remediation plan."""
    PROPOSED = "proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class RiskLevel(str, Enum):
    """Risk classification for remediation actions."""
    LOW = "low"          # read-only, restart service
    MEDIUM = "medium"    # config change, resource scaling
    HIGH = "high"        # network change, data migration
    CRITICAL = "critical"  # destructive, multi-device


@dataclass
class RemediationStep:
    """A single atomic remediation step."""
    step_id: str
    order: int
    action: str
    target: str  # device_id or resource
    params: dict[str, Any] = field(default_factory=dict)
    rollback_action: str = ""
    rollback_params: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300
    requires_approval: bool = False
    executed: bool = False
    result: str = ""


@dataclass
class RemediationPlan:
    """Complete remediation plan with steps, rollback, and approval."""
    plan_id: str
    incident_id: str
    diagnosis_report_id: str
    description: str
    risk_level: RiskLevel
    status: RemediationStatus
    steps: list[RemediationStep] = field(default_factory=list)
    pre_flight_checks: list[dict[str, Any]] = field(default_factory=list)
    blast_radius: dict[str, Any] = field(default_factory=dict)
    estimated_duration_seconds: int = 0
    created_at: float = field(default_factory=time.time)
    approved_at: float | None = None
    approved_by: str | None = None
    executed_at: float | None = None
    completed_at: float | None = None
    rollback_triggered: bool = False


# Remediation templates for each incident type
REMEDIATION_TEMPLATES: dict[str, dict[str, Any]] = {
    "cpu_spike": {
        "description": "Mitigate CPU spike via process management and resource limits",
        "risk_level": "medium",
        "steps": [
            {
                "action": "identify_top_processes",
                "description": "List top CPU consumers",
                "rollback": "none",
            },
            {
                "action": "apply_cpu_limit",
                "description": "Apply cgroup CPU limit to runaway process",
                "rollback": "remove_cpu_limit",
            },
            {
                "action": "restart_service",
                "description": "Gracefully restart affected service if limit insufficient",
                "rollback": "start_service",
            },
        ],
    },
    "memory_leak": {
        "description": "Address memory leak via graceful restart and limit enforcement",
        "risk_level": "medium",
        "steps": [
            {
                "action": "capture_heap_dump",
                "description": "Capture memory profile for post-mortem",
                "rollback": "none",
            },
            {
                "action": "set_memory_limit",
                "description": "Apply OOM score adjustment and memory cgroup limit",
                "rollback": "remove_memory_limit",
            },
            {
                "action": "graceful_restart",
                "description": "Rolling restart of affected service",
                "rollback": "none",
            },
        ],
    },
    "disk_full": {
        "description": "Reclaim disk space via log rotation and temp cleanup",
        "risk_level": "low",
        "steps": [
            {
                "action": "analyze_disk_usage",
                "description": "Identify largest files and directories",
                "rollback": "none",
            },
            {
                "action": "rotate_logs",
                "description": "Force log rotation and compress old logs",
                "rollback": "none",
            },
            {
                "action": "clean_temp_files",
                "description": "Remove temporary files older than 7 days",
                "rollback": "none",
            },
            {
                "action": "expand_volume",
                "description": "Expand logical volume if available",
                "rollback": "shrink_volume",
            },
        ],
    },
    "link_down": {
        "description": "Restore network link via interface reset and failover",
        "risk_level": "high",
        "steps": [
            {
                "action": "check_physical_layer",
                "description": "Verify cable, SFP, and port status",
                "rollback": "none",
            },
            {
                "action": "bounce_interface",
                "description": "Administratively bounce the interface",
                "rollback": "shutdown_interface",
            },
            {
                "action": "activate_failover",
                "description": "Activate backup path if available",
                "rollback": "deactivate_failover",
            },
            {
                "action": "verify_connectivity",
                "description": "Verify end-to-end connectivity restored",
                "rollback": "none",
            },
        ],
    },
    "bgp_flap": {
        "description": "Stabilize BGP session via soft reset and route dampening",
        "risk_level": "high",
        "steps": [
            {
                "action": "check_bgp_neighbors",
                "description": "Review BGP neighbor state and received prefixes",
                "rollback": "none",
            },
            {
                "action": "soft_reset_bgp",
                "description": "Perform BGP soft-reconfiguration inbound",
                "rollback": "none",
            },
            {
                "action": "apply_route_dampening",
                "description": "Enable route dampening to suppress flapping",
                "rollback": "remove_route_dampening",
            },
            {
                "action": "verify_route_table",
                "description": "Verify expected prefixes are received and installed",
                "rollback": "none",
            },
        ],
    },
}


class RemediatorAgent(BaseAgent):
    """
    Remediation agent that generates, manages, and executes fix plans.

    Key principles:
    - Every change is reversible (rollback plan required)
    - Human approval required before execution (HITL gate)
    - Blast radius is assessed and bounded
    - All actions are logged for audit
    """

    def __init__(self) -> None:
        super().__init__(
            name="RemediatorAgent",
            description="Generates remediation plans with rollback and HITL approval",
            capabilities=[
                "fix_generation",
                "config_change_proposal",
                "rollback_preparation",
                "blast_radius_assessment",
                "change_execution",
            ],
        )
        self.plans: dict[str, RemediationPlan] = {}
        self._max_blast_radius = 10  # Safety limit

        self.register_handler("generate_plan", self._handle_generate_plan)
        self.register_handler("approve_plan", self._handle_approve_plan)
        self.register_handler("execute_plan", self._handle_execute_plan)
        self.register_handler("rollback_plan", self._handle_rollback_plan)

    def generate_plan(
        self,
        incident_id: str,
        diagnosis_report_id: str,
        incident_type: str,
        device_id: str,
        blast_radius: int = 1,
    ) -> RemediationPlan:
        """
        Generate a remediation plan based on the diagnosis.

        Returns a plan in PROPOSED status, requiring approval before execution.
        """
        task_id = self.create_task("generate_plan", {
            "incident_id": incident_id,
            "incident_type": incident_type,
        })

        template = REMEDIATION_TEMPLATES.get(incident_type, {
            "description": f"Manual remediation required for {incident_type}",
            "risk_level": "high",
            "steps": [{"action": "escalate", "description": "Escalate to on-call", "rollback": "none"}],
        })

        risk_level = RiskLevel(template["risk_level"])

        # Build ordered remediation steps
        steps = []
        for i, step_tmpl in enumerate(template["steps"]):
            step = RemediationStep(
                step_id=f"STEP-{uuid.uuid4().hex[:6]}",
                order=i + 1,
                action=step_tmpl["action"],
                target=device_id,
                params={"description": step_tmpl["description"]},
                rollback_action=step_tmpl.get("rollback", "none"),
                requires_approval=(risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) and i == 0),
            )
            steps.append(step)

        # Assess blast radius
        blast = {
            "estimated_devices": blast_radius,
            "risk_level": risk_level.value,
            "within_limits": blast_radius <= self._max_blast_radius,
            "max_allowed": self._max_blast_radius,
        }

        plan = RemediationPlan(
            plan_id=f"REM-{uuid.uuid4().hex[:8]}",
            incident_id=incident_id,
            diagnosis_report_id=diagnosis_report_id,
            description=template["description"],
            risk_level=risk_level,
            status=RemediationStatus.AWAITING_APPROVAL,
            steps=steps,
            pre_flight_checks=[
                {"check": "device_reachable", "target": device_id},
                {"check": "maintenance_window", "target": device_id},
                {"check": "blast_radius_acceptable", "limit": self._max_blast_radius},
            ],
            blast_radius=blast,
            estimated_duration_seconds=len(steps) * 60,
        )

        # Reject if blast radius exceeds limits
        if blast_radius > self._max_blast_radius:
            plan.status = RemediationStatus.REJECTED
            self._log_action("plan_rejected_blast_radius", {
                "plan_id": plan.plan_id,
                "blast_radius": blast_radius,
                "limit": self._max_blast_radius,
            })

        self.plans[plan.plan_id] = plan
        self.complete_task(task_id, {"plan_id": plan.plan_id, "status": plan.status.value})

        self._log_action("plan_generated", {
            "plan_id": plan.plan_id,
            "incident_type": incident_type,
            "risk_level": risk_level.value,
            "step_count": len(steps),
        })

        return plan

    def approve_plan(self, plan_id: str, approved_by: str = "operator") -> RemediationPlan:
        """Approve a remediation plan for execution (HITL gate)."""
        plan = self.plans.get(plan_id)
        if not plan:
            raise KeyError(f"Unknown plan: {plan_id}")
        if plan.status != RemediationStatus.AWAITING_APPROVAL:
            raise ValueError(f"Plan {plan_id} is not awaiting approval (status: {plan.status.value})")

        plan.status = RemediationStatus.APPROVED
        plan.approved_at = time.time()
        plan.approved_by = approved_by

        self._log_action("plan_approved", {
            "plan_id": plan_id,
            "approved_by": approved_by,
        })

        return plan

    def reject_plan(self, plan_id: str, reason: str = "") -> RemediationPlan:
        """Reject a remediation plan."""
        plan = self.plans.get(plan_id)
        if not plan:
            raise KeyError(f"Unknown plan: {plan_id}")

        plan.status = RemediationStatus.REJECTED
        self._log_action("plan_rejected", {"plan_id": plan_id, "reason": reason})
        return plan

    def execute_plan(self, plan_id: str) -> RemediationPlan:
        """
        Execute an approved remediation plan.

        Simulates step-by-step execution with success/failure outcomes.
        All steps are logged for audit trail.
        """
        plan = self.plans.get(plan_id)
        if not plan:
            raise KeyError(f"Unknown plan: {plan_id}")
        if plan.status != RemediationStatus.APPROVED:
            raise ValueError(f"Plan {plan_id} not approved (status: {plan.status.value})")

        plan.status = RemediationStatus.EXECUTING
        plan.executed_at = time.time()

        task_id = self.create_task("execute_plan", {"plan_id": plan_id})

        for step in plan.steps:
            self._log_action("step_executing", {
                "plan_id": plan_id,
                "step_id": step.step_id,
                "action": step.action,
            })

            # Simulate execution (all steps succeed in mock mode)
            step.executed = True
            step.result = f"Simulated: {step.action} on {step.target} — SUCCESS"

            self._log_action("step_completed", {
                "plan_id": plan_id,
                "step_id": step.step_id,
                "result": step.result,
            })

        plan.status = RemediationStatus.COMPLETED
        plan.completed_at = time.time()

        self.complete_task(task_id, {"plan_id": plan_id, "status": "completed"})
        self._log_action("plan_executed", {
            "plan_id": plan_id,
            "duration": plan.completed_at - plan.executed_at,
        })

        return plan

    def rollback_plan(self, plan_id: str, reason: str = "verification_failed") -> RemediationPlan:
        """
        Roll back an executed remediation plan.

        Executes rollback actions in reverse order for all completed steps.
        """
        plan = self.plans.get(plan_id)
        if not plan:
            raise KeyError(f"Unknown plan: {plan_id}")

        plan.rollback_triggered = True

        # Execute rollback steps in reverse
        for step in reversed(plan.steps):
            if step.executed and step.rollback_action != "none":
                self._log_action("rollback_step", {
                    "plan_id": plan_id,
                    "step_id": step.step_id,
                    "rollback_action": step.rollback_action,
                })
                step.result = f"ROLLED BACK: {step.rollback_action}"

        plan.status = RemediationStatus.ROLLED_BACK
        self._log_action("plan_rolled_back", {
            "plan_id": plan_id,
            "reason": reason,
        })

        return plan

    def get_plan(self, plan_id: str) -> RemediationPlan | None:
        """Get a plan by ID."""
        return self.plans.get(plan_id)

    def get_pending_approvals(self) -> list[RemediationPlan]:
        """Get all plans awaiting approval."""
        return [p for p in self.plans.values() if p.status == RemediationStatus.AWAITING_APPROVAL]

    def get_plan_summary(self, plan_id: str) -> dict[str, Any]:
        """Get a human-readable plan summary."""
        plan = self.plans.get(plan_id)
        if not plan:
            return {"error": f"Unknown plan: {plan_id}"}

        return {
            "plan_id": plan.plan_id,
            "incident_id": plan.incident_id,
            "description": plan.description,
            "risk_level": plan.risk_level.value,
            "status": plan.status.value,
            "steps": [
                {
                    "order": s.order,
                    "action": s.action,
                    "target": s.target,
                    "description": s.params.get("description", ""),
                    "rollback": s.rollback_action,
                    "executed": s.executed,
                }
                for s in plan.steps
            ],
            "blast_radius": plan.blast_radius,
            "estimated_duration": f"{plan.estimated_duration_seconds}s",
            "approved_by": plan.approved_by,
        }

    # Message handlers
    def _handle_generate_plan(self, message: dict[str, Any]) -> dict[str, Any]:
        plan = self.generate_plan(
            incident_id=message.get("incident_id", "unknown"),
            diagnosis_report_id=message.get("diagnosis_report_id", "unknown"),
            incident_type=message.get("incident_type", "unknown"),
            device_id=message.get("device_id", "unknown"),
            blast_radius=message.get("blast_radius", 1),
        )
        return {"type": "plan_generated", "plan_id": plan.plan_id, "status": plan.status.value}

    def _handle_approve_plan(self, message: dict[str, Any]) -> dict[str, Any]:
        plan = self.approve_plan(
            plan_id=message["plan_id"],
            approved_by=message.get("approved_by", "operator"),
        )
        return {"type": "plan_approved", "plan_id": plan.plan_id}

    def _handle_execute_plan(self, message: dict[str, Any]) -> dict[str, Any]:
        plan = self.execute_plan(plan_id=message["plan_id"])
        return {"type": "plan_executed", "plan_id": plan.plan_id, "status": plan.status.value}

    def _handle_rollback_plan(self, message: dict[str, Any]) -> dict[str, Any]:
        plan = self.rollback_plan(
            plan_id=message["plan_id"],
            reason=message.get("reason", "manual_rollback"),
        )
        return {"type": "plan_rolled_back", "plan_id": plan.plan_id}
