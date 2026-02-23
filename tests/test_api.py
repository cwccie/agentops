"""Tests for REST API endpoints."""

import pytest
from agentops.api.routes import create_api_app


@pytest.fixture
def client():
    app = create_api_app(auto_approve=True)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestAPI:
    def test_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "AgentOps API"

    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "healthy"

    def test_status(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "agents" in data

    def test_list_agents(self, client):
        resp = client.get("/api/v1/agents")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["agents"]) == 4

    def test_submit_incident(self, client):
        resp = client.post("/api/v1/incidents", json={
            "device_id": "web-srv-01",
            "description": "CPU spike test",
            "scenario": "cpu_spike",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["incident_id"].startswith("INC-")

    def test_get_incident(self, client):
        # Submit first
        resp = client.post("/api/v1/incidents", json={
            "device_id": "web-srv-01",
            "scenario": "cpu_spike",
        })
        inc_id = resp.get_json()["incident_id"]
        # Get it
        resp = client.get(f"/api/v1/incidents/{inc_id}")
        assert resp.status_code == 200
        assert resp.get_json()["incident_id"] == inc_id

    def test_get_unknown_incident(self, client):
        resp = client.get("/api/v1/incidents/nonexistent")
        assert resp.status_code == 404

    def test_process_incident(self, client):
        resp = client.post("/api/v1/incidents", json={
            "device_id": "db-srv-01",
            "scenario": "disk_full",
        })
        inc_id = resp.get_json()["incident_id"]
        resp = client.post(f"/api/v1/incidents/{inc_id}/process")
        assert resp.status_code == 200

    def test_audit_log(self, client):
        resp = client.get("/api/v1/audit")
        assert resp.status_code == 200
        assert "audit_log" in resp.get_json()

    def test_approvals(self, client):
        resp = client.get("/api/v1/approvals")
        assert resp.status_code == 200
