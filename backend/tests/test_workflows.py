import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["app"] == "Agentic Legal Assistant"

def test_docs_list():
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    assert "documents" in resp.json()

def test_review_workflow():
    resp = client.post("/api/review", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "key_facts" in data
    assert "timeline" in data
    assert "contradictions" in data
    assert "missing_info" in data

def test_draft_workflow():
    resp = client.post("/api/draft", json={"user_facts": {"arrest_date": "24-Jan-2024"}})
    assert resp.status_code == 200
    data = resp.json()
    assert "draft_text" in data
    assert data["groundedness_score"] >= 60.0

def test_research_workflow():
    resp = client.post("/api/research", json={"issue": "Parity in bail under Section 439"})
    assert resp.status_code == 200
    data = resp.json()
    assert "statutes" in data
    assert "precedents" in data

def test_eval_results():
    resp = client.get("/api/eval/results")
    assert resp.status_code == 200
    data = resp.json()
    assert "ablation" in data
    assert len(data["ablation"]) == 8
