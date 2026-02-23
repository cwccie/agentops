"""Tests for observability — tracing, decision logging, metrics."""

import pytest
from agentops.observe.tracer import Tracer


class TestTracer:
    def test_start_trace(self):
        tracer = Tracer()
        span = tracer.start_trace("incident_pipeline")
        assert span.trace_id
        assert span.parent_span_id is None
        assert span.operation_name == "incident_pipeline"

    def test_child_span(self):
        tracer = Tracer()
        root = tracer.start_trace("parent")
        child = tracer.start_span("child_op", root)
        assert child.trace_id == root.trace_id
        assert child.parent_span_id == root.span_id

    def test_finish_span(self):
        tracer = Tracer()
        span = tracer.start_trace("test")
        tracer.finish_span(span)
        assert span.end_time is not None
        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_span_events(self):
        tracer = Tracer()
        span = tracer.start_trace("test")
        span.add_event("checkpoint", {"step": 1})
        assert len(span.events) == 1

    def test_record_decision(self):
        tracer = Tracer()
        record = tracer.record_decision(
            agent_id="agent-1",
            agent_name="TestAgent",
            decision_type="diagnosis",
            input_data={"alerts": 3},
            output_data={"root_cause": "cpu"},
            rationale="High CPU alerts correlated with process table",
            confidence=0.85,
        )
        assert record.decision_id.startswith("DEC-")
        assert record.confidence == 0.85

    def test_record_metric(self):
        tracer = Tracer()
        tracer.record_metric("pipeline_duration", 2.5, "seconds")
        assert len(tracer.metrics) == 1
        assert tracer.metrics[0].value == 2.5

    def test_get_trace(self):
        tracer = Tracer()
        root = tracer.start_trace("pipeline")
        tracer.start_span("step1", root)
        tracer.start_span("step2", root)
        trace = tracer.get_trace(root.trace_id)
        assert len(trace) == 3

    def test_audit_trail(self):
        tracer = Tracer()
        tracer.record_decision("a1", "Agent1", "diag", {}, {}, "test", 0.9)
        tracer.record_decision("a2", "Agent2", "rem", {}, {}, "test", 0.7)
        trail = tracer.get_audit_trail()
        assert len(trail) == 2
        trail_a1 = tracer.get_audit_trail("a1")
        assert len(trail_a1) == 1

    def test_performance_summary(self):
        tracer = Tracer()
        span = tracer.start_trace("test")
        tracer.finish_span(span)
        summary = tracer.get_performance_summary()
        assert summary["total_spans"] == 1
        assert summary["completed_spans"] == 1

    def test_otel_export(self):
        tracer = Tracer()
        tracer.start_trace("test")
        exported = tracer.export_otel_format()
        assert len(exported) == 1
        assert "trace_id" in exported[0]
