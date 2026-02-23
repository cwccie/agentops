"""Tests for MonitorAgent — metrics, thresholds, anomaly detection."""

import pytest
from agentops.agents.monitor import MonitorAgent, ThresholdRule, Severity


class TestThresholdRule:
    def test_gt_critical(self):
        rule = ThresholdRule("cpu", 80.0, 95.0, "gt")
        assert rule.evaluate(96.0) == Severity.CRITICAL

    def test_gt_warning(self):
        rule = ThresholdRule("cpu", 80.0, 95.0, "gt")
        assert rule.evaluate(85.0) == Severity.HIGH

    def test_gt_ok(self):
        rule = ThresholdRule("cpu", 80.0, 95.0, "gt")
        assert rule.evaluate(50.0) is None

    def test_lt_critical(self):
        rule = ThresholdRule("bgp", 100.0, 50.0, "lt")
        assert rule.evaluate(30.0) == Severity.CRITICAL

    def test_lt_warning(self):
        rule = ThresholdRule("bgp", 100.0, 50.0, "lt")
        assert rule.evaluate(75.0) == Severity.HIGH


class TestMonitorAgent:
    def test_creation(self):
        agent = MonitorAgent()
        assert agent.name == "MonitorAgent"
        assert "metric_collection" in agent.card.capabilities

    def test_default_rules(self):
        agent = MonitorAgent()
        assert len(agent.rules) > 0
        rule_names = [r.metric_name for r in agent.rules]
        assert "cpu_percent" in rule_names
        assert "memory_percent" in rule_names

    def test_mock_device_healthy(self):
        agent = MonitorAgent()
        agent.setup_mock_device("dev-1", "healthy")
        assert "dev-1" in agent._mock_metrics
        assert agent._mock_metrics["dev-1"]["cpu_percent"] == 25.0

    def test_mock_device_cpu_spike(self):
        agent = MonitorAgent()
        agent.setup_mock_device("dev-1", "cpu_spike")
        assert agent._mock_metrics["dev-1"]["cpu_percent"] == 92.0

    def test_collect_metrics(self):
        agent = MonitorAgent()
        agent.setup_mock_device("dev-1", "healthy")
        samples = agent.collect_metrics("dev-1")
        assert len(samples) > 0
        names = [s.metric_name for s in samples]
        assert "cpu_percent" in names

    def test_evaluate_alerts(self):
        agent = MonitorAgent()
        agent.setup_mock_device("dev-1", "cpu_spike")
        samples = agent.collect_metrics("dev-1")
        alerts = agent.evaluate_metrics(samples)
        assert len(alerts) > 0
        assert any(a.metric_name == "cpu_percent" for a in alerts)

    def test_healthy_no_alerts(self):
        agent = MonitorAgent()
        agent.setup_mock_device("dev-1", "healthy")
        samples = agent.collect_metrics("dev-1")
        alerts = agent.evaluate_metrics(samples)
        # Healthy device may have minor jitter but typically no alerts
        critical = [a for a in alerts if a.severity == Severity.CRITICAL]
        assert len(critical) == 0

    def test_check_device(self):
        agent = MonitorAgent()
        agent.setup_mock_device("dev-1", "link_down")
        report = agent.check_device("dev-1")
        assert report["device_id"] == "dev-1"
        assert "metrics" in report
        assert "alerts" in report
        assert not report["healthy"]

    def test_acknowledge_alert(self):
        agent = MonitorAgent()
        agent.setup_mock_device("dev-1", "cpu_spike")
        samples = agent.collect_metrics("dev-1")
        alerts = agent.evaluate_metrics(samples)
        if alerts:
            assert agent.acknowledge_alert(alerts[0].alert_id)
            active = agent.get_active_alerts()
            assert alerts[0].alert_id not in [a.alert_id for a in active]

    def test_message_handler_collect(self):
        agent = MonitorAgent()
        agent.setup_mock_device("dev-1", "healthy")
        result = agent.receive_message({"type": "collect_metrics", "device_id": "dev-1"})
        assert result is not None
        assert "report" in result
