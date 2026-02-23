"""
Change Approval Gates — HITL (Human-in-the-Loop) approval system.

No remediation action can be executed without passing through an
approval gate. Gates can be configured for:
- Automatic approval (demo/test mode)
- Manual approval via CLI/API
- Time-limited approval windows
- Risk-based auto-approval (low-risk only)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ApprovalPolicy(str, Enum):
    """How approval decisions are made."""
    ALWAYS_REQUIRE = "always_require"  # Human must approve everything
    AUTO_LOW_RISK = "auto_low_risk"    # Auto-approve low risk, require for medium+
    AUTO_ALL = "auto_all"              # Auto-approve everything (demo mode only)


@dataclass
class ApprovalRequest:
    """A request for human approval of a remediation action."""
    request_id: str = field(default_factory=lambda: f"APR-{uuid.uuid4().hex[:8]}")
    plan_id: str = ""
    incident_id: str = ""
    risk_level: str = "medium"
    description: str = ""
    steps_summary: list[str] = field(default_factory=list)
    blast_radius: int = 1
    status: str = "pending"  # pending, approved, rejected, expired
    requested_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    decided_by: str | None = None
    expires_at: float | None = None
    reason: str = ""


class ApprovalGate:
    """
    Human-in-the-Loop approval gate for change management.

    All remediation plans must pass through this gate before execution.
    """

    def __init__(
        self,
        policy: ApprovalPolicy = ApprovalPolicy.ALWAYS_REQUIRE,
        timeout_seconds: int = 3600,
    ) -> None:
        self.policy = policy
        self.timeout_seconds = timeout_seconds
        self.requests: dict[str, ApprovalRequest] = {}

    def request_approval(
        self,
        plan_id: str,
        incident_id: str,
        risk_level: str,
        description: str,
        steps: list[str] | None = None,
        blast_radius: int = 1,
    ) -> ApprovalRequest:
        """Create an approval request."""
        request = ApprovalRequest(
            plan_id=plan_id,
            incident_id=incident_id,
            risk_level=risk_level,
            description=description,
            steps_summary=steps or [],
            blast_radius=blast_radius,
            expires_at=time.time() + self.timeout_seconds,
        )

        # Auto-approve based on policy
        if self.policy == ApprovalPolicy.AUTO_ALL:
            request.status = "approved"
            request.decided_at = time.time()
            request.decided_by = "auto-policy"
        elif self.policy == ApprovalPolicy.AUTO_LOW_RISK and risk_level == "low":
            request.status = "approved"
            request.decided_at = time.time()
            request.decided_by = "auto-policy-low-risk"

        self.requests[request.request_id] = request
        return request

    def approve(self, request_id: str, approved_by: str = "operator") -> ApprovalRequest:
        """Approve a pending request."""
        request = self.requests.get(request_id)
        if not request:
            raise KeyError(f"Unknown request: {request_id}")
        if request.status != "pending":
            raise ValueError(f"Request already {request.status}")

        request.status = "approved"
        request.decided_at = time.time()
        request.decided_by = approved_by
        return request

    def reject(self, request_id: str, rejected_by: str = "operator", reason: str = "") -> ApprovalRequest:
        """Reject a pending request."""
        request = self.requests.get(request_id)
        if not request:
            raise KeyError(f"Unknown request: {request_id}")
        if request.status != "pending":
            raise ValueError(f"Request already {request.status}")

        request.status = "rejected"
        request.decided_at = time.time()
        request.decided_by = rejected_by
        request.reason = reason
        return request

    def get_pending(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        now = time.time()
        pending = []
        for r in self.requests.values():
            if r.status == "pending":
                if r.expires_at and now > r.expires_at:
                    r.status = "expired"
                else:
                    pending.append(r)
        return pending

    def is_approved(self, plan_id: str) -> bool:
        """Check if a plan has been approved."""
        for r in self.requests.values():
            if r.plan_id == plan_id and r.status == "approved":
                return True
        return False

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Get the full approval audit log."""
        return [
            {
                "request_id": r.request_id,
                "plan_id": r.plan_id,
                "risk_level": r.risk_level,
                "status": r.status,
                "decided_by": r.decided_by,
                "decided_at": r.decided_at,
            }
            for r in self.requests.values()
        ]
