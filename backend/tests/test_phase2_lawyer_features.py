import os
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.ingestion.pipeline import get_db, ingest_document
from backend.workflows.lawyer_features import (
    check_citations_and_facts,
    build_case_chronology,
    export_chronology_csv,
    export_chronology_docx,
    extract_dates_and_deadlines,
    export_deadlines_ics,
    compare_two_documents,
    build_authority_table,
    generate_formal_draft,
    build_issue_matrix,
    record_feedback,
    get_feedback_records,
    detect_and_process_indian_language,
)

client = TestClient(app)

@pytest.fixture(scope="module")
def setup_test_matter_and_docs(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("p2")
    import secrets
    email = f"lawyer_p2_{secrets.token_hex(6)}@lexground.local"
    res = client.post("/api/auth/register", json={"email": email, "password": "PasswordP2_2026!"})
    token = res.json()["token"]
    user_id = res.json()["user"]["id"]

    # Create Matter
    m_res = client.post(
        "/api/matters",
        json={"name": "Commercial & Bail Matter 2026", "client_ref": "MAT-2026-01", "notes": "Pilot tests"},
        headers={"Authorization": f"Bearer {token}"}
    )
    matter_id = m_res.json()["matter"]["id"]

    # Ingest Doc A (Bail Order)
    file_a = tmp_path / "bail_order_doc.txt"
    file_a.write_text(
        "IN THE HIGH COURT OF DELHI\n"
        "BAIL APPLN. NO. 450/2026\n"
        "IN THE MATTER OF: Rajesh Verma ... PETITIONER VERSUS State of NCT of Delhi ... RESPONDENT\n"
        "ORDER DATED: 15-Mar-2026.\n"
        "The applicant is accused of offences under Section 420 and Section 406 of IPC.\n"
        "Arrest occurred on 10-Jan-2026 and investigation is complete with charge-sheet filed.\n"
        "Hearing fixed for 22-Apr-2026 before the Trial Court.\n"
        "Applicant directed to furnish local solvent surety of Rs. 50,000.\n"
        "Relied upon Satender Kumar Antil v. CBI (2022) 10 SCC 51.\n"
        "Bail is granted on conditions."
    )
    with open(file_a, "rb") as f:
        up_a = client.post(
            "/api/docs/upload",
            files={"files": ("bail_order_doc.txt", f, "text/plain")},
            headers={"Authorization": f"Bearer {token}", "X-Matter-Id": matter_id}
        )
    doc_a_id = up_a.json()["id"]

    # Ingest Doc B (Cheque Dishonour Notice)
    file_b = tmp_path / "cheque_notice_doc.txt"
    file_b.write_text(
        "LEGAL DEMAND NOTICE\n"
        "UNDER SECTION 138 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881\n"
        "TO: Ramesh Gupta ... ACCUSED / RECIPIENT\n"
        "FROM: Rajesh Verma ... COMPLAINANT\n"
        "DATED: 28-Feb-2026.\n"
        "Cheque No. 445566 dated 15-Jan-2026 for amount Rs. 5,00,000 returned unpaid with memo dated 20-Feb-2026.\n"
        "Notice period of 15 days is granted to make payment of Rs. 5,00,000 failing which complaint under Section 138 NI Act shall be filed."
    )
    with open(file_b, "rb") as f:
        up_b = client.post(
            "/api/docs/upload",
            files={"files": ("cheque_notice_doc.txt", f, "text/plain")},
            headers={"Authorization": f"Bearer {token}", "X-Matter-Id": matter_id}
        )
    doc_b_id = up_b.json()["id"]

    return {
        "token": token,
        "user_id": user_id,
        "matter_id": matter_id,
        "doc_a_id": doc_a_id,
        "doc_b_id": doc_b_id
    }

def test_citation_checker_report(setup_test_matter_and_docs):
    ctx = setup_test_matter_and_docs
    token = ctx["token"]
    doc_id = ctx["doc_a_id"]

    brief_text = (
        "The applicant is accused of offences under Section 420 and Section 406 of IPC. "
        "The Supreme Court in Satender Kumar Antil v. CBI held that bail is the rule. "
        "The applicant also committed robbery on Mars."
    )

    resp = client.post(
        "/api/citation-check",
        json={"text": brief_text, "doc_ids": [doc_id]},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "statements" in data
    assert "authorities" in data
    assert "summary" in data

    # Check disclaimer rule: never claim "correct law"
    assert "does not constitute legal opinion" in data["disclaimer"]
    assert "only presence in provided scoped documents" in data["disclaimer"]

    # Statement 1 should be Supported
    stmts = data["statements"]
    assert any("Supported" in s["status"] for s in stmts)
    assert any("Not found" in s["status"] for s in stmts)

    # Authority Satender Kumar Antil found in sources
    auths = data["authorities"]
    assert any("Satender Kumar Antil" in a["authority"] and a["status"] == "Found in provided sources" for a in auths)

def test_case_chronology_and_exports(setup_test_matter_and_docs, tmp_path):
    ctx = setup_test_matter_and_docs
    token = ctx["token"]
    doc_id = ctx["doc_a_id"]

    resp = client.post(
        "/api/chronology",
        json={"doc_ids": [doc_id]},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "dated_events" in data
    assert len(data["dated_events"]) >= 2
    # Verify dates are extracted
    dates = [ev["date"] for ev in data["dated_events"]]
    assert any("15-Mar-2026" in d or "10-Jan-2026" in d for d in dates)

    # CSV Export
    csv_resp = client.get("/api/chronology/export/csv", headers={"Authorization": f"Bearer {token}"})
    assert csv_resp.status_code == 200
    assert "Date,Event,Document,Page,Source Quote" in csv_resp.text

    # DOCX Export
    docx_resp = client.get("/api/chronology/export/docx", headers={"Authorization": f"Bearer {token}"})
    assert docx_resp.status_code == 200
    assert len(docx_resp.content) > 1000

def test_dates_and_deadlines_calendar_export(setup_test_matter_and_docs):
    ctx = setup_test_matter_and_docs
    token = ctx["token"]
    doc_id = ctx["doc_a_id"]

    resp = client.post(
        "/api/deadlines",
        json={"doc_ids": [doc_id]},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "deadlines" in data
    assert "Extracted from the documents; verify before relying" in data["disclaimer"]

    # ICS Calendar export
    ics_resp = client.get("/api/deadlines/export/ics", headers={"Authorization": f"Bearer {token}"})
    assert ics_resp.status_code == 200
    assert "BEGIN:VCALENDAR" in ics_resp.text
    assert "END:VCALENDAR" in ics_resp.text

def test_document_comparison(setup_test_matter_and_docs):
    ctx = setup_test_matter_and_docs
    token = ctx["token"]
    doc_a = ctx["doc_a_id"]
    doc_b = ctx["doc_b_id"]

    resp = client.post(
        "/api/docs/compare",
        json={"doc_id_a": doc_a, "doc_id_b": doc_b},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "differences" in data
    assert data["differences_count"] > 0
    diff_types = [d["type"] for d in data["differences"]]
    assert any("Party" in t or "Timeline" in t or "Court" in t for t in diff_types)

def test_authority_table(setup_test_matter_and_docs):
    ctx = setup_test_matter_and_docs
    token = ctx["token"]
    doc_a = ctx["doc_a_id"]

    resp = client.post(
        "/api/authorities",
        json={"doc_ids": [doc_a]},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "authorities" in data
    auth_names = [a["name"] for a in data["authorities"]]
    assert any("Section 420" in a or "Satender Kumar Antil" in a for a in auth_names)

def test_five_formal_draft_templates(setup_test_matter_and_docs):
    ctx = setup_test_matter_and_docs
    token = ctx["token"]
    doc_a = ctx["doc_a_id"]

    templates = [
        "bail_application",
        "section_138_complaint",
        "consumer_complaint",
        "writ_petition",
        "legal_notice"
    ]

    for tmpl in templates:
        resp = client.post(
            "/api/draft/template",
            json={
                "doc_type": tmpl,
                "doc_ids": [doc_a],
                "user_facts": {"arrest_date": "10-Jan-2026", "cheque_no": "998877", "amount": "1,00,000"}
            },
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["doc_type"] == tmpl
        assert len(data["draft_text"]) > 100
        assert "pre_draft_report" in data
        assert "export_files" in data
        assert data["export_files"]["docx"].endswith(".docx")

def test_issue_matrix(setup_test_matter_and_docs):
    ctx = setup_test_matter_and_docs
    token = ctx["token"]
    doc_a = ctx["doc_a_id"]

    resp = client.post(
        "/api/issues",
        json={"doc_ids": [doc_a]},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "matrix" in data
    assert len(data["matrix"]) > 0
    item = data["matrix"][0]
    assert "issue" in item
    assert "opposing_arguments" in item
    assert "supporting_evidence" in item
    assert "weak_spots" in item

def test_per_answer_feedback(setup_test_matter_and_docs):
    ctx = setup_test_matter_and_docs
    token = ctx["token"]

    # Submit feedback
    resp = client.post(
        "/api/feedback",
        json={
            "rating": 1,
            "notes": "Excellent verified citation from bail order.",
            "message_id": "msg_test_01",
            "prompt_version": "v2.0-verified",
            "model": "llama-3.3-70b-versatile",
            "retrieval_params": {"mode": "hybrid_rerank", "top_k": 6},
            "verified_status": "pass"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Query feedback
    fb_list = client.get("/api/feedback", headers={"Authorization": f"Bearer {token}"})
    assert fb_list.status_code == 200
    records = fb_list.json()["feedback"]
    assert len(records) >= 1
    assert records[0]["rating"] == 1
    assert records[0]["notes"] == "Excellent verified citation from bail order."

def test_multilingual_indian_language_processing():
    hindi_text = "अभियुक्त ने दण्ड प्रक्रिया संहिता की धारा 439 के तहत नियमित जमानत याचिका प्रस्तुत की।"
    res = detect_and_process_indian_language(hindi_text)

    assert res["language"] == "hi"
    assert res["is_multilingual"] is True
    concepts = [c["concept"] for c in res["mapped_legal_concepts"]]
    assert "bail" in concepts
    assert "section" in concepts
    assert "CrPC" in concepts
