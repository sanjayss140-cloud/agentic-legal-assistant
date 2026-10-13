import os
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.ingestion.pipeline import get_db, ingest_document
from backend.security.auth import (
    hash_password,
    verify_password,
    create_user,
    authenticate_user,
    create_access_token,
    decode_token,
    initiate_password_reset,
    complete_password_reset
)
from backend.security.crypto import encrypt_bytes, decrypt_bytes
from backend.security.redaction import mask_personal_identifiers, restore_personal_identifiers
from backend.retrieval.engine import retrieve

client = TestClient(app)

def test_password_hashing_and_verification():
    raw_pass = "SecureAdvocate2026!"
    h = hash_password(raw_pass)
    assert h.startswith("$argon2") or h.startswith("$2b$")
    assert verify_password(raw_pass, h) is True
    assert verify_password("WrongPassword123", h) is False

def test_login_rate_limiting_and_lockout():
    email = f"lockout_{int(time.time())}@lexground.local"
    pw = "CorrectPassword123!"
    success, _, _ = create_user(email, pw)
    assert success is True

    # 4 failed attempts
    for _ in range(4):
        ok, msg, _ = authenticate_user(email, "WrongPass123")
        assert ok is False
        assert "Invalid" in msg

    # 5th attempt -> triggers lockout
    ok, msg, _ = authenticate_user(email, "WrongPass123")
    assert ok is False
    assert "locked" in msg.lower()

    # Even with correct password, login is blocked during lockout
    ok, msg, _ = authenticate_user(email, pw)
    assert ok is False
    assert "locked" in msg.lower()

def test_password_reset_flow():
    email = f"reset_{int(time.time())}@lexground.local"
    pw = "InitialPassword123!"
    create_user(email, pw)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    user_id = cursor.fetchone()["id"]

    # Initiate reset
    initiate_password_reset(email)
    cursor.execute("SELECT token FROM password_resets WHERE user_id = ? AND used = 0", (user_id,))
    row = cursor.fetchone()
    assert row is not None
    token = row["token"]
    conn.close()

    # Complete reset
    new_pass = "BrandNewPassword2026!"
    ok, msg = complete_password_reset(token, new_pass)
    assert ok is True

    # Verify old password fails, new password succeeds
    ok_old, _, _ = authenticate_user(email, pw)
    assert ok_old is False
    ok_new, _, _ = authenticate_user(email, new_pass)
    assert ok_new is True

def test_crypto_at_rest_encryption():
    secret_text = b"CONFIDENTIAL CASE MEMORANDUM - HIGH COURT"
    enc = encrypt_bytes(secret_text)
    assert enc != secret_text
    assert b"CONFIDENTIAL" not in enc
    dec = decrypt_bytes(enc)
    assert dec == secret_text

def test_pii_identifier_masking_and_restoration():
    sensitive_text = (
        "Client Rajesh Kumar (PAN: ABCDE1234F, Aadhaar: 9876 5432 1098) "
        "can be reached at rajesh.advocate@court.in or +919876543210."
    )
    masked, token_map = mask_personal_identifiers(sensitive_text)
    
    assert "ABCDE1234F" not in masked
    assert "9876 5432 1098" not in masked
    assert "rajesh.advocate@court.in" not in masked
    assert "+919876543210" not in masked
    assert "[PAN_1]" in masked
    assert "[AADHAAR_1]" in masked
    assert "[EMAIL_1]" in masked
    assert "[PHONE_1]" in masked

    # Restore
    restored = restore_personal_identifiers(masked, token_map)
    assert restored == sensitive_text

