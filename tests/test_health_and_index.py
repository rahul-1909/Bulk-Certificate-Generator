"""Tests for health check and index endpoints."""

from fastapi.testclient import TestClient


def test_health_check_endpoint(client: TestClient):
    """Verify that /health and /api/v1/health return healthy status for DB and storage."""
    res1 = client.get("/health")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "healthy"
    assert data1["database"] == "healthy"
    assert data1["storage"] == "healthy"

    res2 = client.get("/api/v1/health")
    assert res2.status_code == 200
    assert res2.json()["status"] == "healthy"


def test_index_endpoint(client: TestClient):
    """Verify service root index endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Bulk Certificate Generator API"
    assert data["status"] == "online"
    assert data["documentation"] == "/docs"
