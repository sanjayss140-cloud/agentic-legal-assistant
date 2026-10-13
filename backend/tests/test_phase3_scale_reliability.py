import os
import time
import pytest
import fitz
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.ingestion.pipeline import get_db, init_db
from backend.security.auth import create_user, create_access_token
from backend.ingestion.async_worker import (
    create_job,
    update_job,
    get_job,
    recover_stale_jobs,
    process_job,
)
from backend.security.rate_limiter import (
    check_rate_limit,
    reset_rate_limits,
    check_matter_document_quota,
    record_token_usage,
    check_token_budget,
)
from backend.services.groq_resilience import (
    GroqCircuitBreaker,
    CircuitBreakerOpenError,
    resilient_groq_completion,
)
from backend.services.metrics import generate_prometheus_metrics

client = TestClient(app)

@pytest.fixture
def auth_headers_scale():
    email = f"scale_lawyer_{int(time.time()*1000)}@firm.legal"
    _, _, user = create_user(email, "StrongSecretPass123!", role="lawyer")
    conn = get_db()
    cursor = conn.cursor()
    matter_id = f"mat_scale_{int(time.time()*1000)}"
    cursor.execute(
        "INSERT INTO matters (id, user_id, name, client_ref, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (matter_id, user["id"], "Scale & Reliability Matter", "SCALE-01", "Testing", time.time())
    )
    conn.commit()
    conn.close()

    token = create_access_token(user["id"], user["email"], user["role"], matter_id=matter_id)
    return {
        "Authorization": f"Bearer {token}",
        "x-user-id": user["id"],
        "x-matter-id": matter_id,
        "user_id": user["id"],
        "matter_id": matter_id
    }

def test_alembic_migration_up_and_down():
    """Verify schema migrations run cleanly up and down using Alembic."""
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    
    # 1. Downgrade to base
    command.downgrade(alembic_cfg, "base")

    # 2. Upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Verify tables exist in DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cursor.fetchall()}
    conn.close()

    expected_tables = {
        "users", "matters", "documents", "chunks", "citation_registry",
        "chat_history", "drafts", "password_resets", "audit_logs",
        "answer_feedback", "ingestion_jobs"
    }
    assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"

