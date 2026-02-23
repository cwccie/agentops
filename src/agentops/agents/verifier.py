"""
Verification Agent — post-fix validation, metric comparison, SLA check.

After remediation is executed, the VerifierAgent confirms the fix worked:
1. Collects post-remediation metrics
2. Compares against pre-incident baselines
3. Validates SLA compliance
4. Triggers automatic rollback if verification fails
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentops.agents.base import BaseAgent


class VerificationResult(str, Enum):
    """Outcome of a verification check."""
    PASSED = "passed"
    FAILED = "failed"
    DEGRADED = "degraded"  # improved but not fully recovered
    PENDING = "pending"
    TIMED_OUT = "timed_out"


@dataclass
class SLATarget:
    """An SLA target for a metric."""
    metric_name: str
    target_value: float
    comparison: str = "lt"  # lt = value must be less than target
    description: str = ""


@dataclass
class VerificationCheck:
    """A single verification check result."""
    check_id: str
    check_type: str  # metric_comparison, sla_check, connectivity, custom
    description: str
    result: VerificationResult
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class VerificationReport:
    """Complete verification report for a remediation."""
    report_id: str
    plan_id: str
    incident_id: str
    timestamp: float
    overall_result: VerificationResult
    checks: list[VerificationCheck]
    pre_metrics: dict[str, float]
    post_metrics: dict[str, float]
    improvement: dict[str, float]  # metric_name -> percent improvement
    sla_compliance: dict[str, bool]
    duration_seconds: float
    rollback_recommended: bool


# Default SLA targets
DEFAULT_SLAS = [
    SLATarget("cpu_percent", 80.0, "lt", "CPU must be below 80%"),
    SLATarget("memory_percent", 85.0, "lt", "Memory must be below 85%"),
    SLATarget("disk_percent", 85.0, "lt", "Disk must be below 85%"),
    SLATarget("response_time_ms", 500.0, "lt", "Response time must be below 500ms"),
    SLATarget("network_error_rate", 0.01, "lt", "Error rate must be below 1%"),
    SLATarget("link_state", 1.0, "eq", "Link must be up"),
    SLATarget("bgp_prefixes", 100.0, "gt", "Must receive at least 100 BGP prefixes"),
]


class VerifierAgent(BaseAgent):
    """
    Post-remediation verification agent.

    Validates that remediation actually fixed the problem by comparing
    metrics against baselines and SLA targets. Recommends rollback if
    the fix didn't improve things within the configured window.
    """

    def __init__(self, verification_window_seconds: int = 300) -> None:
        super().__init__(
            name="VerifierAgent",
            description="Post-fix validation, metric comparison, and SLA compliance",
            capabilities=[
                "metric_comparison",
                "sla_validation",
                "rollback_recommendation",
                "improvement_scoring",
            ],
        )
        self.sla_targets = list(DEFAULT_SLAS)
        self.verification_window = verification_window_seconds
        self.reports: list[VerificationReport] = []

        self.register_handler("verify", self._handle_verify)
        self.register_handler("set_sla", self._handle_set_sla)

    def verify_remediation(
        self,
        plan_id: str,
        incident_id: str,
        pre_metrics: dict[str, float],
        post_metrics: dict[str, float],
    ) -> VerificationReport:
        """
        Verify that a remediation was successful.

        Compares pre/post metrics, checks SLA compliance, and determines
        whether the fix should be kept or rolled back.
        """
        start_time = time.time()
        task_id = self.create_task("verification", {
            "plan_id": plan_id,
            "incident_id": incident_id,
        })

        checks = []

        # 1. Metric comparison checks
        improvement = {}
        for metric_name in pre_metrics:
            if metric_name in post_metrics:
                pre_val = pre_metrics[metric_name]
                post_val = post_metrics[metric_name]

                if pre_val != 0:
                    pct_change = ((post_val - pre_val) / abs(pre_val)) * 100
                else:
                    pct_change = 0.0

                improvement[metric_name] = round(pct_change, 2)

                # Determine if this metric improved
                # For most metrics, lower is better (cpu, mem, disk, errors, latency)
                # For link_state and bgp_prefixes, higher is better
                higher_is_better = metric_name in ("link_state", "bgp_prefixes")

                if higher_is_better:
                    improved = post_val >= pre_val
                else:
                    improved = post_val <= pre_val

                result = VerificationResult.PASSED if improved else VerificationResult.FAILED

                checks.append(VerificationCheck(
                    check_id=f"CHK-{uuid.uuid4().hex[:6]}",
                    check_type="metric_comparison",
                    description=f"{metric_name}: {pre_val:.2f} -> {post_val:.2f} ({pct_change:+.1f}%)",
                    result=result,
                    details={
                        "metric": metric_name,
                        "pre_value": pre_val,
                        "post_value": post_val,
                        "percent_change": pct_change,
                        "improved": improved,
                    },
                ))

        # 2. SLA compliance checks
        sla_compliance = {}
        for sla in self.sla_targets:
            if sla.metric_name in post_metrics:
                post_val = post_metrics[sla.metric_name]
                if sla.comparison == "lt":
                    compliant = post_val < sla.target_value
                elif sla.comparison == "gt":
                    compliant = post_val > sla.target_value
                elif sla.comparison == "eq":
                    compliant = abs(post_val - sla.target_value) < 0.01
                else:
                    compliant = True

                sla_compliance[sla.metric_name] = compliant

                checks.append(VerificationCheck(
                    check_id=f"CHK-{uuid.uuid4().hex[:6]}",
                    check_type="sla_check",
                    description=f"SLA: {sla.description} — {'PASS' if compliant else 'FAIL'}",
                    result=VerificationResult.PASSED if compliant else VerificationResult.FAILED,
                    details={
                        "sla_metric": sla.metric_name,
                        "target": sla.target_value,
                        "actual": post_val,
                        "compliant": compliant,
                    },
                ))

        # 3. Determine overall result
        failed_checks = [c for c in checks if c.result == VerificationResult.FAILED]
        failed_slas = [m for m, compliant in sla_compliance.items() if not compliant]

        if len(failed_checks) == 0:
            overall_result = VerificationResult.PASSED
        elif len(failed_checks) <= len(checks) // 3:
            overall_result = VerificationResult.DEGRADED
        else:
            overall_result = VerificationResult.FAILED

        rollback_recommended = overall_result == VerificationResult.FAILED

        duration = time.time() - start_time

        report = VerificationReport(
            report_id=f"VER-{uuid.uuid4().hex[:8]}",
            plan_id=plan_id,
            incident_id=incident_id,
            timestamp=time.time(),
            overall_result=overall_result,
            checks=checks,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
            improvement=improvement,
            sla_compliance=sla_compliance,
            duration_seconds=round(duration, 3),
            rollback_recommended=rollback_recommended,
        )

        self.reports.append(report)

        self.complete_task(task_id, {
            "report_id": report.report_id,
            "result": overall_result.value,
            "rollback_recommended": rollback_recommended,
        })

        self._log_action("verification_complete", {
            "report_id": report.report_id,
            "result": overall_result.value,
            "checks_passed": len(checks) - len(failed_checks),
            "checks_failed": len(failed_checks),
            "sla_failures": failed_slas,
            "rollback_recommended": rollback_recommended,
        })

        return report

    def get_verification_summary(self, report_id: str) -> dict[str, Any]:
        """Get human-readable verification summary."""
        for report in self.reports:
            if report.report_id == report_id:
                return {
                    "report_id": report.report_id,
                    "plan_id": report.plan_id,
                    "overall_result": report.overall_result.value,
                    "checks": [
                        {
                            "type": c.check_type,
                            "description": c.description,
                            "result": c.result.value,
                        }
                        for c in report.checks
                    ],
                    "improvement": report.improvement,
                    "sla_compliance": report.sla_compliance,
                    "rollback_recommended": report.rollback_recommended,
                }
        return {"error": f"Report {report_id} not found"}

    # Message handlers
    def _handle_verify(self, message: dict[str, Any]) -> dict[str, Any]:
        report = self.verify_remediation(
            plan_id=message.get("plan_id", "unknown"),
            incident_id=message.get("incident_id", "unknown"),
            pre_metrics=message.get("pre_metrics", {}),
            post_metrics=message.get("post_metrics", {}),
        )
        return {
            "type": "verification_report",
            "report_id": report.report_id,
            "result": report.overall_result.value,
            "rollback_recommended": report.rollback_recommended,
        }

    def _handle_set_sla(self, message: dict[str, Any]) -> dict[str, Any]:
        sla = SLATarget(**message.get("sla", {}))
        self.sla_targets.append(sla)
        return {"type": "sla_added", "metric": sla.metric_name}
