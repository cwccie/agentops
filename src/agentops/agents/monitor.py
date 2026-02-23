"""
Monitoring Agent — metric collection, threshold evaluation, anomaly detection.

The MonitorAgent continuously evaluates infrastructure metrics against
configured thresholds and anomaly detection rules. When violations are
detected, it creates incident reports and delegates to the diagnosis agent.

Mock infrastructure metrics simulate realistic patterns including:
- Gradual degradation (memory leak, disk fill)
- Sudden spikes (CPU, network)
- Flapping (BGP sessions, link state)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentops.agents.base import BaseAgent


class Severity(str, Enum):
    """Alert severity levels aligned with ITILv4."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ThresholdRule:
    """A threshold-based alerting rule."""
    metric_name: str
    warning_threshold: float
    critical_threshold: float
    comparison: str = "gt"  # gt, lt, eq, ne
    duration_seconds: int = 60
    description: str = ""

    def evaluate(self, value: float) -> Severity | None:
        """Evaluate a metric value against this rule."""
        if self.comparison == "gt":
            if value > self.critical_threshold:
                return Severity.CRITICAL
            if value > self.warning_threshold:
                return Severity.HIGH
        elif self.comparison == "lt":
            if value < self.critical_threshold:
                return Severity.CRITICAL
            if value < self.warning_threshold:
                return Severity.HIGH
        return None


@dataclass
class MetricSample:
    """A single metric measurement."""
    device_id: str
    metric_name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class Alert:
    """A triggered alert from threshold violation or anomaly detection."""
    alert_id: str
    device_id: str
    metric_name: str
    severity: Severity
    current_value: float
    threshold_value: float
    message: str
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False


