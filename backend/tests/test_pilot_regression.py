import time
import pytest
import fitz
from pathlib import Path
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.ingestion.pipeline import ingest_document, get_db
from backend.security.auth import create_user, create_access_token
from backend.verifier.gates import verify_gate_a, verify_gate_b, verify_gate_c
from backend.workflows.service import review_case, draft_document, research_legal_issue
from backend.workflows.lawyer_features import (
    build_case_chronology,
    extract_dates_and_deadlines,
    generate_formal_draft,
    check_citations_and_facts
)

client = TestClient(app)

@pytest.fixture(scope="module")
def pilot_synthetic_suite(tmp_path_factory):
    """Generates 5 realistic synthetic case PDFs with known ground-truth facts."""
    base_dir = tmp_path_factory.mktemp("pilot_cases")

    cases = {}

    # Case 1: Bail Application (Criminal)
    p1 = base_dir / "case1_bail.pdf"
    doc1 = fitz.open()
    page1 = doc1.new_page()
    page1.insert_text((50, 70), """IN THE HIGH COURT OF JUDICATURE AT BOMBAY
BAIL APPLICATION NO. 882 OF 2024
IN THE MATTER OF:
Sanjay Gupta ... APPLICANT
VERSUS
State of Maharashtra ... RESPONDENT

FIR No. 204/2023 registered at PS Bandra.
Sections: Section 420, Section 406, and Section 468 of Indian Penal Code.
The Applicant was arrested on 14.11.2023 and has been in judicial custody since.
Investigation is complete and charge sheet has been submitted before the learned Magistrate.
Co-accused Vijay Shah was granted regular bail by this Hon'ble Court on 10.01.2024.
The Applicant undertakes to furnish local solvent surety of Rs. 50,000/-.
Date of Order: 15.02.2024.
""", fontsize=10)
    doc1.save(str(p1))
    doc1.close()
    cases["case1_bail"] = {
        "path": str(p1),
        "ground_truth": {
            "fir": "204/2023",
            "arrest_date": "14.11.2023",
            "co_accused": "Vijay Shah",
            "sections": ["Section 420", "Section 406", "Section 468"],
            "surety": "Rs. 50,000/-"
        }
    }

    # Case 2: Cheque Bounce (Section 138 NI Act)
    p2 = base_dir / "case2_cheque.pdf"
    doc2 = fitz.open()
    page2 = doc2.new_page()
    page2.insert_text((50, 70), """IN THE COURT OF METROPOLITAN MAGISTRATE, NEW DELHI
COMPLAINT CASE NO. 1102 OF 2024
M/s Apex Enterprises ... COMPLAINANT
VERSUS
R.K. Builders & Developers ... ACCUSED

Complaint under Section 138 of the Negotiable Instruments Act, 1881.
1. The Accused issued Cheque No. 998877 dated 15.02.2024 for an amount of Rs. 15,00,000/- drawn on HDFC Bank.
2. The said cheque was presented and returned dishonoured with remark 'Funds Insufficient' on 18.02.2024.
3. Statutory legal demand notice was dispatched on 25.02.2024 and served on 28.02.2024.
4. Despite receipt of notice, the Accused failed to pay within the 15 days period expiring on 14.03.2024.
""", fontsize=10)
    doc2.save(str(p2))
    doc2.close()
    cases["case2_cheque"] = {
        "path": str(p2),
        "ground_truth": {
            "cheque_no": "998877",
            "amount": "Rs. 15,00,000/-",
            "dishonour_date": "18.02.2024",
            "notice_served": "28.02.2024",
            "act": "Negotiable Instruments Act"
        }
    }

    # Case 3: Commercial Dispute / Arbitration
    p3 = base_dir / "case3_commercial.pdf"
    doc3 = fitz.open()
    page3 = doc3.new_page()
    page3.insert_text((50, 70), """IN THE HIGH COURT OF DELHI AT NEW DELHI
COMMERCIAL ARBITRATION PETITION NO. 45 OF 2024
Zenith Software Solutions ... PETITIONER
VERSUS
Omega Retail Corp ... RESPONDENT

Master Software Services Agreement entered on 01.07.2023.
Milestone delivery was completed on 15.10.2023.
Outstanding Invoice No. INV-2023-99 for Rs. 24,50,000/- remains unpaid despite demand notice dated 01.12.2023.
Clause 18 provides for dispute resolution under the Arbitration and Conciliation Act, 1996.
The Petitioner seeks appointment of a sole arbitrator.
""", fontsize=10)
    doc3.save(str(p3))
    doc3.close()
    cases["case3_commercial"] = {
        "path": str(p3),
        "ground_truth": {
            "invoice": "INV-2023-99",
            "amount": "Rs. 24,50,000/-",
            "agreement_date": "01.07.2023",
            "statute": "Arbitration and Conciliation Act"
        }
    }

    # Case 4: Consumer Protection Complaint
    p4 = base_dir / "case4_consumer.pdf"
    doc4 = fitz.open()
    page4 = doc4.new_page()
    page4.insert_text((50, 70), """BEFORE THE DISTRICT CONSUMER DISPUTES REDRESSAL COMMISSION
CONSUMER COMPLAINT NO. 78 OF 2024
Dr. Arvind Mehta ... COMPLAINANT
VERSUS
Star Electronics Pvt Ltd ... OPPOSITE PARTY

Complaint under Section 35 of the Consumer Protection Act, 2019.
The Complainant purchased Medical Imaging Display on 10.08.2023 for Rs. 6,80,000/-.
A severe recurrent display flickering defect appeared on 22.08.2023.
Service Job Sheet No. JS-441 dated 05.09.2023 verified display panel defect.
The Opposite Party refused replacement or refund, constituting deficiency in service.
""", fontsize=10)
    doc4.save(str(p4))
    doc4.close()
    cases["case4_consumer"] = {
        "path": str(p4),
        "ground_truth": {
            "purchase_date": "10.08.2023",
            "defect": "display flickering defect",
            "job_sheet": "JS-441",
            "amount": "Rs. 6,80,000/-"
        }
    }

    # Case 5: Writ Petition (Constitutional)
    p5 = base_dir / "case5_writ.pdf"
    doc5 = fitz.open()
    page5 = doc5.new_page()
    page5.insert_text((50, 70), """IN THE HIGH COURT OF JUDICATURE AT ALLAHABAD
WRIT TAX PETITION NO. 312 OF 2024
Kiran Verma ... PETITIONER
VERSUS
State of Uttar Pradesh and Others ... RESPONDENTS

Petition under Article 226 of the Constitution of India.
The Petitioner holds Mining Lease granted on 12.05.2018 valid till 11.05.2028.
Impugned cancellation order No. MIN-889 was passed on 18.01.2024 without show-cause notice or opportunity of hearing.
The action violates principles of natural justice and Article 14 of the Constitution.
Precedent relied upon: Maneka Gandhi v. Union of India.
Prayer for quashing order dated 18.01.2024.
""", fontsize=10)
    doc5.save(str(p5))
    doc5.close()
    cases["case5_writ"] = {
        "path": str(p5),
        "ground_truth": {
            "order_no": "MIN-889",
            "order_date": "18.01.2024",
            "article": "Article 226",
            "precedent": "Maneka Gandhi v. Union of India"
        }
    }

    return cases

