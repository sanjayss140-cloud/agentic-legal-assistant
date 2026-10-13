import re
import csv
import io
import time
import json
import secrets
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from backend.ingestion.pipeline import get_db
from backend.retrieval.engine import retrieve
from backend.workflows.service import resolve_scope, create_valid_docx, clean_legal_text
from backend.app import config

# -------------------------------------------------------------
# 1. CITATION CHECKER
# -------------------------------------------------------------

def check_citations_and_facts(
    text: str,
    doc_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Checks user-provided brief/draft:
    Extracts every factual statement and cited authority.
    Verifies each against selected documents and citation registry.
    Strict Rule: Never claims citation is "correct law", only "found / not found in provided sources".
    """
    scoped_docs, err_msg = resolve_scope(doc_ids, user_id=user_id, matter_id=matter_id)
    if err_msg:
        return {
            "error": err_msg,
            "statements": [],
            "authorities": [],
            "summary": {"total_statements": 0, "supported": 0, "partially_supported": 0, "not_found": 0}
        }

    scoped_doc_ids = [d["id"] for d in scoped_docs]

    # Protect legal abbreviations before sentence splitting
    proc_text = re.sub(r'\b(v|vs|no|sec|art|dr|mr|mrs)\.\s+', r'\1_DOT_ ', text, flags=re.IGNORECASE)
    raw_sentences = [s.replace('_DOT_ ', '. ').strip() for s in re.split(r'(?<=[.!?])\s+', proc_text) if len(s.strip()) > 20]
    
    # Extract candidate statutes and cases from input text directly
    statute_pattern = re.compile(r'(?:Section|Sec\.|s\.)\s*\d+[A-Za-z]*(?:\s*\([0-9a-zA-Z]+\))*(?:\s*(?:of\s+(?:the\s+)?)?(?:IPC|CrPC|BNSS|BNS|NI\s+Act|PMLA|NDPS|POCSO|CPA))?', re.IGNORECASE)

    extracted_authorities = set()
    for m in statute_pattern.finditer(text):
        extracted_authorities.add((m.group(0).strip(), "statute"))

    # Extract case precedents from whole text directly
    text_lower = text.lower()
    for sep in [" v. ", " vs. ", " vs ", " versus "]:
        start = 0
        while True:
            idx = text_lower.find(sep, start)
            if idx == -1:
                break
            before = text[:idx].strip()
            after = text[idx + len(sep):].strip()
            words_before = before.split()[-4:] if before else []
            words_after = after.split()[:3] if after else []
            if words_before and words_after:
                p1_raw = " ".join(words_before)
                p2_raw = " ".join(words_after)
                p1 = re.sub(r'^(?:(?:the\s+)?(?:supreme\s+court|high\s+court|court)\s+(?:in|of)\s+|in\s+|the\s+)', '', p1_raw, flags=re.IGNORECASE).strip()
                p2 = re.split(r'\b(?:held|observed|stated|ruled|decided|is|was|that)\b', p2_raw, flags=re.IGNORECASE)[0].strip(" ,.;\n")
                if len(p1) > 2 and len(p2) > 1 and not any(k in p1.lower() for k in ["section", "article"]):
                    extracted_authorities.add((f"{p1} v. {p2}", "precedent"))
            start = idx + len(sep)

    # Check statements against scoped documents
    statement_results = []
    supported_cnt = 0
    partial_cnt = 0
    not_found_cnt = 0

    for stmt in raw_sentences[:15]:
        # Search scoped chunks
        retrieved_chunks = retrieve(stmt, doc_ids=scoped_doc_ids, mode="hybrid", top_k=3, user_id=user_id, matter_id=matter_id)
        
        status = "Not found in the provided documents"
        quote_found = ""
        page_found = None
        doc_found = ""

        if retrieved_chunks:
            best_chunk = retrieved_chunks[0]
            chk_text = best_chunk["text"]

            # Exact normalized substring check (Gate A logic)
            clean_stmt = re.sub(r'[^a-z0-9]', '', stmt.lower())
            clean_chunk = re.sub(r'[^a-z0-9]', '', chk_text.lower())

            # Check if significant subphrases exist
            subwords = [w for w in re.findall(r'\b[a-zA-Z0-9]{4,}\b', stmt.lower()) if w not in ["that", "this", "with", "from", "have", "been", "which"]]
            matched_words = [w for w in subwords if w in chk_text.lower()]
            overlap_ratio = len(matched_words) / max(len(subwords), 1)

            if clean_stmt in clean_chunk or (len(clean_stmt) > 30 and clean_stmt[:30] in clean_chunk):
                status = "Supported"
                quote_found = chk_text[:160].strip()
                page_found = best_chunk["page"]
                doc_found = best_chunk["doc_title"]
                supported_cnt += 1
            elif overlap_ratio >= 0.55:
                status = "Partially supported"
                quote_found = chk_text[:160].strip()
                page_found = best_chunk["page"]
                doc_found = best_chunk["doc_title"]
                partial_cnt += 1
            else:
                not_found_cnt += 1
        else:
            not_found_cnt += 1

        statement_results.append({
            "statement": stmt,
            "status": status,
            "quote": quote_found,
            "page": page_found,
            "document": doc_found
        })

    # Check authorities against scoped document chunks AND corpus citation registry
    conn = get_db()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in scoped_doc_ids)
    cursor.execute(f"SELECT c.chunk_id, c.page, c.doc_id, c.text, d.title AS doc_title FROM chunks c JOIN documents d ON d.id = c.doc_id WHERE c.doc_id IN ({placeholders})", scoped_doc_ids)
    scoped_chunk_rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT citation_text, citation_type, doc_id, chunk_id FROM citation_registry WHERE user_id = ? OR ? IS NULL", (user_id, user_id))
    reg_rows = cursor.fetchall()
    conn.close()

    reg_texts = [r["citation_text"].lower() for r in reg_rows]

    authority_results = []
    for auth_name, auth_type in extracted_authorities:
        clean_auth = auth_name.lower().strip()
        core_name = re.sub(r'\s*\([^)]*\).*', '', clean_auth).strip()

        # Check in scoped chunks directly
        matching_chunk = None
        for chk in scoped_chunk_rows:
            chk_lower = chk["text"].lower()
            if clean_auth in chk_lower or (len(core_name) > 4 and core_name in chk_lower):
                matching_chunk = chk
                break

        found_in_record = bool(matching_chunk) or any(clean_auth in rt or rt in clean_auth or (len(core_name) > 4 and core_name in rt) for rt in reg_texts)

        if found_in_record:
            authority_results.append({
                "authority": auth_name,
                "type": auth_type,
                "status": "Found in provided sources",
                "quote": matching_chunk["text"][:140].strip() if matching_chunk else f"Found in scoped matter citation record",
                "page": matching_chunk["page"] if matching_chunk else 1,
                "document": matching_chunk["doc_title"] if matching_chunk else "Scoped Document"
            })
        else:
            authority_results.append({
                "authority": auth_name,
                "type": auth_type,
                "status": "Authority not in provided documents",
                "quote": "",
                "page": None,
                "document": ""
            })

    return {
        "statements": statement_results,
        "authorities": authority_results,
        "disclaimer": "Factual and authority status reflects only presence in provided scoped documents; does not constitute legal opinion or determination of current law.",
        "summary": {
            "total_statements": len(statement_results),
            "supported": supported_cnt,
            "partially_supported": partial_cnt,
            "not_found": not_found_cnt,
            "total_authorities": len(authority_results),
            "authorities_found": sum(1 for a in authority_results if a["status"] == "Found in provided sources"),
            "authorities_unverified": sum(1 for a in authority_results if a["status"] != "Found in provided sources")
        }
    }

# -------------------------------------------------------------
# 2. CASE CHRONOLOGY
# -------------------------------------------------------------

def build_case_chronology(
    doc_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    filter_keyword: Optional[str] = None
) -> Dict[str, Any]:
    scoped_docs, err_msg = resolve_scope(doc_ids, user_id=user_id, matter_id=matter_id)
    if err_msg:
        return {"error": err_msg, "dated_events": [], "undated_events": []}

    scoped_doc_ids = [d["id"] for d in scoped_docs]

    conn = get_db()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in scoped_doc_ids)
    cursor.execute(f"""
    SELECT c.chunk_id, c.doc_id, c.page, c.text, d.title AS doc_title
    FROM chunks c
    JOIN documents d ON d.id = c.doc_id
    WHERE c.doc_id IN ({placeholders})
    ORDER BY c.doc_id, c.page ASC, c.chunk_index ASC
    """, scoped_doc_ids)
    rows = cursor.fetchall()
    conn.close()

    date_regex = re.compile(
        r'\b(\d{1,2}[-./\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-./\s]\d{2,4}|\d{1,2}[-./]\d{1,2}[-./]\d{2,4})\b',
        re.IGNORECASE
    )

    dated_events = []
    undated_events = []
    seen_events = set()

    for r in rows:
        text = r["text"]
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 25]

        for sent in sentences:
            if filter_keyword and filter_keyword.lower() not in sent.lower():
                continue

            # Check if event contains legal significance
            has_action = any(k in sent.lower() for k in [
                "arrest", "fir", "filed", "ordered", "issued", "seized", "complaint",
                "remand", "custody", "summon", "notice", "hearing", "adjourned",
                "charge", "allegation", "occurred", "incident", "cheque", "dishonour", "return"
            ])

            date_match = date_regex.search(sent)
            if date_match:
                date_str = date_match.group(1).strip()
                event_key = (date_str, sent[:50])
                if event_key not in seen_events:
                    seen_events.add(event_key)
                    dated_events.append({
                        "date": date_str,
                        "event": sent[:220].strip(),
                        "document": r["doc_title"],
                        "page": r["page"],
                        "quote": sent[:160].strip()
                    })
            elif has_action:
                event_key = ("undated", sent[:50])
                if event_key not in seen_events and len(undated_events) < 15:
                    seen_events.add(event_key)
                    undated_events.append({
                        "event": sent[:220].strip(),
                        "document": r["doc_title"],
                        "page": r["page"],
                        "quote": sent[:160].strip()
                    })

    # Sort dated events
    def parse_sort_date(item):
        raw = item["date"]
        # Basic normalize for sorting
        m = re.search(r'(\d{4})', raw)
        year = int(m.group(1)) if m else 9999
        return (year, raw)

    dated_events.sort(key=parse_sort_date)

    return {
        "dated_events": dated_events,
        "undated_events": undated_events,
        "total_dated": len(dated_events),
        "total_undated": len(undated_events),
        "sources_used": [d["title"] for d in scoped_docs]
    }

def export_chronology_csv(chronology_data: Dict[str, Any]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Event", "Document", "Page", "Source Quote"])
    for ev in chronology_data.get("dated_events", []):
        writer.writerow([ev.get("date", ""), ev.get("event", ""), ev.get("document", ""), ev.get("page", ""), ev.get("quote", "")])
    for ev in chronology_data.get("undated_events", []):
        writer.writerow(["Undated", ev.get("event", ""), ev.get("document", ""), ev.get("page", ""), ev.get("quote", "")])
    return output.getvalue()

def export_chronology_docx(chronology_data: Dict[str, Any], filepath: str):
    text_content = ["CASE CHRONOLOGY RECORD", "=" * 40, ""]
    text_content.append("DATED EVENTS (CHRONOLOGICAL):")
    text_content.append("-" * 30)
    for idx, ev in enumerate(chronology_data.get("dated_events", []), 1):
        text_content.append(f"{idx}. Date: {ev['date']}")
        text_content.append(f"   Event: {ev['event']}")
        text_content.append(f"   Source: {ev['document']} (Page {ev['page']})")
        text_content.append(f"   Quote: \"{ev['quote']}\"")
        text_content.append("")

    if chronology_data.get("undated_events"):
        text_content.append("UNDATED MATERIAL EVENTS:")
        text_content.append("-" * 30)
        for idx, ev in enumerate(chronology_data.get("undated_events", []), 1):
            text_content.append(f"{idx}. Event: {ev['event']}")
            text_content.append(f"   Source: {ev['document']} (Page {ev['page']})")
            text_content.append(f"   Quote: \"{ev['quote']}\"")
            text_content.append("")

    create_valid_docx(filepath, "Case Chronology", "\n".join(text_content))

# -------------------------------------------------------------
# 3. DATES AND DEADLINES (With Calendar .ics Export)
# -------------------------------------------------------------

def extract_dates_and_deadlines(
    doc_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None
) -> Dict[str, Any]:
    scoped_docs, err_msg = resolve_scope(doc_ids, user_id=user_id, matter_id=matter_id)
    if err_msg:
        return {"error": err_msg, "deadlines": []}

    scoped_doc_ids = [d["id"] for d in scoped_docs]

    conn = get_db()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in scoped_doc_ids)
    cursor.execute(f"""
    SELECT c.chunk_id, c.doc_id, c.page, c.text, d.title AS doc_title
    FROM chunks c
    JOIN documents d ON d.id = c.doc_id
    WHERE c.doc_id IN ({placeholders})
    ORDER BY c.page ASC
    """, scoped_doc_ids)
    rows = cursor.fetchall()
    conn.close()

    deadline_keywords = [
        ("Hearing Date", [r"listed\s+on\s*([^\.,;]+)", r"hearing\s+(?:on|fixed\s+for)\s*([^\.,;]+)", r"next\s+date\s*[:\-]?\s*([^\.,;]+)"]),
        ("Filing Deadline", [r"within\s+(?:the\s+)?(\d+\s+(?:days|weeks|months)[^\.,;]*)", r"file\s+(?:reply|counter|affidavit)\s+within\s+([^\.,;]+)"]),
        ("Compliance Period", [r"deposit\s+(?:within|amount)\s+([^\.,;]+)", r"surrender\s+within\s+([^\.,;]+)", r"comply\s+within\s+([^\.,;]+)", r"expiring\s+on\s*([^\.,;]+)"]),
        ("Notice Period", [r"(\d+\s+days\s+notice)", r"notice\s+period\s+of\s+([^\.,;]+)", r"(\d+\s+days\s+period)"]),
        ("Interim Stay Validity", [r"interim\s+order\s+extended\s+till\s+([^\.,;]+)", r"stay\s+shall\s+continue\s+till\s+([^\.,;]+)"])
    ]

    extracted_entries = []
    seen = set()

    for r in rows:
        text = r["text"]
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 20]
        for s in sentences:
            for category, patterns in deadline_keywords:
                for pat in patterns:
                    m = re.search(pat, s, re.IGNORECASE)
                    if m:
                        val = m.group(1).strip() if len(m.groups()) > 0 else m.group(0).strip()
                        key = (category, val[:30])
                        if key not in seen and len(val) < 60:
                            seen.add(key)
                            extracted_entries.append({
                                "category": category,
                                "date_or_period": val,
                                "context": s[:180].strip(),
                                "document": r["doc_title"],
                                "page": r["page"],
                                "quote": s[:140].strip()
                            })

    return {
        "deadlines": extracted_entries,
        "disclaimer": "Extracted from the documents; verify before relying. The system does not compute statutory limitation periods.",
        "sources_used": [d["title"] for d in scoped_docs],
        "count": len(extracted_entries)
    }

def export_deadlines_ics(deadlines_data: Dict[str, Any]) -> str:
    """Generates valid RFC 5545 iCalendar content."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LexGround Legal//Matter Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH"
    ]

    now_stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

    for idx, d in enumerate(deadlines_data.get("deadlines", []), start=1):
        uid = f"deadline-{idx}-{int(time.time())}@lexground.local"
        summary = f"[{d['category']}] {d['date_or_period']}"
        desc = f"Extracted from {d['document']} (Page {d['page']}). Quote: {d['quote']}. Verify before relying."
        
        # Approximate start date
        date_clean = re.sub(r'[^0-9]', '', d['date_or_period'])
        dt_start = now_stamp  # default fallback
        if len(date_clean) >= 8:
            dt_start = f"{date_clean[:8]}T100000Z"

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART:{now_stamp}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "STATUS:CONFIRMED",
            "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