def test_user_a_and_user_b_complete_isolation(tmp_path):
    # Setup User A
    email_a = f"usera_{int(time.time())}@lexground.local"
    res_a = client.post("/api/auth/register", json={"email": email_a, "password": "PasswordUserA123!"})
    assert res_a.status_code == 200
    token_a = res_a.json()["token"]
    user_a_id = res_a.json()["user"]["id"]

    # Setup User B
    email_b = f"userb_{int(time.time())}@lexground.local"
    res_b = client.post("/api/auth/register", json={"email": email_b, "password": "PasswordUserB123!"})
    assert res_b.status_code == 200
    token_b = res_b.json()["token"]
    user_b_id = res_b.json()["user"]["id"]

    # User A creates a Matter
    mat_a = client.post(
        "/api/matters",
        json={"name": "State v. User A Case", "client_ref": "REF-USER-A", "notes": "Private client"},
        headers={"Authorization": f"Bearer {token_a}"}
    )
    assert mat_a.status_code == 200
    matter_a_id = mat_a.json()["matter"]["id"]

    # User A uploads a legal document to their matter
    test_file_path = tmp_path / "private_contract_a.txt"
    test_file_path.write_text("IN THE HIGH COURT OF DELHI\nCase No. CRL-A-101/2026\nSecret testimony concerning Project Alpha confidential agreement.")
    
    with open(test_file_path, "rb") as f:
        up_res = client.post(
            "/api/docs/upload",
            files={"files": ("private_contract_a.txt", f, "text/plain")},
            headers={"Authorization": f"Bearer {token_a}", "X-Matter-Id": matter_a_id}
        )
    assert up_res.status_code == 200
    doc_a_id = up_res.json()["id"]

    # 1. User B lists documents -> Doc A MUST NOT appear
    list_b = client.get("/api/docs", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    doc_ids_for_b = [d["id"] for d in list_b.json()["documents"]]
    assert doc_a_id not in doc_ids_for_b

    # 2. User B tries to get status of Doc A -> 404 / access denied
    stat_b = client.get(f"/api/docs/{doc_a_id}/status", headers={"Authorization": f"Bearer {token_b}"})
    assert stat_b.status_code == 404

    # 3. User B tries to retrieve/search using Doc A's ID -> 0 chunks returned
    ret_b = client.post(
        "/api/retrieve",
        json={"query": "Project Alpha", "doc_ids": [doc_a_id]},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert ret_b.status_code == 200
    assert len(ret_b.json()["chunks"]) == 0

    # 4. User B queries chat explicitly asking about Doc A -> denied or not found
    chat_b = client.post(
        "/api/chat",
        json={"question": "What is Project Alpha in Case CRL-A-101?", "doc_ids": [doc_a_id]},
        headers={"Authorization": f"Bearer {token_b}"}
    )
    assert chat_b.status_code == 200
    assert "not available" in chat_b.json()["answer"].lower() or "not found" in chat_b.json()["answer"].lower()

    # 5. User B tries to delete User A's matter -> 404 / denied
    del_mat_b = client.delete(f"/api/matters/{matter_a_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert del_mat_b.status_code == 404

    # 6. Verify User A CAN see their document and matter
    list_a = client.get("/api/docs", headers={"Authorization": f"Bearer {token_a}"})
    assert any(d["id"] == doc_a_id for d in list_a.json()["documents"])

def test_account_deletion_removes_all_user_data(tmp_path):
    email = f"purge_{int(time.time())}@lexground.local"
    res = client.post("/api/auth/register", json={"email": email, "password": "PurgePassword123!"})
    token = res.json()["token"]
    user_id = res.json()["user"]["id"]

    # Upload a document
    doc_file = tmp_path / "purge_record.txt"
    doc_file.write_text("IN THE SUPREME COURT OF INDIA\nBail order for Purge Test.")
    with open(doc_file, "rb") as f:
        up = client.post(
            "/api/docs/upload",
            files={"files": ("purge_record.txt", f, "text/plain")},
            headers={"Authorization": f"Bearer {token}"}
        )
    doc_id = up.json()["id"]

    # Check existence in DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (doc_id,))
    assert cursor.fetchone() is not None
    conn.close()

    # Delete Account
    del_res = client.delete("/api/user/account", headers={"Authorization": f"Bearer {token}"})
    assert del_res.status_code == 200

    # Verify purge in DB
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    assert cursor.fetchone() is None
    cursor.execute("SELECT id FROM documents WHERE user_id = ?", (user_id,))
    assert cursor.fetchall() == []
    cursor.execute("SELECT chunk_id FROM chunks WHERE user_id = ?", (user_id,))
    assert cursor.fetchall() == []
    cursor.execute("SELECT id FROM matters WHERE user_id = ?", (user_id,))
    assert cursor.fetchall() == []
    conn.close()

    # Calling with old token fails (session invalid)
    st = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert st.status_code == 401

def test_expired_or_tampered_token_rejection():
    # Fresh isolated client state
    isolated_client = TestClient(app)

    # Invalid token string
    res = isolated_client.get("/api/auth/me", headers={"Authorization": "Bearer totally_forged_token"})
    assert res.status_code == 401

    # Expired token
    from datetime import datetime, timedelta, timezone
    import jwt
    from backend.security.auth import JWT_SECRET, JWT_ALGORITHM
    expired_payload = {
        "sub": "user_expired",
        "email": "expired@test.com",
        "role": "lawyer",
        "type": "access",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=10),
        "iat": datetime.now(timezone.utc) - timedelta(minutes=40)
    }
    expired_token = jwt.encode(expired_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    res2 = isolated_client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res2.status_code == 401
