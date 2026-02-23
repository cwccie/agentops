"""
Web Dashboard — Flask application for the AgentOps management interface.

Provides:
- Real-time agent status overview
- Active incident tracking
- Approval queue management
- Remediation timeline visualization
- Observability and audit trail views
"""

from __future__ import annotations

import time
from typing import Any

from flask import Flask, render_template_string, jsonify, request

from agentops.orchestrator.engine import Orchestrator, IncidentStatus

# Dashboard HTML template (embedded for single-file deployment)
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AgentOps Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; }
        .header { background: linear-gradient(135deg, #1e293b, #0f172a); padding: 20px 40px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }
        .header h1 { font-size: 24px; color: #38bdf8; }
        .header .badge { background: #22c55e; color: #fff; padding: 4px 12px; border-radius: 12px; font-size: 12px; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px 40px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 24px; }
        .card h2 { color: #38bdf8; font-size: 16px; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }
        .stat-value { font-size: 36px; font-weight: bold; color: #f8fafc; }
        .stat-label { font-size: 14px; color: #94a3b8; margin-top: 4px; }
        .agent-list { list-style: none; }
        .agent-list li { padding: 10px 0; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }
        .agent-list li:last-child { border: none; }
        .status-active { color: #22c55e; }
        .status-paused { color: #f59e0b; }
        .status-stopped { color: #ef4444; }
        .incident-row { padding: 12px 0; border-bottom: 1px solid #334155; }
        .incident-row .id { color: #38bdf8; font-weight: bold; }
        .incident-row .status { padding: 2px 8px; border-radius: 4px; font-size: 12px; display: inline-block; }
        .status-resolved { background: #166534; color: #86efac; }
        .status-detecting { background: #854d0e; color: #fde68a; }
        .status-awaiting { background: #9f1239; color: #fda4af; }
        .timeline { list-style: none; padding-left: 20px; border-left: 2px solid #334155; }
        .timeline li { padding: 8px 0 8px 16px; position: relative; }
        .timeline li::before { content: ''; position: absolute; left: -7px; top: 12px; width: 12px; height: 12px; background: #38bdf8; border-radius: 50%; }
        .btn { background: #38bdf8; color: #0f172a; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; text-decoration: none; }
        .btn:hover { background: #7dd3fc; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-danger:hover { background: #f87171; }
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 10px; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; font-weight: 600; text-transform: uppercase; font-size: 12px; }
        .refresh-note { color: #64748b; font-size: 12px; margin-top: 20px; text-align: center; }
    </style>
</head>
<body>
    <div class="header">
        <h1>AgentOps</h1>
        <div>
            <span class="badge">{{ agent_count }} Agents Active</span>
        </div>
    </div>
    <div class="container">
        <div class="grid">
            <div class="card">
                <h2>Incidents</h2>
                <div class="stat-value">{{ total_incidents }}</div>
                <div class="stat-label">Total Tracked</div>
            </div>
            <div class="card">
                <h2>Resolved</h2>
                <div class="stat-value" style="color: #22c55e;">{{ resolved_count }}</div>
                <div class="stat-label">Successfully Fixed</div>
            </div>
            <div class="card">
                <h2>Pending Approval</h2>
                <div class="stat-value" style="color: #f59e0b;">{{ pending_count }}</div>
                <div class="stat-label">Awaiting Human Review</div>
            </div>
            <div class="card">
                <h2>Rolled Back</h2>
                <div class="stat-value" style="color: #ef4444;">{{ rollback_count }}</div>
                <div class="stat-label">Safety Rollbacks</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h2>Agent Status</h2>
                <ul class="agent-list">
                    {% for agent in agents %}
                    <li>
                        <span>{{ agent.name }}</span>
                        <span class="status-{{ agent.state }}">{{ agent.state }}</span>
                    </li>
                    {% endfor %}
                </ul>
            </div>
            <div class="card">
                <h2>Recent Incidents</h2>
                {% for inc in incidents %}
                <div class="incident-row">
                    <span class="id">{{ inc.incident_id }}</span>
                    <span class="status status-{{ inc.status_class }}">{{ inc.status }}</span>
                    <div style="color: #94a3b8; font-size: 13px; margin-top: 4px;">
                        {{ inc.device_id }} — {{ inc.description[:60] }}
                    </div>
                </div>
                {% endfor %}
                {% if not incidents %}
                <div style="color: #64748b; padding: 20px 0;">No incidents yet. Use CLI to simulate one.</div>
                {% endif %}
            </div>
        </div>

        <div class="card" style="margin-bottom: 30px;">
            <h2>Audit Trail (Recent)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Agent</th>
                        <th>Action</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    {% for entry in audit_log %}
                    <tr>
                        <td>{{ entry.agent_name }}</td>
                        <td>{{ entry.action }}</td>
                        <td style="color: #94a3b8;">{{ entry.details_str }}</td>
                    </tr>
                    {% endfor %}
                    {% if not audit_log %}
                    <tr><td colspan="3" style="color: #64748b;">No audit entries yet.</td></tr>
                    {% endif %}
                </tbody>
            </table>
        </div>

        <p class="refresh-note">Refresh page to update. AgentOps v0.1.0 | Safety-First Multi-Agent Infrastructure Remediation</p>
    </div>
</body>
</html>
"""

# Module-level orchestrator
_dashboard_orchestrator: Orchestrator | None = None


def create_dashboard_app(auto_approve: bool = False) -> Flask:
    """Create the dashboard Flask application."""
    global _dashboard_orchestrator

    app = Flask(__name__)
    _dashboard_orchestrator = Orchestrator(auto_approve=auto_approve)

    @app.route("/")
    def index():
        orch = _dashboard_orchestrator

        agents = [
            {"name": a.name, "state": a.state.value}
            for a in orch._agents
        ]

        incidents = []
        for inc in list(orch.incidents.values())[-10:]:
            status_class = "detecting"
            if inc.status == IncidentStatus.RESOLVED:
                status_class = "resolved"
            elif inc.status == IncidentStatus.AWAITING_APPROVAL:
                status_class = "awaiting"
            incidents.append({
                "incident_id": inc.incident_id,
                "device_id": inc.device_id,
                "description": inc.description,
                "status": inc.status.value,
                "status_class": status_class,
            })

        audit_log = []
        for agent in orch._agents:
            for entry in agent.get_action_log()[-10:]:
                details = entry.get("details", {})
                details_str = ", ".join(f"{k}={v}" for k, v in list(details.items())[:3])
                audit_log.append({
                    "agent_name": entry.get("agent_name", ""),
                    "action": entry.get("action", ""),
                    "details_str": details_str[:80],
                })
        audit_log = audit_log[-20:]

        status_counts = orch._count_by_status()

        return render_template_string(
            DASHBOARD_HTML,
            agent_count=len(agents),
            total_incidents=len(orch.incidents),
            resolved_count=status_counts.get("resolved", 0),
            pending_count=status_counts.get("awaiting_approval", 0),
            rollback_count=status_counts.get("rolled_back", 0),
            agents=agents,
            incidents=incidents,
            audit_log=audit_log,
        )

    @app.route("/api/status")
    def api_status():
        return jsonify(_dashboard_orchestrator.get_status())

    return app


def get_dashboard_orchestrator() -> Orchestrator | None:
    """Get the dashboard's orchestrator instance."""
    return _dashboard_orchestrator