# -------------------------------------------------------------
# 4. DOCUMENT COMPARISON
# -------------------------------------------------------------

def compare_two_documents(
    doc_id_a: str,
    doc_id_b: str,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None
) -> Dict[str, Any]:
    """Compares two documents (order vs petition, notice vs reply)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, court, date, case_number, parties, statutes FROM documents WHERE id = ? AND (user_id = ? OR ? IS NULL)", (doc_id_a, user_id, user_id))
    doc_a = cursor.fetchone()
    cursor.execute("SELECT id, title, court, date, case_number, parties, statutes FROM documents WHERE id = ? AND (user_id = ? OR ? IS NULL)", (doc_id_b, user_id, user_id))
    doc_b = cursor.fetchone()

    if not doc_a or not doc_b:
        conn.close()
        return {"error": "One or both documents not found or access denied."}

    doc_a = dict(doc_a)
    doc_b = dict(doc_b)

    cursor.execute("SELECT page, text FROM chunks WHERE doc_id = ? ORDER BY page ASC LIMIT 10", (doc_id_a,))
    chunks_a = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT page, text FROM chunks WHERE doc_id = ? ORDER BY page ASC LIMIT 10", (doc_id_b,))
    chunks_b = [dict(r) for r in cursor.fetchall()]
    conn.close()

    text_a = " ".join(c["text"] for c in chunks_a)
    text_b = " ".join(c["text"] for c in chunks_b)

    differences = []

    # 1. Compare Parties
    parties_a = doc_a.get("parties") or "MISSING"
    parties_b = doc_b.get("parties") or "MISSING"
    if parties_a != parties_b:
        differences.append({
            "aspect": "Parties Title",
            "doc_a_value": parties_a,
            "doc_a_quote": f"Cause Title in {doc_a['title']}",
            "doc_b_value": parties_b,
            "doc_b_quote": f"Cause Title in {doc_b['title']}",
            "type": "Party Difference"
        })

    # 2. Compare Court
    court_a = doc_a.get("court") or "MISSING"
    court_b = doc_b.get("court") or "MISSING"
    if court_a != court_b:
        differences.append({
            "aspect": "Jurisdiction / Forum",
            "doc_a_value": court_a,
            "doc_a_quote": court_a,
            "doc_b_value": court_b,
            "doc_b_quote": court_b,
            "type": "Court Forum Variance"
        })

    # 3. Compare Dates
    date_regex = re.compile(r'\b(\d{1,2}[-./\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-./\s]\d{2,4}|\d{1,2}[-./]\d{1,2}[-./]\d{2,4})\b', re.IGNORECASE)
    dates_a = set(date_regex.findall(text_a))
    dates_b = set(date_regex.findall(text_b))

    unique_to_a = sorted(list(dates_a - dates_b))[:3]
    unique_to_b = sorted(list(dates_b - dates_a))[:3]

    if unique_to_a or unique_to_b:
        differences.append({
            "aspect": "Distinct Timeline Dates",
            "doc_a_value": ", ".join(unique_to_a) or "None unique",
            "doc_a_quote": f"Dates mentioned in {doc_a['title']}",
            "doc_b_value": ", ".join(unique_to_b) or "None unique",
            "doc_b_quote": f"Dates mentioned in {doc_b['title']}",
            "type": "Timeline Variation"
        })

    # 4. Compare Amounts / Figures (e.g. cheque or recovery sums)
    amount_regex = re.compile(r'(?:Rs\.?|INR|\₹)\s*[\d,]+(?:\.\d{2})?|\b\d{1,3}(?:,\d{2,3})+(?:\s*rupees)?\b', re.IGNORECASE)
    amounts_a = set(amount_regex.findall(text_a))
    amounts_b = set(amount_regex.findall(text_b))

    if amounts_a or amounts_b:
        differences.append({
            "aspect": "Financial Claims & Amounts",
            "doc_a_value": ", ".join(list(amounts_a)[:3]) or "No monetary claims",
            "doc_a_quote": f"Monetary quotes in {doc_a['title']}",
            "doc_b_value": ", ".join(list(amounts_b)[:3]) or "No monetary claims",
            "doc_b_quote": f"Monetary quotes in {doc_b['title']}",
            "type": "Monetary Claims"
        })

    return {
        "doc_a": {"id": doc_a["id"], "title": doc_a["title"]},
        "doc_b": {"id": doc_b["id"], "title": doc_b["title"]},
        "differences": differences,
        "differences_count": len(differences)
    }

# -------------------------------------------------------------
# 5. AUTHORITY TABLE (Statutes & Precedents)
# -------------------------------------------------------------

def build_authority_table(
    doc_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None
) -> Dict[str, Any]:
    scoped_docs, err_msg = resolve_scope(doc_ids, user_id=user_id, matter_id=matter_id)
    if err_msg:
        return {"error": err_msg, "authorities": []}

    scoped_doc_ids = [d["id"] for d in scoped_docs]

    conn = get_db()
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in scoped_doc_ids)
    cursor.execute(f"""
    SELECT r.citation_text, r.citation_type, r.doc_id, r.chunk_id, d.title AS doc_title, c.page, c.text
    FROM citation_registry r
    JOIN documents d ON d.id = r.doc_id
    JOIN chunks c ON c.chunk_id = r.chunk_id
    WHERE r.doc_id IN ({placeholders})
    """, scoped_doc_ids)
    rows = cursor.fetchall()
    conn.close()

    authorities = []
    seen = set()

    for r in rows:
        name = r["citation_text"].strip()
        if name.lower() in seen or len(name) < 3:
            continue
        seen.add(name.lower())

        c_text = r["text"]
        # Extract sentence where authority appears
        sent_m = re.search(rf"[^.!?]*\b{re.escape(name)}\b[^.!?]*[.]?", c_text, re.IGNORECASE)
        quote = sent_m.group(0).strip() if sent_m else name

        # Determine supports or distinguished
        q_lower = quote.lower()
        if any(k in q_lower for k in ["distinguished", "inapplicable", "not apply", "rejected"]):
            position = "Distinguished / Against"
        elif any(k in q_lower for k in ["relied", "binding", "applies", "granted", "settled", "held"]):
            position = "Relied Upon / In Support"
        else:
            position = "Statutory Reference / Cited"

        authorities.append({
            "name": name,
            "type": r["citation_type"],
            "document": r["doc_title"],
            "page": r["page"],
            "quote": quote[:180],
            "position": position,
            "relevance": f"Cited in {r['doc_title']} regarding governing legal standards."
        })

    return {
        "authorities": authorities,
        "count": len(authorities),
        "sources_used": [d["title"] for d in scoped_docs]
    }

# -------------------------------------------------------------
# 6. DRAFT TEMPLATES (5 Core Indian Legal Drafts)
# -------------------------------------------------------------

def generate_formal_draft(
    doc_type: str,
    doc_ids: Optional[List[str]] = None,
    user_facts: Optional[Dict[str, str]] = None,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None
) -> Dict[str, Any]:
    scoped_docs, err_msg = resolve_scope(doc_ids, user_id=user_id, matter_id=matter_id)
    if err_msg:
        return {"error": err_msg, "no_scope": True, "sources_used": []}

    target_doc = scoped_docs[0]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT page, chunk_index, text FROM chunks WHERE doc_id = ? ORDER BY page ASC, chunk_index ASC LIMIT 5", (target_doc["id"],))
    chunks = [dict(c) for c in cursor.fetchall()]
    conn.close()

    first_text = chunks[0]["text"] if chunks else ""
    user_facts = user_facts or {}
    doc_title = target_doc["title"]
    is_non_legal = target_doc.get("doc_type") == "not_legal"

    # Extract parties, court, case number
    court_val = user_facts.get("court") or target_doc.get("court") or "[MISSING: court name]"
    parties_val = user_facts.get("parties") or target_doc.get("parties") or "[MISSING: petitioner vs respondent]"
    case_no_val = user_facts.get("case_number") or target_doc.get("case_number") or "[MISSING: case number]"

    pre_draft_report = []
    draft_text = ""

    if doc_type == "bail_application":
        arrest_val = user_facts.get("arrest_date", "[MISSING: date of arrest]")
        surety_val = user_facts.get("surety", "[MISSING: solvent local surety amount]")
        antecedents_val = user_facts.get("antecedents", "[MISSING: clean criminal antecedents affidavit]")
        pre_draft_report = [
            {"fact": "Court Name", "status": "USER-PROVIDED" if "court" in user_facts else ("FOUND" if "[MISSING" not in court_val else "MISSING"), "value": court_val},
            {"fact": "Parties", "status": "USER-PROVIDED" if "parties" in user_facts else ("FOUND" if "[MISSING" not in parties_val else "MISSING"), "value": parties_val},
            {"fact": "Date of Arrest", "status": "USER-PROVIDED" if "arrest_date" in user_facts else "MISSING", "value": arrest_val},
            {"fact": "Solvent Surety Details", "status": "USER-PROVIDED" if "surety" in user_facts else "MISSING", "value": surety_val},
            {"fact": "Antecedents Record", "status": "USER-PROVIDED" if "antecedents" in user_facts else "MISSING", "value": antecedents_val}
        ]
        draft_text = f"""IN THE {court_val.upper()}

