from fastapi.testclient import TestClient
from backend.app.main import app
import pytest

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert data.get("app") == "Agentic Legal Assistant"

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "Agentic Legal Assistant" in response.text

