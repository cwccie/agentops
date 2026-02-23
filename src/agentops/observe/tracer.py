"""
Observability — OpenTelemetry-compatible tracing and decision logging.

Provides comprehensive observability for all agent actions:
- Distributed tracing with span hierarchy
- Decision logging for audit trail
- Performance metrics collection
- OTel-compatible export format
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Span:
    """An OTel-compatible trace span."""
    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation_name: str
    service_name: str
    start_time: float
    end_time: float | None = None
    status: str = "ok"  # ok, error
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float | None:
        if self.end_time:
            return round((self.end_time - self.start_time) * 1000, 2)
        return None

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })

    def finish(self, status: str = "ok") -> None:
        self.end_time = time.time()
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "service_name": self.service_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }


@dataclass
class DecisionRecord:
    """An auditable record of a decision made by an agent."""
    decision_id: str
    agent_id: str
    agent_name: str
    decision_type: str  # diagnosis, remediation, approval, rollback
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    rationale: str
    timestamp: float = field(default_factory=time.time)
    confidence: float = 0.0
    trace_id: str = ""


@dataclass
class PerformanceMetric:
    """A performance metric observation."""
    metric_name: str
    value: float
    unit: str
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class Tracer:
    """
    Distributed tracing and observability for AgentOps.

    Provides OTel-compatible tracing, decision logging, and
    performance metrics for all agent operations.
    """

    def __init__(self, service_name: str = "agentops") -> None:
        self.service_name = service_name
        self.spans: list[Span] = []
        self.decisions: list[DecisionRecord] = []
        self.metrics: list[PerformanceMetric] = []
        self._active_spans: dict[str, Span] = {}

    def start_trace(self, operation_name: str, attributes: dict[str, Any] | None = None) -> Span:
        """Start a new trace (root span)."""
        trace_id = uuid.uuid4().hex[:32]
        span_id = uuid.uuid4().hex[:16]

        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            operation_name=operation_name,
            service_name=self.service_name,
            start_time=time.time(),
            attributes=attributes or {},
        )

        self._active_spans[span_id] = span
        self.spans.append(span)
        return span

    def start_span(
        self,
        operation_name: str,
        parent: Span,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        """Start a child span within an existing trace."""
        span_id = uuid.uuid4().hex[:16]

        span = Span(
            trace_id=parent.trace_id,
            span_id=span_id,
            parent_span_id=parent.span_id,
            operation_name=operation_name,
            service_name=self.service_name,
            start_time=time.time(),
            attributes=attributes or {},
        )

        self._active_spans[span_id] = span
        self.spans.append(span)
        return span

    def finish_span(self, span: Span, status: str = "ok") -> None:
        """Finish a span."""
        span.finish(status)
        self._active_spans.pop(span.span_id, None)

    def record_decision(
        self,
        agent_id: str,
        agent_name: str,
        decision_type: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        rationale: str,
        confidence: float = 0.0,
        trace_id: str = "",
    ) -> DecisionRecord:
        """Record an auditable decision."""
        record = DecisionRecord(
            decision_id=f"DEC-{uuid.uuid4().hex[:8]}",
            agent_id=agent_id,
            agent_name=agent_name,
            decision_type=decision_type,
            input_data=input_data,
            output_data=output_data,
            rationale=rationale,
            confidence=confidence,
            trace_id=trace_id,
        )
        self.decisions.append(record)
        return record

    def record_metric(
        self,
        name: str,
        value: float,
        unit: str = "",
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a performance metric."""
        metric = PerformanceMetric(
            metric_name=name,
            value=value,
            unit=unit,
            labels=labels or {},
        )
        self.metrics.append(metric)

    def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """Get all spans for a trace."""
        return [s.to_dict() for s in self.spans if s.trace_id == trace_id]

    def get_audit_trail(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        """Get the decision audit trail, optionally filtered by agent."""
        decisions = self.decisions
        if agent_id:
            decisions = [d for d in decisions if d.agent_id == agent_id]
        return [
            {
                "decision_id": d.decision_id,
                "agent_name": d.agent_name,
                "type": d.decision_type,
                "rationale": d.rationale,
                "confidence": d.confidence,
                "timestamp": d.timestamp,
            }
            for d in decisions
        ]

    def get_performance_summary(self) -> dict[str, Any]:
        """Get performance metrics summary."""
        completed_spans = [s for s in self.spans if s.end_time is not None]
        durations = [s.duration_ms for s in completed_spans if s.duration_ms is not None]

        return {
            "total_spans": len(self.spans),
            "completed_spans": len(completed_spans),
            "active_spans": len(self._active_spans),
            "total_decisions": len(self.decisions),
            "total_metrics": len(self.metrics),
            "avg_span_duration_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "max_span_duration_ms": round(max(durations), 2) if durations else 0,
        }

    def export_otel_format(self) -> list[dict[str, Any]]:
        """Export spans in OTel-compatible format."""
        return [s.to_dict() for s in self.spans]