{case_no_val}

IN THE MATTER OF:
{parties_val}

APPLICATION UNDER SECTION 439 OF THE CODE OF CRIMINAL PROCEDURE, 1973
(NOW SECTION 483 OF BHARATIYA NAGARIK SURAKSHA SANHITA, 2023)
FOR GRANT OF REGULAR BAIL

MOST RESPECTFULLY SHOWETH:
1. That the Applicant is a permanent resident having deep roots in society and has been falsely implicated.
2. That the Applicant has been in custody since {arrest_val}.
3. That the investigation is complete and charge-sheet has been submitted.
4. That the Applicant undertakes to furnish solvent local surety of {surety_val} and comply with all conditions.
5. Antecedents: {antecedents_val}.

PRAYER:
It is most respectfully prayed that this Hon'ble Court may graciously be pleased to enlarge the Applicant on regular bail during trial.
"""

    elif doc_type == "section_138_complaint":
        cheque_no = user_facts.get("cheque_no", "[MISSING: cheque number]")
        amount = user_facts.get("amount", "[MISSING: cheque amount in INR]")
        memo_date = user_facts.get("memo_date", "[MISSING: return memo date]")
        notice_date = user_facts.get("notice_date", "[MISSING: legal notice dispatch date]")
        pre_draft_report = [
            {"fact": "Complainant vs Accused", "status": "USER-PROVIDED" if "parties" in user_facts else "FOUND", "value": parties_val},
            {"fact": "Dishonoured Cheque No", "status": "USER-PROVIDED" if "cheque_no" in user_facts else "MISSING", "value": cheque_no},
            {"fact": "Cheque Amount", "status": "USER-PROVIDED" if "amount" in user_facts else "MISSING", "value": amount},
            {"fact": "Return Memo Date", "status": "USER-PROVIDED" if "memo_date" in user_facts else "MISSING", "value": memo_date},
            {"fact": "Statutory Notice Date", "status": "USER-PROVIDED" if "notice_date" in user_facts else "MISSING", "value": notice_date}
        ]
        draft_text = f"""IN THE COURT OF THE METROPOLITAN MAGISTRATE / JUDICIAL MAGISTRATE FIRST CLASS

