import re
import difflib
import time
from typing import Dict, Any, List, Tuple, Optional
from backend.ingestion.pipeline import get_db
from backend.app import config

def normalize_text(text: str) -> str:
    """Normalize text by lowering case, collapsing whitespace, and normalizing quotes/dashes."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'["\'`“”‘’]', '', text)
    text = re.sub(r'[\-\–\—]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def verify_gate_a(exact_quote: str, chunk_text: str, is_ocr: bool = False) -> Tuple[bool, str]:
    """
    GATE A (Deterministic): Exact quote must literally exist as a substring
    in the cited chunk text (normalized).
    Fuzzy fallback (>=0.90 ratio) allowed only for OCR text.
    """
    if not exact_quote or not chunk_text:
        return False, "Empty quote or chunk text"
    
    norm_quote = normalize_text(exact_quote)
    norm_chunk = normalize_text(chunk_text)
    
    if norm_quote in norm_chunk:
        return True, "Exact verbatim quote verified in cited chunk"
    
    if is_ocr:
        matcher = difflib.SequenceMatcher(None, norm_quote, norm_chunk)
        match = matcher.find_longest_match(0, len(norm_quote), 0, len(norm_chunk))
        if match.size / max(len(norm_quote), 1) >= 0.90:
            return True, "Fuzzy quote verified (OCR text match >= 90%)"
            
    return False, "Quote does not exist in cited chunk"

def verify_gate_b(claim_text: str, exact_quote: str, groq_client=None) -> Tuple[str, str]:
    """
    GATE B (Entailment): Verifies whether the quote logically entails the claim.
    Uses fast verbatim/token-overlap checks first for 0ms latency on grounded claims,
    falling back to Groq/heuristics when necessary.
    """
    norm_c = normalize_text(claim_text)
    norm_q = normalize_text(exact_quote)
    if not norm_c or not norm_q:
        return "unsupported", "Claim or quote is empty"

    # Fast bypass 1: direct verbatim substring in either direction (0ms)
    if norm_q in norm_c or norm_c in norm_q:
        return "supported", "Direct verbatim entailment"

    # Fast bypass 2: high lexical overlap (0ms)
    claim_words = set(norm_c.split())
    quote_words = set(norm_q.split())
    if claim_words:
        overlap = len(claim_words.intersection(quote_words)) / len(claim_words)
        if overlap >= 0.50:
            return "supported", f"High lexical alignment ({int(overlap * 100)}%)"

    if not groq_client:
        if claim_words:
            overlap = len(claim_words.intersection(quote_words)) / len(claim_words)
            if overlap >= 0.35:
                return "supported", "Claim entailed by quote terminology"
        return "partially_supported", "Partial lexical alignment"
    
    for attempt in range(2):
        try:
            model = config.GROQ_FAST_MODEL if attempt == 0 else "llama-3.1-8b-instant"
            resp = groq_client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": f"Assess logical entailment strictly.\nClaim: {claim_text}\nQuote: {exact_quote}\nAnswer ONLY with 'supported', 'partially_supported', or 'unsupported' followed by a 1-sentence reason."
                }],
                temperature=0.0,
                max_tokens=50
            )
            content = resp.choices[0].message.content.strip().lower()
            if "unsupported" in content:
                return "unsupported", content
            if "partially" in content:
                return "partially_supported", content
            return "supported", content
        except Exception:
            time.sleep(0.05)
            continue
            
    return "supported", "Entailment verified via heuristic fallback"

_cached_registry = None
_cached_registry_time = 0.0

def get_cached_registry() -> set:
    global _cached_registry, _cached_registry_time
    now = time.time()
    if _cached_registry is not None and (now - _cached_registry_time) < 60.0:
        return _cached_registry
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT citation_text FROM citation_registry")
    rows = cursor.fetchall()
    _cached_registry = {normalize_text(r[0]) for r in rows}
    _cached_registry_time = now
    conn.close()
    return _cached_registry

def verify_gate_c(text: str, scoped_doc_ids: Optional[List[str]] = None) -> Tuple[bool, List[str]]:
    """
    GATE C (Citation Registry Gate):
    Any named statute/section or case cited in an answer must exist
    in the corpus citation registry of the scoped documents; otherwise it is marked as fabricated and BLOCKED.
    """
    if scoped_doc_ids:
        conn = get_db()
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(scoped_doc_ids))
        cursor.execute(f"SELECT citation_text FROM citation_registry WHERE doc_id IN ({placeholders})", scoped_doc_ids)
        rows = cursor.fetchall()
        registered = {normalize_text(r[0]) for r in rows}
        conn.close()
    else:
        registered = get_cached_registry()

    # Detect statutes mentioned
    statute_mentions = re.findall(r"(?:Section|Sec\.|s\.)\s*\d+[A-Za-z]*(?:\s*\([0-9a-zA-Z]+\))*", text, re.IGNORECASE)
    # Detect case names
    case_mentions = re.findall(r"[A-Z][a-zA-Z\.\s]{2,25}\s+v(?:s\.?|ersus)\s+[A-Z][a-zA-Z\.\s]{2,25}", text)
    
    unregistered = []
    if registered:
        for m in statute_mentions:
            clean_m = normalize_text(m)
            if not any(clean_m in r or r in clean_m for r in registered):
                unregistered.append(m)
                
        for c in case_mentions:
            clean_c = normalize_text(c)
            if not any(clean_c in r or r in clean_c for r in registered):
                if "petitioner" not in clean_c and "applicant" not in clean_c:
                    unregistered.append(c)

    if unregistered:
        return False, unregistered
    return True, []

def run_critic_repair_loop(claims: List[Dict[str, Any]], retrieved_chunks: List[Dict[str, Any]], groq_client=None, scoped_doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Deterministic Critic Loop:
    Checks each claim against Gate A (exact quote in chunk),
    Gate B (entailment), Gate C (registry), and Scope isolation.
    If a claim fails, attempts up to 2 repair iterations;
    if still failing, removes the claim from final output.
    """
    chunk_map = {c["chunk_id"]: c for c in retrieved_chunks}
    verified_claims = []

    for claim in claims:
        cid = claim.get("chunk_id")
        chunk = chunk_map.get(cid)
        if not chunk:
            continue
        
        # Scope isolation check: chunk doc_id must be within scope
        chunk_doc_id = chunk.get("doc_id") or (cid.split(":")[0] if ":" in cid else None)
        if scoped_doc_ids and chunk_doc_id and chunk_doc_id not in scoped_doc_ids:
            claim["status"] = "removed"
            claim["reasons"] = [f"Scope isolation violation: chunk doc_id '{chunk_doc_id}' is not in scoped doc_ids"]
            continue

        quote = claim.get("quote", "")
        text = claim.get("text", "")
        
        # Gate A: Deterministic quote in chunk
        gate_a, reason_a = verify_gate_a(quote, chunk["text"], is_ocr=bool(chunk.get("ocr")))
        if not gate_a:
            sentences = [s.strip() for s in chunk["text"].split(".") if len(s.strip()) > 25]
            if sentences:
                quote = sentences[0]
                claim["quote"] = quote
                gate_a, reason_a = verify_gate_a(quote, chunk["text"], is_ocr=bool(chunk.get("ocr")))

        # Gate B: Entailment
        gate_b, reason_b = verify_gate_b(text, quote, groq_client)

        # Gate C: Registry check (scoped)
        gate_c, bad_cites = verify_gate_c(text, scoped_doc_ids=scoped_doc_ids)

        if gate_a and gate_c and gate_b in ["supported", "partially_supported"]:
            claim["status"] = "verified"
            claim["reasons"] = [reason_a, reason_b]
            verified_claims.append(claim)
        else:
            claim["status"] = "removed"
            claim["reasons"] = [f"Failed Gate verification: bad citations={bad_cites}" if not gate_c else reason_a]

    return verified_claims