def test_async_ingestion_20_page_document(auth_headers_scale, tmp_path):
    """Verify a 20-page document processes asynchronously without blocking concurrent requests."""
    # Create synthetic 20-page PDF
    doc = fitz.open()
    for page_num in range(1, 21):
        page = doc.new_page(width=595, height=842)
        text = f"IN THE HIGH COURT OF DELHI\nPage {page_num} of 20\nSection 439 CrPC regular bail.\nApplicant was not named in FIR No. 101/2024.\nDate: 15.01.2024.\n"
        page.insert_text((50, 72), text, fontsize=11)
    
    pdf_path = tmp_path / "twenty_page_case.pdf"
    doc.save(str(pdf_path))
    doc.close()

    headers = {
        "Authorization": auth_headers_scale["Authorization"],
        "x-matter-id": auth_headers_scale["matter_id"]
    }

    # Upload asynchronously
    with open(pdf_path, "rb") as f:
        resp = client.post(
            "/api/docs/upload-async",
            files={"files": ("twenty_page_case.pdf", f, "application/pdf")},
            headers=headers
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    job_id = data.get("job_id") or data.get("jobs", [{}])[0].get("job_id")
    assert job_id is not None
    assert data.get("status") == "queued" or data.get("jobs", [{}])[0].get("status") == "queued"

    # Concurrent request works immediately while job is in progress
    health_resp = client.get("/health")
    assert health_resp.status_code == 200

    # Poll job status until completion (up to 15s)
    completed = False
    for _ in range(60):
        job_resp = client.get(f"/api/jobs/{job_id}", headers=headers)
        assert job_resp.status_code == 200
        job_data = job_resp.json()
        if job_data["status"] == "ready":
            completed = True
            assert job_data["progress_pct"] == 100
            assert job_data["document_id"] is not None
            break
        elif job_data["status"] == "failed":
            pytest.fail(f"Async ingestion failed: {job_data.get('error_message')}")
        time.sleep(0.1)

    assert completed, "Job did not complete within timeout"

def test_recover_stale_jobs_on_worker_restart():
    """Verify interrupted jobs are gracefully transitioned and not lost on restart."""
    job_id = create_job("test_user_restart", "test_matter", "interrupted_file.pdf")
    update_job(job_id, status="chunking", progress_pct=45)

    # Simulate worker restart
    recovered = recover_stale_jobs()
    assert recovered >= 1

    job = get_job(job_id)
    assert job is not None
    assert job["status"] == "failed"
    assert "worker restart" in job["error_message"].lower()

def test_rate_limiter_rpm_trigger_and_reset():
    """Verify rate limit triggers clean 429 with retry-after and resets properly."""
    reset_rate_limits()
    test_user = "test_rate_user_123"
    custom_rpm = 5

    # 5 requests should pass
    for _ in range(custom_rpm):
        allowed, retry_after, msg = check_rate_limit(test_user, rpm_limit=custom_rpm)
        assert allowed is True
        assert retry_after == 0

    # 6th request must trigger rate limit
    allowed, retry_after, msg = check_rate_limit(test_user, rpm_limit=custom_rpm)
    assert allowed is False
    assert retry_after > 0
    assert "rate limit" in msg.lower()

    # Reset
    reset_rate_limits()
    allowed_after, _, _ = check_rate_limit(test_user, rpm_limit=custom_rpm)
    assert allowed_after is True

def test_matter_document_quota():
    """Verify per-matter document quotas prevent unbounded uploads."""
    user_id = "quota_user"
    matter_id = "quota_matter"

    # Check quota with limit of 0
    allowed, msg = check_matter_document_quota(user_id, matter_id, max_docs=0)
    assert allowed is False
    assert "quota" in msg.lower()

    # High quota should pass
    allowed_high, _ = check_matter_document_quota(user_id, matter_id, max_docs=1000)
    assert allowed_high is True

def test_daily_token_budget():
    """Verify daily token consumption tracking and quota enforcement."""
    reset_rate_limits()
    user_id = "token_budget_user"

    # Consume 5,000 tokens out of 10,000 budget
    record_token_usage(user_id, 5000)
    allowed, remaining, _ = check_token_budget(user_id, max_daily_tokens=10000)
    assert allowed is True
    assert remaining == 5000

    # Consume another 6,000 tokens -> exceeds 10,000
    record_token_usage(user_id, 6000)
    allowed, remaining, msg = check_token_budget(user_id, max_daily_tokens=10000)
    assert allowed is False
    assert remaining == 0
    assert "exhausted" in msg.lower()

def test_circuit_breaker_trips_on_simulated_503_and_resets():
    """Verify circuit breaker trips on repeated 503 errors and resets gracefully."""
    cb = GroqCircuitBreaker(failure_threshold=3, recovery_timeout=0.2)
    assert cb.state == "CLOSED"
    assert cb.can_attempt() is True

    mock_client = MagicMock()
    # Simulate HTTP 503 Service Unavailable
    mock_client.chat.completions.create.side_effect = Exception("503 Service Unavailable")

    # Call resilient completion - should fail and trip circuit breaker after threshold
    for i in range(3):
        try:
            resilient_groq_completion(
                mock_client,
                messages=[{"role": "user", "content": "hi"}],
                circuit_breaker=cb,
                max_retries=1
            )
        except Exception:
            pass

    assert cb.state == "OPEN"
    assert cb.can_attempt() is False

    # Calling when OPEN raises CircuitBreakerOpenError fail-fast without hitting upstream
    with pytest.raises(CircuitBreakerOpenError) as exc_info:
        resilient_groq_completion(
            mock_client,
            messages=[{"role": "user", "content": "hi"}],
            circuit_breaker=cb
        )
    assert "LLM provider temporarily unavailable; cached verification is active" in str(exc_info.value)

    # After recovery timeout, it transitions to HALF_OPEN
    time.sleep(0.25)
    assert cb.can_attempt() is True
    assert cb.state == "HALF_OPEN"

    # Successful call resets state to CLOSED
    mock_client.chat.completions.create.side_effect = None
    mock_choice = MagicMock()
    mock_choice.message.content = "OK"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp

    resp = resilient_groq_completion(
        mock_client,
        messages=[{"role": "user", "content": "hi"}],
        circuit_breaker=cb
    )
    assert cb.state == "CLOSED"
    assert cb.failures == 0

def test_groq_resilience_model_fallback():
    """Verify fallback from 70B to 8B when 70B encounters rate limit (429)."""
    cb = GroqCircuitBreaker(failure_threshold=5)
    mock_client = MagicMock()

    calls = []
    def mock_create(model, messages, **kwargs):
        calls.append(model)
        if model == "llama-3.3-70b-versatile":
            raise Exception("429 Rate limit exceeded for 70b")
        mock_choice = MagicMock()
        mock_choice.message.content = "Fallback 8B response"
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        return mock_resp

    mock_client.chat.completions.create.side_effect = mock_create

    resp = resilient_groq_completion(
        mock_client,
        messages=[{"role": "user", "content": "test"}],
        model="llama-3.3-70b-versatile",
        fallback_model="llama-3.1-8b-instant",
        circuit_breaker=cb,
        max_retries=2
    )

    assert "llama-3.3-70b-versatile" in calls
    assert "llama-3.1-8b-instant" in calls
    assert resp.choices[0].message.content == "Fallback 8B response"

def test_metrics_endpoint():
    """Verify Prometheus metrics endpoint outputs valid OpenMetrics format."""
    # Hit health endpoint to record an HTTP request
    client.get("/health")

    resp = client.get("/metrics")
    assert resp.status_code == 200
    metrics_text = resp.text

    assert "# HELP http_requests_total" in metrics_text
    assert "# TYPE http_requests_total counter" in metrics_text
    assert "# HELP retrieval_latency_seconds" in metrics_text
    assert "# TYPE retrieval_latency_seconds histogram" in metrics_text
    assert "# HELP verification_outcomes_total" in metrics_text
    assert "# HELP ingestion_queue_depth" in metrics_text
    assert "ingestion_queue_depth" in metrics_text