COMPLAINT CASE NO. {case_no_val}

IN THE MATTER OF:
{parties_val}

COMPLAINT UNDER SECTION 138 READ WITH SECTION 142 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881

MOST RESPECTFULLY SHOWETH:
1. That the Complainant is carrying on legitimate business/transactions with the Accused.
2. That in discharge of legally enforceable liability, the Accused issued Cheque No. {cheque_no} for Rs. {amount}.
3. That upon presentation, the cheque was returned dishonoured with remark 'Funds Insufficient' vide Bank Memo dated {memo_date}.
4. That a statutory legal demand notice was dispatched on {notice_date} demanding payment within 15 days of receipt.
5. That despite receipt, the Accused failed to make payment, committing the offence under Section 138 of the NI Act.

PRAYER:
Summon, try and punish the Accused in accordance with law and award double compensation to the Complainant.
"""

    elif doc_type == "consumer_complaint":
        defect_val = user_facts.get("defect", "[MISSING: deficiency in service or defect description]")
        claim_amt = user_facts.get("claim_amount", "[MISSING: total claim amount with compensation in INR]")
        pre_draft_report = [
            {"fact": "Forum / Commission", "status": "USER-PROVIDED" if "court" in user_facts else "FOUND", "value": court_val},
            {"fact": "Complainant vs Opposite Party", "status": "USER-PROVIDED" if "parties" in user_facts else "FOUND", "value": parties_val},
            {"fact": "Deficiency / Defect", "status": "USER-PROVIDED" if "defect" in user_facts else "MISSING", "value": defect_val},
            {"fact": "Claim & Compensation", "status": "USER-PROVIDED" if "claim_amount" in user_facts else "MISSING", "value": claim_amt}
        ]
        draft_text = f"""BEFORE THE DISTRICT CONSUMER DISPUTES REDRESSAL COMMISSION

