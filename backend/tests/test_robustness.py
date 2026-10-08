import os
import shutil
from pathlib import Path
import fitz
import pytest
from backend.ingestion.pipeline import (
    ingest_document,
    extract_text_from_file,
    classify_document_type
)
from backend.workflows.service import (
    answer_query,
    review_case,
    draft_document,
    research_legal_issue
)
from backend.verifier.gates import verify_gate_a, verify_gate_b, verify_gate_c

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

@pytest.fixture(scope="session", autouse=True)
def setup_fixtures():
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Recipe PDF (non-legal)
    doc_recipe = fitz.open()
    p = doc_recipe.new_page()
    p.insert_text((50, 50), "Delicious Chocolate Cake Recipe\nIngredients: 2 cups flour, 1 tablespoon sugar, 3 eggs.\nBake time 30 minutes. Calories 250 per slice.\nEnjoy cooking this cuisine.")
    doc_recipe.save(str(FIXTURES_DIR / "recipe.pdf"))
    doc_recipe.close()

    # 2. Empty file
    with open(FIXTURES_DIR / "empty.pdf", "wb") as f:
        f.write(b"")

    # 3. Corrupted PDF
    with open(FIXTURES_DIR / "corrupted.pdf", "wb") as f:
        f.write(b"%PDF-1.4\ncorrupted_gibberish_bytes_cannot_parse")

    # 4. Password-protected PDF
    doc_enc = fitz.open()
    p = doc_enc.new_page()
    p.insert_text((50, 50), "Confidential legal judgment")
    doc_enc.save(str(FIXTURES_DIR / "locked.pdf"), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret123")
    doc_enc.close()

    # 5. TXT file (Legal Notice)
    with open(FIXTURES_DIR / "notice.txt", "w", encoding="utf-8") as f:
        f.write("LEGAL NOTICE\nUnder Section 138 Negotiable Instruments Act.\nCheque No. 44109 dishonoured for Rs. 50,000.\nDemand payment within 15 days.")

    # 6. Unsupported file (.exe)
    with open(FIXTURES_DIR / "unsupported.exe", "wb") as f:
        f.write(b"MZ\x90\x00\x03\x00\x00\x00")

    # 7. Non-English (Hindi) Legal document
    doc_hindi = fitz.open()
    p_h = doc_hindi.new_page()
    p_h.insert_text((50, 50), "न्यायालय मुख्य न्यायिक मजिस्ट्रेट, दिल्ली।\nअपराध संख्या 402/2024 धारा 420 भारतीय दंड संहिता।\nअभियुक्त की जमानत याचिका स्वीकार की जाती है।")
    doc_hindi.save(str(FIXTURES_DIR / "hindi_legal.pdf"))
    doc_hindi.close()

    # 8. Synthetic Bail Case PDF
    doc_bail = fitz.open()
    p_b = doc_bail.new_page()
    p_b.insert_text((50, 50), "IN THE HIGH COURT OF DELHI\nBAIL APPLN. NO. 550/2024\nRAMESH v. STATE\nUnder Section 439 CrPC for regular bail in FIR No. 12/2024 under Section 420 IPC.\nApplicant has been in custody since 10-Jan-2024. Chargesheet is filed.\nBail granted on bond of Rs. 25,000/-.")
    doc_bail.save(str(FIXTURES_DIR / "synthetic_bail.pdf"))
    doc_bail.close()

    # 9. Synthetic Cheque Bounce Case PDF
    doc_cheque = fitz.open()
    p_c = doc_cheque.new_page()
    p_c.insert_text((50, 50), "IN THE COURT OF METROPOLITAN MAGISTRATE\nCC NO. 882/2024\nSUNIL v. AMIT\nComplaint under Section 138 of Negotiable Instruments Act.\nCheque No. 90211 dated 05-Feb-2024 for Rs. 1,00,000/- returned unpaid with remark funds insufficient.\nStatutory notice served.")
    doc_cheque.save(str(FIXTURES_DIR / "synthetic_cheque.pdf"))
    doc_cheque.close()

    yield

def test_unsupported_file_type():
    res = ingest_document(str(FIXTURES_DIR / "unsupported.exe"), "doc_unsupported")
    assert res["status"] == "error"
    assert "supported" in res["message"].lower()

def test_empty_file():
    res = ingest_document(str(FIXTURES_DIR / "empty.pdf"), "doc_empty")
    assert res["status"] == "error"
    assert "couldn't read" in res["message"].lower() or "empty" in res.get("error_code", "")

def test_corrupted_file():
    res = ingest_document(str(FIXTURES_DIR / "corrupted.pdf"), "doc_corrupted")
    assert res["status"] == "error"
    assert "couldn't read" in res["message"].lower()

def test_password_protected_pdf():
    res = ingest_document(str(FIXTURES_DIR / "locked.pdf"), "doc_locked")
    assert res["status"] == "error"
    assert "locked" in res["message"].lower() or "unlocked copy" in res["message"].lower()

def test_recipe_classified_as_not_legal():
    res = ingest_document(str(FIXTURES_DIR / "recipe.pdf"), "doc_recipe")
    assert res["is_legal"] is False
    assert res["doc_type"] == "not_legal"
    assert "doesn't look like a case file" in res["message"].lower()

def test_txt_file_ingestion():
    res = ingest_document(str(FIXTURES_DIR / "notice.txt"), "doc_notice")
    assert res["status"] in ["ready", "duplicate"]
    assert res["is_legal"] is True
    assert res["case_type"] == "cheque_bounce"

def test_duplicate_file_detection():
    # Ingesting same file twice
    res1 = ingest_document(str(FIXTURES_DIR / "notice.txt"), "doc_dup1")
    res2 = ingest_document(str(FIXTURES_DIR / "notice.txt"), "doc_dup2")
    assert res2["status"] == "duplicate"
    assert "Already uploaded" in res2["message"]

def test_case_type_adaptive_classification():
    res_b = ingest_document(str(FIXTURES_DIR / "synthetic_bail.pdf"), "doc_syn_bail")
    assert res_b["is_legal"] is True
    assert res_b["case_type"] == "bail"

    res_c = ingest_document(str(FIXTURES_DIR / "synthetic_cheque.pdf"), "doc_syn_cheque")
    assert res_c["is_legal"] is True
    assert res_c["case_type"] == "cheque_bounce"

def test_fake_case_trap():
    ans = answer_query("What did the Supreme Court hold in State v. Mercer?")
    assert "Refusal" in ans["answer"] or "cannot be verified" in ans["answer"] or "Not found" in ans["answer"]

def test_deterministic_quote_verifier():
    # Verbatim quote passes Gate A
    pass_a, _ = verify_gate_a("Bail granted on bond of Rs. 25,000/-", "Bail granted on bond of Rs. 25,000/-.")
    assert pass_a is True

    # Altered quote fails Gate A
    fail_a, _ = verify_gate_a("Bail denied on bond of Rs. 25,000/-", "Bail granted on bond of Rs. 25,000/-.")
    assert fail_a is False

def test_draft_missing_placeholders():
    draft = draft_document(doc_type="bail_application")
    assert "[MISSING:" in draft["draft_text"]
    assert "IN THE" in draft["draft_text"]
    assert "IN THE IN THE" not in draft["draft_text"]
