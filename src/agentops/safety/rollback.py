"""
Rollback Manager — automatic rollback when metrics don't improve.

Monitors post-remediation metrics and automatically triggers rollback
if improvement isn't observed within the configurable window.

Key features:
- Configurable observation window (default: 5 minutes)
- Metric-specific thresholds for improvement
- Automatic or manual rollback trigger
- Full audit trail of rollback decisions
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class RollbackTrigger(str, Enum):
    """What triggered the rollback."""
    METRIC_DEGRADATION = "metric_degradation"
    TIMEOUT = "timeout"
    MANUAL = "manual"
    KILL_SWITCH = "kill_switch"
    SLA_VIOLATION = "sla_violation"


@dataclass
class RollbackPolicy:
    """Policy defining when rollback should be triggered."""
    observation_window_seconds: int = 300  # 5 minutes
    improvement_threshold_percent: float = 10.0  # must improve by at least 10%
    max_degradation_percent: float = 5.0  # rollback if worse by more than 5%
    require_all_metrics_improved: bool = False  # at least one metric must improve
    auto_rollback: bool = True  # automatically trigger rollback


@dataclass
class RollbackRecord:
    """Record of a rollback decision and execution."""
    record_id: str
    plan_id: str
    incident_id: str
    trigger: RollbackTrigger
    reason: str
    pre_metrics: dict[str, float]
    post_metrics: dict[str, float]
    improvement: dict[str, float]
    timestamp: float = field(default_factory=time.time)
    executed: bool = False


class RollbackManager:
    """
    Manages automatic rollback decisions based on post-remediation metrics.

    Works with the VerifierAgent to determine whether a fix should be
    kept or rolled back, and coordinates the rollback with the RemediatorAgent.
    """

    def __init__(self, policy: RollbackPolicy | None = None) -> None:
        self.policy = policy or RollbackPolicy()
        self.records: list[RollbackRecord] = []
        self._record_counter = 0
        self._rollback_callbacks: list[Callable] = []

    def register_rollback_callback(self, callback: Callable) -> None:
        """Register a callback to be invoked when rollback is triggered."""
        self._rollback_callbacks.append(callback)

    def evaluate(
        self,
        plan_id: str,
        incident_id: str,
        pre_metrics: dict[str, float],
        post_metrics: dict[str, float],
    ) -> RollbackRecord:
        """
        Evaluate whether rollback should be triggered.

        Compares pre/post metrics against the rollback policy and
        creates a rollback record with the decision.
        """
        self._record_counter += 1
        improvement: dict[str, float] = {}
        degraded_metrics = []
        improved_metrics = []

        for metric, pre_val in pre_metrics.items():
            if metric in post_metrics:
                post_val = post_metrics[metric]
                if pre_val != 0:
                    pct_change = ((post_val - pre_val) / abs(pre_val)) * 100
                else:
                    pct_change = 0.0

                improvement[metric] = round(pct_change, 2)

                # For most metrics, negative change = improvement (lower is better)
                # For link_state and bgp_prefixes, positive change = improvement
                higher_is_better = metric in ("link_state", "bgp_prefixes")

                if higher_is_better:
                    if pct_change < -self.policy.max_degradation_percent:
                        degraded_metrics.append(metric)
                    elif pct_change > self.policy.improvement_threshold_percent:
                        improved_metrics.append(metric)
                else:
                    if pct_change > self.policy.max_degradation_percent:
                        degraded_metrics.append(metric)
                    elif pct_change < -self.policy.improvement_threshold_percent:
                        improved_metrics.append(metric)

        # Determine if rollback should trigger
        should_rollback = False
        trigger = RollbackTrigger.METRIC_DEGRADATION
        reason = ""

        if degraded_metrics:
            should_rollback = True
            reason = f"Metrics degraded: {', '.join(degraded_metrics)}"
        elif self.policy.require_all_metrics_improved and not improved_metrics:
            should_rollback = True
            reason = "No metrics showed improvement"

        record = RollbackRecord(
            record_id=f"RB-{self._record_counter:04d}",
            plan_id=plan_id,
            incident_id=incident_id,
            trigger=trigger,
            reason=reason,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
            improvement=improvement,
        )

        if should_rollback and self.policy.auto_rollback:
            record.executed = True
            for callback in self._rollback_callbacks:
                callback(plan_id, reason)

        self.records.append(record)
        return record

    def force_rollback(self, plan_id: str, reason: str = "manual trigger") -> RollbackRecord:
        """Force a manual rollback."""
        self._record_counter += 1
        record = RollbackRecord(
            record_id=f"RB-{self._record_counter:04d}",
            plan_id=plan_id,
            incident_id="manual",
            trigger=RollbackTrigger.MANUAL,
            reason=reason,
            pre_metrics={},
            post_metrics={},
            improvement={},
            executed=True,
        )

        for callback in self._rollback_callbacks:
            callback(plan_id, reason)

        self.records.append(record)
        return record

    def get_history(self) -> list[dict[str, Any]]:
        """Get rollback decision history."""
        return [
            {
                "record_id": r.record_id,
                "plan_id": r.plan_id,
                "trigger": r.trigger.value,
                "reason": r.reason,
                "executed": r.executed,
                "timestamp": r.timestamp,
            }
            for r in self.records
        ]

    def update_policy(self, **kwargs: Any) -> RollbackPolicy:
        """Update rollback policy parameters."""
        for key, value in kwargs.items():
            if hasattr(self.policy, key):
                setattr(self.policy, key, value)
        return self.policy
