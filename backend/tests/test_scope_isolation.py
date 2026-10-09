import pytest
from pathlib import Path
from backend.ingestion.pipeline import get_db, ingest_document
from backend.workflows.service import answer_query, review_case, draft_document, research_legal_issue
from backend.verifier.gates import run_critic_repair_loop

FIXTURES_DIR = Path(__file__).parent / "fixtures"

DOC_A_ID = "iso_doc_legal_a"
DOC_B_ID = "iso_doc_recipe_b"
DOC_C_ID = "iso_doc_cheque_c"

@pytest.fixture(scope="module", autouse=True)
def setup_isolation_docs():
    global DOC_A_ID, DOC_B_ID, DOC_C_ID
    res_a = ingest_document(str(FIXTURES_DIR / "synthetic_bail.pdf"), doc_id="iso_doc_legal_a", title="State v. Accused (Bail Order)")
    DOC_A_ID = res_a.get("doc_id") or "iso_doc_legal_a"

    res_b = ingest_document(str(FIXTURES_DIR / "recipe.pdf"), doc_id="iso_doc_recipe_b", title="Chocolate Cake Recipe")
    DOC_B_ID = res_b.get("doc_id") or "iso_doc_recipe_b"

    res_c = ingest_document(str(FIXTURES_DIR / "notice.txt"), doc_id="iso_doc_cheque_c", title="Statutory Cheque Notice")
    DOC_C_ID = res_c.get("doc_id") or "iso_doc_cheque_c"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET title = 'State v. Accused (Bail Order)', is_legal = 1 WHERE id = ?", (DOC_A_ID,))
    cursor.execute("UPDATE documents SET title = 'Chocolate Cake Recipe', is_legal = 0, user_override = 0 WHERE id = ?", (DOC_B_ID,))
    cursor.execute("UPDATE documents SET title = 'Statutory Cheque Notice', is_legal = 1 WHERE id = ?", (DOC_C_ID,))
    conn.commit()
    conn.close()

def test_tick_none_selection_blocks_all_workflows():
    """Tick none -> clear prompt to select; repeat for chat, review, draft and research."""
    # 1. Chat
    ans = answer_query("What happened?", doc_ids=[])
    assert "Please select at least one document to proceed" in ans["answer"]
    assert ans["claims"] == []
    assert ans["sources_used"] == []

    # 2. Case Review
    rev = review_case(doc_ids=[])
    assert "error" in rev
    assert "Please select at least one document to proceed" in rev["error"]

    # 3. Draft
    drf = draft_document(doc_ids=[])
    assert "error" in drf
    assert "Please select at least one document to proceed" in drf["error"]

    # 4. Research
    res = research_legal_issue("Section 439 CrPC", doc_ids=[])
    assert "Please select at least one document to proceed" in res["message"]
    assert res["statutes"] == []
    assert res["precedents"] == []

def test_tick_only_non_legal_without_override():
    """Ticked set is empty after excluding not_legal -> return clear message and run NOTHING."""
    # Ensure user_override is 0
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET user_override = 0, is_legal = 0 WHERE id = ?", (DOC_B_ID,))
    conn.commit()
    conn.close()

    # 1. Chat
    ans = answer_query("What are the grounds?", doc_ids=[DOC_B_ID])
    assert "The selected file isn't a legal document" in ans["answer"]
    assert ans["claims"] == []

    # 2. Review
    rev = review_case(doc_ids=[DOC_B_ID])
    assert "The selected file isn't a legal document" in rev["error"]

    # 3. Draft
    drf = draft_document(doc_ids=[DOC_B_ID])
    assert "The selected file isn't a legal document" in drf["error"]

    # 4. Research
    res = research_legal_issue("Bail", doc_ids=[DOC_B_ID])
    assert "The selected file isn't a legal document" in res["message"]

def test_tick_only_non_legal_with_use_anyway_override():
    """With 'Use anyway' on non-legal: run only on that file; fields absent become MISSING; zero content from legal doc A."""
    # Set user_override to 1
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE documents SET user_override = 1 WHERE id = ?", (DOC_B_ID,))
    conn.commit()
    conn.close()

    # 1. Case Review on B only
    rev = review_case(doc_ids=[DOC_B_ID])
    assert "error" not in rev
    assert rev["title"] == "Chocolate Cake Recipe"
    assert rev["sources_used"] == ["Chocolate Cake Recipe"]

    # Assert zero content from document A
    rev_str = str(rev)
    assert "Vikram Sharma" not in rev_str
    assert "Suresh Kumar Kait" not in rev_str
    assert "Criminal Misc" not in rev_str

    # Assert fields absent from recipe become MISSING
    for kf in rev["key_facts"]:
        assert kf["value"] == "MISSING"

    assert rev["timeline"] == []
    assert rev["contradictions"] == []
    for item in rev["missing_info"]:
        assert item["status"] == "MISSING"

    # 2. Draft on B only
    drf = draft_document(doc_ids=[DOC_B_ID], doc_type="bail_application")
    assert "error" not in drf
    drf_text = drf["draft_text"]
    assert "Vikram Sharma" not in drf_text
    assert "[MISSING: court name]" in drf_text
    assert "[MISSING: date of arrest]" in drf_text
    assert drf["footnotes"] == []

    # 3. Research on B only
    res = research_legal_issue("Bail under Section 439", doc_ids=[DOC_B_ID])
    assert res["statutes"] == []
    assert res["precedents"] == []
    assert "No relevant authority in the provided documents" in res["message"]

def test_tick_only_legal_doc_a():
    """Tick only A -> output only from A; zero content from B or C."""
    rev = review_case(doc_ids=[DOC_A_ID])
    assert "error" not in rev
    assert rev["title"] == "State v. Accused (Bail Order)"
    assert rev["sources_used"] == ["State v. Accused (Bail Order)"]
    assert "Chocolate Cake" not in str(rev)
    assert "sugar" not in str(rev)
    assert "cheque" not in str(rev)

def test_switching_selection_mid_chat():
    """Test switching selection mid-chat updates retrieval scope and prevents bleed."""
    session = "test_switching_session"

    # Turn 1: scoped to Bail Doc A
    ans1 = answer_query("What section is mentioned?", doc_ids=[DOC_A_ID], session_id=session)
    assert "Section" in ans1["answer"] or "Not found" in ans1["answer"]
    assert "cheque" not in ans1["answer"].lower()

    # Turn 2: switch scope to Cheque Notice C
    ans2 = answer_query("What is the matter about?", doc_ids=[DOC_C_ID], session_id=session)
    assert ans2["sources_used"] == ["Statutory Cheque Notice"]
    assert "flour" not in ans2["answer"].lower()

def test_deterministic_gate_blocks_out_of_scope_chunks():
    """Gate blocks chunks outside scope even if maliciously provided in candidate list."""
    candidate_claims = [
        {
            "id": "c1",
            "text": "The recipe requires two cups of flour.",
            "chunk_id": f"{DOC_B_ID}:p1:c0",
            "doc": "Chocolate Cake Recipe",
            "page": 1,
            "quote": "two cups of flour"
        }
    ]
    chunks = [
        {
            "chunk_id": f"{DOC_B_ID}:p1:c0",
            "doc_id": DOC_B_ID,
            "text": "The recipe requires two cups of flour.",
            "ocr": 0
        }
    ]

    # Scoped only to legal Doc A
    verified = run_critic_repair_loop(candidate_claims, chunks, scoped_doc_ids=[DOC_A_ID])
    assert len(verified) == 0