class MonitorAgent(BaseAgent):
    """
    Infrastructure monitoring agent.

    Collects metrics from registered devices, evaluates thresholds,
    detects anomalies, and creates alerts that trigger the incident
    resolution pipeline.
    """

    def __init__(self) -> None:
        super().__init__(
            name="MonitorAgent",
            description="Collects metrics, evaluates thresholds, detects anomalies",
            capabilities=[
                "metric_collection",
                "threshold_evaluation",
                "anomaly_detection",
                "alert_generation",
            ],
        )
        self.rules: list[ThresholdRule] = []
        self.metric_history: dict[str, list[MetricSample]] = {}
        self.alerts: list[Alert] = []
        self._alert_counter = 0
        self._mock_metrics: dict[str, dict[str, float]] = {}

        # Register message handlers
        self.register_handler("collect_metrics", self._handle_collect_metrics)
        self.register_handler("add_rule", self._handle_add_rule)
        self.register_handler("get_alerts", self._handle_get_alerts)

        # Default threshold rules for common metrics
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Configure default monitoring rules."""
        self.rules = [
            ThresholdRule("cpu_percent", 80.0, 95.0, "gt", 60, "CPU utilization"),
            ThresholdRule("memory_percent", 85.0, 95.0, "gt", 60, "Memory utilization"),
            ThresholdRule("disk_percent", 80.0, 90.0, "gt", 300, "Disk utilization"),
            ThresholdRule("network_error_rate", 0.01, 0.05, "gt", 30, "Network error rate"),
            ThresholdRule("response_time_ms", 500.0, 2000.0, "gt", 30, "API response time"),
            ThresholdRule("bgp_prefixes", 100.0, 50.0, "lt", 10, "BGP received prefixes drop"),
            ThresholdRule("link_state", 1.0, 0.5, "lt", 5, "Link state (1=up, 0=down)"),
        ]

    def setup_mock_device(self, device_id: str, scenario: str = "healthy") -> None:
        """
        Configure mock metrics for a device under a given scenario.

        Scenarios:
          healthy    — all metrics normal
          cpu_spike  — CPU gradually rising to critical
          mem_leak   — memory slowly increasing
          disk_full  — disk approaching capacity
          link_down  — interface going down
          bgp_flap   — BGP session instability
        """
        base_metrics = {
            "cpu_percent": 25.0,
            "memory_percent": 45.0,
            "disk_percent": 40.0,
            "network_error_rate": 0.001,
            "response_time_ms": 120.0,
            "bgp_prefixes": 850.0,
            "link_state": 1.0,
        }

        scenario_overrides = {
            "cpu_spike": {"cpu_percent": 92.0, "response_time_ms": 1800.0},
            "mem_leak": {"memory_percent": 88.0},
            "disk_full": {"disk_percent": 93.0},
            "link_down": {"link_state": 0.0, "network_error_rate": 0.08},
            "bgp_flap": {"bgp_prefixes": 45.0, "network_error_rate": 0.03},
        }

        metrics = {**base_metrics}
        if scenario in scenario_overrides:
            metrics.update(scenario_overrides[scenario])

        self._mock_metrics[device_id] = metrics
        self._log_action("mock_device_setup", {"device_id": device_id, "scenario": scenario})

    def collect_metrics(self, device_id: str) -> list[MetricSample]:
        """
        Collect current metrics from a device.

        Uses mock metrics with realistic jitter for demonstration.
        """
        if device_id not in self._mock_metrics:
            self.setup_mock_device(device_id)

        samples = []
        for metric_name, base_value in self._mock_metrics[device_id].items():
            # Add realistic jitter
            if metric_name == "link_state":
                value = base_value  # binary metric
            else:
                jitter = random.gauss(0, base_value * 0.02)
                value = max(0, base_value + jitter)

            sample = MetricSample(
                device_id=device_id,
                metric_name=metric_name,
                value=round(value, 3),
            )
            samples.append(sample)

            # Store in history
            key = f"{device_id}:{metric_name}"
            if key not in self.metric_history:
                self.metric_history[key] = []
            self.metric_history[key].append(sample)

            # Keep last 1000 samples per metric
            if len(self.metric_history[key]) > 1000:
                self.metric_history[key] = self.metric_history[key][-1000:]

        self._log_action("metrics_collected", {
            "device_id": device_id,
            "sample_count": len(samples),
        })
        return samples

    def evaluate_metrics(self, samples: list[MetricSample]) -> list[Alert]:
        """Evaluate collected metrics against all threshold rules."""
        new_alerts = []

        for sample in samples:
            for rule in self.rules:
                if rule.metric_name != sample.metric_name:
                    continue

                severity = rule.evaluate(sample.value)
                if severity:
                    self._alert_counter += 1
                    alert = Alert(
                        alert_id=f"ALT-{self._alert_counter:06d}",
                        device_id=sample.device_id,
                        metric_name=sample.metric_name,
                        severity=severity,
                        current_value=sample.value,
                        threshold_value=(
                            rule.critical_threshold
                            if severity == Severity.CRITICAL
                            else rule.warning_threshold
                        ),
                        message=(
                            f"{rule.description}: {sample.metric_name}="
                            f"{sample.value:.2f} exceeds threshold "
                            f"{rule.critical_threshold if severity == Severity.CRITICAL else rule.warning_threshold}"
                        ),
                    )
                    new_alerts.append(alert)
                    self.alerts.append(alert)

        if new_alerts:
            self._log_action("alerts_generated", {
                "count": len(new_alerts),
                "severities": [a.severity.value for a in new_alerts],
            })

        return new_alerts

    def detect_anomaly(self, device_id: str, metric_name: str) -> dict[str, Any] | None:
        """
        Simple anomaly detection using rolling statistics.

        Compares current value against the rolling mean +/- 3 standard deviations.
        """
        key = f"{device_id}:{metric_name}"
        history = self.metric_history.get(key, [])

        if len(history) < 10:
            return None

        values = [s.value for s in history[-100:]]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = variance ** 0.5

        if std == 0:
            return None

        current = history[-1].value
        z_score = (current - mean) / std

        if abs(z_score) > 3.0:
            result = {
                "device_id": device_id,
                "metric_name": metric_name,
                "current_value": current,
                "mean": round(mean, 3),
                "std": round(std, 3),
                "z_score": round(z_score, 3),
                "anomaly": True,
                "direction": "high" if z_score > 0 else "low",
            }
            self._log_action("anomaly_detected", result)
            return result

        return None

    def check_device(self, device_id: str) -> dict[str, Any]:
        """
        Full health check: collect metrics, evaluate thresholds, detect anomalies.

        Returns a complete health report for the device.
        """
        samples = self.collect_metrics(device_id)
        alerts = self.evaluate_metrics(samples)
        anomalies = []

        for sample in samples:
            anomaly = self.detect_anomaly(device_id, sample.metric_name)
            if anomaly:
                anomalies.append(anomaly)

        report = {
            "device_id": device_id,
            "timestamp": time.time(),
            "metrics": {s.metric_name: s.value for s in samples},
            "alerts": [
                {
                    "alert_id": a.alert_id,
                    "severity": a.severity.value,
                    "metric": a.metric_name,
                    "value": a.current_value,
                    "message": a.message,
                }
                for a in alerts
            ],
            "anomalies": anomalies,
            "healthy": len(alerts) == 0 and len(anomalies) == 0,
        }

        return report

    def get_active_alerts(self, severity: Severity | None = None) -> list[Alert]:
        """Get all unacknowledged alerts, optionally filtered by severity."""
        alerts = [a for a in self.alerts if not a.acknowledged]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert by ID."""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                self._log_action("alert_acknowledged", {"alert_id": alert_id})
                return True
        return False

    # Message handlers
    def _handle_collect_metrics(self, message: dict[str, Any]) -> dict[str, Any]:
        device_id = message.get("device_id", "unknown")
        report = self.check_device(device_id)
        return {"type": "health_report", "report": report}

    def _handle_add_rule(self, message: dict[str, Any]) -> dict[str, Any]:
        rule = ThresholdRule(**message.get("rule", {}))
        self.rules.append(rule)
        return {"type": "rule_added", "metric": rule.metric_name}

    def _handle_get_alerts(self, message: dict[str, Any]) -> dict[str, Any]:
        severity = message.get("severity")
        if severity:
            severity = Severity(severity)
        alerts = self.get_active_alerts(severity)
        return {
            "type": "alert_list",
            "alerts": [
                {
                    "alert_id": a.alert_id,
                    "severity": a.severity.value,
                    "device_id": a.device_id,
                    "message": a.message,
                }
                for a in alerts
            ],
        }