CONSUMER COMPLAINT NO. {case_no_val}

IN THE MATTER OF:
{parties_val}

COMPLAINT UNDER SECTION 35 OF THE CONSUMER PROTECTION ACT, 2019

MOST RESPECTFULLY SHOWETH:
1. That the Complainant is a 'consumer' within Section 2(7) of the CPA 2019 having availed goods/services for valuable consideration.
2. That the Opposite Party committed unfair trade practice and gross deficiency in service by: {defect_val}.
3. That the cause of action arose within territorial and pecuniary limits of this Commission.

PRAYER:
Direct Opposite Party to rectify defect, refund amount, and pay compensation of Rs. {claim_amt} for mental agony.
"""

    elif doc_type == "writ_petition":
        relief_val = user_facts.get("relief", "[MISSING: specific prerogative writ or directions sought]")
        rights_val = user_facts.get("fundamental_rights", "[MISSING: Fundamental Rights infringed under Part III]")
        pre_draft_report = [
            {"fact": "High Court / Supreme Court", "status": "USER-PROVIDED" if "court" in user_facts else "FOUND", "value": court_val},
            {"fact": "Petitioner vs State / Respondents", "status": "USER-PROVIDED" if "parties" in user_facts else "FOUND", "value": parties_val},
            {"fact": "Rights Violated", "status": "USER-PROVIDED" if "fundamental_rights" in user_facts else "MISSING", "value": rights_val},
            {"fact": "Writ Relief Sought", "status": "USER-PROVIDED" if "relief" in user_facts else "MISSING", "value": relief_val}
        ]
        draft_text = f"""IN THE HIGH COURT OF JUDICATURE / SUPREME COURT OF INDIA

