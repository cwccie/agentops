"""
REST API — submit incidents, query agent status, approve/reject changes, view audit log.

Provides a Flask-based REST API for interacting with the AgentOps platform
programmatically.
"""

from __future__ import annotations

import json
import time
from typing import Any

from flask import Blueprint, Flask, jsonify, request

from agentops.orchestrator.engine import Orchestrator

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# Module-level orchestrator reference (set during app creation)
_orchestrator: Orchestrator | None = None


def set_orchestrator(orch: Orchestrator) -> None:
    """Set the orchestrator instance for the API."""
    global _orchestrator
    _orchestrator = orch


def get_orchestrator() -> Orchestrator:
    """Get the orchestrator instance."""
    if _orchestrator is None:
        raise RuntimeError("Orchestrator not initialized")
    return _orchestrator


@api_bp.route("/health", methods=["GET"])
def health_check() -> tuple[Any, int]:
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": time.time()}), 200


@api_bp.route("/status", methods=["GET"])
def platform_status() -> tuple[Any, int]:
    """Get platform status including all agents."""
    orch = get_orchestrator()
    return jsonify(orch.get_status()), 200


@api_bp.route("/incidents", methods=["POST"])
def submit_incident() -> tuple[Any, int]:
    """Submit a new incident for automated resolution."""
    data = request.get_json() or {}
    orch = get_orchestrator()

    device_id = data.get("device_id", "unknown")
    description = data.get("description", "Incident submitted via API")
    scenario = data.get("scenario", "unknown")

    incident = orch.submit_incident(device_id, description, scenario)

    return jsonify({
        "incident_id": incident.incident_id,
        "status": incident.status.value,
        "device_id": incident.device_id,
        "message": "Incident submitted successfully",
    }), 201


@api_bp.route("/incidents/<incident_id>", methods=["GET"])
def get_incident(incident_id: str) -> tuple[Any, int]:
    """Get incident details."""
    orch = get_orchestrator()
    incident = orch.incidents.get(incident_id)
    if not incident:
        return jsonify({"error": f"Incident {incident_id} not found"}), 404

    return jsonify({
        "incident_id": incident.incident_id,
        "device_id": incident.device_id,
        "description": incident.description,
        "status": incident.status.value,
        "scenario": incident.scenario,
        "created_at": incident.created_at,
        "resolved_at": incident.resolved_at,
        "timeline_events": len(incident.timeline),
    }), 200


@api_bp.route("/incidents/<incident_id>/process", methods=["POST"])
def process_incident(incident_id: str) -> tuple[Any, int]:
    """Process an incident through the pipeline."""
    orch = get_orchestrator()

    try:
        incident = orch.process_incident(incident_id)
        return jsonify({
            "incident_id": incident.incident_id,
            "status": incident.status.value,
            "timeline_events": len(incident.timeline),
        }), 200
    except KeyError:
        return jsonify({"error": f"Incident {incident_id} not found"}), 404


@api_bp.route("/incidents/<incident_id>/approve", methods=["POST"])
def approve_incident(incident_id: str) -> tuple[Any, int]:
    """Approve an incident's remediation plan."""
    data = request.get_json() or {}
    orch = get_orchestrator()

    try:
        approved_by = data.get("approved_by", "api-user")
        incident = orch.approve_incident(incident_id, approved_by)
        return jsonify({
            "incident_id": incident.incident_id,
            "status": incident.status.value,
            "approved_by": approved_by,
        }), 200
    except KeyError:
        return jsonify({"error": f"Incident {incident_id} not found"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/incidents/<incident_id>/timeline", methods=["GET"])
def get_timeline(incident_id: str) -> tuple[Any, int]:
    """Get incident timeline."""
    orch = get_orchestrator()
    timeline = orch.get_incident_timeline(incident_id)
    if not timeline:
        return jsonify({"error": f"No timeline for {incident_id}"}), 404
    return jsonify({"incident_id": incident_id, "timeline": timeline}), 200


@api_bp.route("/agents", methods=["GET"])
def list_agents() -> tuple[Any, int]:
    """List all registered agents and their status."""
    orch = get_orchestrator()
    agents = []
    for agent in orch._agents:
        agents.append({
            "agent_id": agent.agent_id,
            "name": agent.name,
            "state": agent.state.value,
            "capabilities": agent.card.capabilities,
            "status": agent.get_status(),
        })
    return jsonify({"agents": agents}), 200


@api_bp.route("/approvals", methods=["GET"])
def list_pending_approvals() -> tuple[Any, int]:
    """List all pending approval requests."""
    orch = get_orchestrator()
    pending = orch.remediator.get_pending_approvals()
    return jsonify({
        "pending": [
            orch.remediator.get_plan_summary(p.plan_id)
            for p in pending
        ],
    }), 200


@api_bp.route("/audit", methods=["GET"])
def audit_log() -> tuple[Any, int]:
    """View the combined audit log from all agents."""
    orch = get_orchestrator()
    audit = []
    for agent in orch._agents:
        for entry in agent.get_action_log()[-50:]:  # Last 50 per agent
            audit.append(entry)
    audit.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    return jsonify({"audit_log": audit[:200]}), 200


def create_api_app(auto_approve: bool = False) -> Flask:
    """Create and configure the Flask API application."""
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    orch = Orchestrator(auto_approve=auto_approve)
    set_orchestrator(orch)

    app.register_blueprint(api_bp)

    @app.route("/")
    def index() -> tuple[Any, int]:
        return jsonify({
            "name": "AgentOps API",
            "version": "0.1.0",
            "endpoints": [
                "/api/v1/health",
                "/api/v1/status",
                "/api/v1/incidents",
                "/api/v1/agents",
                "/api/v1/approvals",
                "/api/v1/audit",
            ],
        }), 200

    return app