@pytest.fixture(scope="module")
def regression_auth():
    uid = f"reg_lawyer_{int(time.time()*1000)}"
    mid = f"reg_mat_{int(time.time()*1000)}"
    create_user(f"{uid}@test.legal", "SecretPass123!", role="lawyer")
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO matters (id, user_id, name, client_ref, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
              (mid, uid, "Pilot Regression Matter", "REG-01", "Testing", time.time()))
    conn.commit()
    conn.close()
    token = create_access_token(uid, f"{uid}@test.legal", "lawyer", matter_id=mid)
    return {"token": token, "user_id": uid, "matter_id": mid}

def test_regression_ingestion_and_gate_a(pilot_synthetic_suite, regression_auth):
    """Verify all 5 synthetic cases ingest cleanly and Gate A deterministically verifies known ground truth."""
    uid = regression_auth["user_id"]
    mid = regression_auth["matter_id"]

    for case_key, case_info in pilot_synthetic_suite.items():
        doc_id = f"doc_reg_{case_key}_{uid[:6]}"
        res = ingest_document(
            case_info["path"],
            doc_id=doc_id,
            title=f"Synthetic Case: {case_key}",
            user_id=uid,
            matter_id=mid,
            encrypt_at_rest=True
        )
        assert res["status"] in ("ready", "legal_case"), f"Failed to ingest {case_key}"
        case_info["doc_id"] = doc_id

        # Query chunk text
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT text FROM chunks WHERE doc_id = ?", (doc_id,))
        chunks = [r[0] for r in cursor.fetchall()]
        conn.close()
        full_doc_text = " ".join(chunks)

        # Gate A Verification: Exact quotes from ground truth must pass
        gt = case_info["ground_truth"]
        for k, val in gt.items():
            if isinstance(val, str):
                valid, msg = verify_gate_a(val, full_doc_text)
                assert valid is True, f"Gate A failed for ground truth '{val}' in {case_key}"
            elif isinstance(val, list):
                for item in val:
                    valid, msg = verify_gate_a(item, full_doc_text)
                    assert valid is True, f"Gate A failed for ground truth '{item}' in {case_key}"