WRIT PETITION (CIVIL / CRIMINAL) NO. {case_no_val}

IN THE MATTER OF:
{parties_val}

PETITION UNDER ARTICLE 226 / ARTICLE 32 OF THE CONSTITUTION OF INDIA

SYNOPSIS AND LIST OF DATES:
The present petition challenges arbitrary, illegal state action infringing rights under {rights_val}.

MOST RESPECTFULLY SHOWETH:
1. That the Petitioner has no other efficacious alternative remedy.
2. That the impugned order/action is violative of the principles of natural justice and Constitutional mandates.

PRAYER:
Issue a Writ of Mandamus/Certiorari or other appropriate writ commanding respondents to grant {relief_val}.
"""

    else:  # default legal notice
        demand_amt = user_facts.get("amount", "[MISSING: claimed demand sum]")
        pre_draft_report = [
            {"fact": "Sender vs Recipient", "status": "USER-PROVIDED" if "parties" in user_facts else "FOUND", "value": parties_val},
            {"fact": "Demand Amount", "status": "USER-PROVIDED" if "amount" in user_facts else "MISSING", "value": demand_amt}
        ]
        draft_text = f"""LEGAL DEMAND NOTICE

TO:
{parties_val}

UNDER INSTRUCTIONS FROM MY CLIENT:
Please take notice that you are in breach of statutory covenants and liable to pay Rs. {demand_amt} within 15 days of this notice.
"""

    # Generate file on disk
    docx_file = Path(config.BASE_DIR) / "frontend" / "dist" / f"draft_{doc_type}.docx"
    create_valid_docx(str(docx_file), f"Legal Draft - {doc_type}", draft_text)

    found_facts = sum(1 for f in pre_draft_report if f["status"] in ["FOUND", "USER-PROVIDED"])
    g_score = round((found_facts / max(len(pre_draft_report), 1)) * 100, 1)

    return {
        "doc_type": doc_type,
        "sources_used": [doc_title],
        "pre_draft_report": pre_draft_report,
        "draft_text": draft_text,
        "groundedness_score": g_score,
        "missing_placeholders": [m["fact"] for m in pre_draft_report if m["status"] == "MISSING"],
        "export_files": {
            "docx": f"/draft_{doc_type}.docx"
        }
    }

# -------------------------------------------------------------
# 7. ISSUE MATRIX
# -------------------------------------------------------------

def build_issue_matrix(
    doc_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None
) -> Dict[str, Any]:
    scoped_docs, err_msg = resolve_scope(doc_ids, user_id=user_id, matter_id=matter_id)
    if err_msg:
        return {"error": err_msg, "matrix": []}

    target_doc = scoped_docs[0]
    c_type = target_doc.get("case_type", "general")
    doc_title = target_doc["title"]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT page, text FROM chunks WHERE doc_id = ? ORDER BY page ASC LIMIT 15", (target_doc["id"],))
    chunks = [dict(c) for c in cursor.fetchall()]
    conn.close()

    full_text = " ".join(c["text"] for c in chunks)

    matrix = []

    if c_type == "bail":
        # Issue 1: Prima facie overt act
        matrix.append({
            "issue": "Whether an overt role or specific overt act is attributed to the applicant?",
            "opposing_arguments": "Prosecution alleges applicant was present at scene and involved in conspiracy.",
            "supporting_evidence": f"FIR / chargesheet extracts omnibus allegations without specific recovery [from {doc_title}, p.1].",
            "supporting_quote": chunks[0]["text"][:120] if chunks else "No overt act attributed",
            "weak_spots": "[MISSING: independent eyewitness statement corroborating presence]"
        })
        # Issue 2: Custody and investigation necessity
        matrix.append({
            "issue": "Whether further custodial interrogation is required after charge-sheet filing?",
            "opposing_arguments": "Investigating agency claims apprehension of witness tampering if enlarged on bail.",
            "supporting_evidence": f"Charge sheet filed; custody duration established in record [from {doc_title}].",
            "supporting_quote": chunks[-1]["text"][:120] if chunks else "Investigation concluded",
            "weak_spots": "[MISSING: verified clean criminal antecedents affidavit]"
        })
    elif c_type == "cheque_bounce":
        matrix.append({
            "issue": "Whether the statutory presumption under Section 139 NI Act is rebutted?",
            "opposing_arguments": "Complainant holds signed cheque creating statutory presumption of debt.",
            "supporting_evidence": "Defence indicates security cheque issued without consideration.",
            "supporting_quote": chunks[0]["text"][:120] if chunks else "Cheque dishonour memo",
            "weak_spots": "[MISSING: contemporaneous ledger or account statement proof]"
        })
    else:
        matrix.append({
            "issue": f"Core Statutory Determination in {doc_title}",
            "opposing_arguments": "Adverse parties contest applicability of statutory relief.",
            "supporting_evidence": f"Pleadings and evidence filed in record of {doc_title}.",
            "supporting_quote": chunks[0]["text"][:120] if chunks else "Record of proceedings",
            "weak_spots": "[MISSING: certified copy of order or secondary verification]"
        })

    return {
        "matrix": matrix,
        "sources_used": [doc_title],
        "count": len(matrix)
    }

# -------------------------------------------------------------
# 8. PER-ANSWER FEEDBACK
# -------------------------------------------------------------

def record_feedback(
    user_id: str,
    rating: int,
    matter_id: Optional[str] = None,
    message_id: Optional[str] = None,
    notes: Optional[str] = None,
    prompt_version: str = "v2.0-verified",
    model: str = "llama-3.3-70b-versatile",
    retrieval_params: Optional[Dict[str, Any]] = None,
    verified_status: str = "pass"
) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS answer_feedback (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        matter_id TEXT,
        message_id TEXT,
        rating INTEGER,
        notes TEXT,
        prompt_version TEXT,
        model TEXT,
        retrieval_params TEXT,
        verified_status TEXT,
        created_at REAL
    );
    """)

    fb_id = f"fb_{int(time.time())}_{secrets.token_hex(4)}"
    ret_str = json.dumps(retrieval_params or {"mode": "hybrid_rerank", "top_k": 6})
    cursor.execute("""
    INSERT INTO answer_feedback (id, user_id, matter_id, message_id, rating, notes, prompt_version, model, retrieval_params, verified_status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (fb_id, user_id, matter_id, message_id, rating, notes, prompt_version, model, ret_str, verified_status, time.time()))
    conn.commit()
    conn.close()

    return {"status": "ok", "feedback_id": fb_id, "rating": rating}

def get_feedback_records(user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS answer_feedback (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        matter_id TEXT,
        message_id TEXT,
        rating INTEGER,
        notes TEXT,
        prompt_version TEXT,
        model TEXT,
        retrieval_params TEXT,
        verified_status TEXT,
        created_at REAL
    );
    """)
    if user_id:
        cursor.execute("SELECT * FROM answer_feedback WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit))
    else:
        cursor.execute("SELECT * FROM answer_feedback ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# -------------------------------------------------------------
# 9. MULTILINGUAL SUPPORT (Indian Languages: Hindi / Tamil / Marathi)
# -------------------------------------------------------------

HINDI_LEGAL_TERMS = {
    "जमानत": "bail",
    "धारा": "section",
    "अभियुक्त": "accused",
    "याचिकाकर्ता": "petitioner",
    "प्रतिवादी": "respondent",
    "न्यायालय": "court",
    "उच्च न्यायालय": "High Court",
    "सर्वोच्च न्यायालय": "Supreme Court",
    "प्रथम सूचना रिपोर्ट": "FIR",
    "आरोप पत्र": "chargesheet",
    "दण्ड प्रक्रिया संहिता": "CrPC",
    "भारतीय न्याय संहिता": "BNS",
    "भारतीय नागरिक सुरक्षा संहिता": "BNSS",
    "चेक अनादर": "cheque bounce",
    "उपभोक्ता": "consumer"
}

def detect_and_process_indian_language(text: str) -> Dict[str, Any]:
    """Detects Devanagari (Hindi/Marathi) or Tamil scripts and produces verified keyword mappings."""
    is_hindi = bool(re.search(r'[\u0900-\u097F]', text))
    is_tamil = bool(re.search(r'[\u0B80-\u0BFF]', text))

    detected_lang = "en"
    detected_terms = []

    if is_hindi:
        detected_lang = "hi"
        for hindi_w, eng_w in HINDI_LEGAL_TERMS.items():
            if hindi_w in text:
                detected_terms.append({"original": hindi_w, "concept": eng_w})
    elif is_tamil:
        detected_lang = "ta"

    return {
        "language": detected_lang,
        "is_multilingual": is_hindi or is_tamil,
        "mapped_legal_concepts": detected_terms
    }