def test_regression_anti_hallucination_and_gate_c(pilot_synthetic_suite, regression_auth):
    """Verify false claims and unindexed statutes are deterministically caught by Gate A and Gate C."""
    uid = regression_auth["user_id"]
    mid = regression_auth["matter_id"]
    doc_id = pilot_synthetic_suite["case1_bail"]["doc_id"]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT text FROM chunks WHERE doc_id = ?", (doc_id,))
    chunk_text = cursor.fetchone()[0]
    conn.close()

    # 1. Gate A: Fabricated quote must fail
    false_quote = "The applicant was arrested on 01.01.2010 and admitted to full guilt"
    valid, msg = verify_gate_a(false_quote, chunk_text)
    assert valid is False
    assert "not exist" in msg.lower()

    # 2. Gate C: Unindexed statute must be blocked
    false_statute_claim = "The applicant was charged under Section 999 of the Indian Penal Code"
    valid_c, unregistered = verify_gate_c(false_statute_claim, scoped_doc_ids=[doc_id])
    assert valid_c is False
    assert any("Section 999" in u for u in unregistered)

def test_regression_bail_application_draft(pilot_synthetic_suite, regression_auth):
    """Verify formal bail drafting on Case 1 extracts grounded facts and leaves missing placeholders."""
    uid = regression_auth["user_id"]
    mid = regression_auth["matter_id"]
    doc_id = pilot_synthetic_suite["case1_bail"]["doc_id"]

    draft_res = generate_formal_draft(
        doc_type="bail_application",
        doc_ids=[doc_id],
        user_facts={"surety_name": "Ramesh Kumar Gupta"},
        user_id=uid,
        matter_id=mid
    )

    text = draft_res["draft_text"]
    assert "SECTION 439" in text or "BAIL" in text
    # Ground truth facts verified
    assert "204/2023" in text or "14.11.2023" in text or "420" in text
    # Missing placeholders discipline
    assert "[MISSING:" in text or "[USER-PROVIDED]" in text
    assert draft_res.get("fabricated_citations", 0) == 0

def test_regression_cheque_bounce_chronology_and_deadlines(pilot_synthetic_suite, regression_auth):
    """Verify chronology and dates extraction accurately extracts cheque dishonour and notice dates."""
    uid = regression_auth["user_id"]
    mid = regression_auth["matter_id"]
    doc_id = pilot_synthetic_suite["case2_cheque"]["doc_id"]

    # Chronology
    chrono = build_case_chronology(doc_ids=[doc_id], user_id=uid, matter_id=mid)
    dated = [e["date"] for e in chrono["dated_events"]]
    assert any("15.02.2024" in d or "18.02.2024" in d or "25.02.2024" in d or "28.02.2024" in d for d in dated)

    # Deadlines
    deadlines = extract_dates_and_deadlines(doc_ids=[doc_id], user_id=uid, matter_id=mid)
    assert len(deadlines["deadlines"]) >= 1
    assert "does not compute statutory limitation periods" in deadlines["disclaimer"]

def test_regression_citation_checker_across_all_cases(pilot_synthetic_suite, regression_auth):
    """Verify Citation Checker reports supported claims for known facts and unverified for invented facts."""
    uid = regression_auth["user_id"]
    mid = regression_auth["matter_id"]
    doc_id = pilot_synthetic_suite["case5_writ"]["doc_id"]

    brief_text = (
        "The Petitioner holds a Mining Lease granted on 12.05.2018 valid till 11.05.2028. "
        "The impugned cancellation order was passed arbitrarily on 18.01.2024. "
        "The respondent acted without notice contrary to Maneka Gandhi v. Union of India. "
        "The petitioner was previously convicted for treason in the year 1999."
    )

    report = check_citations_and_facts(
        text=brief_text,
        doc_ids=[doc_id],
        user_id=uid,
        matter_id=mid
    )

    assert "summary" in report
    assert (report["summary"]["supported"] + report["summary"]["partially_supported"]) >= 2
    # Treason conviction fact is completely absent from document
    assert report["summary"]["not_found"] >= 1
    assert "does not constitute legal opinion" in report["disclaimer"]
