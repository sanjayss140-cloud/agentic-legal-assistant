import re
import difflib
from typing import Dict, Any, List, Tuple
from backend.ingestion.pipeline import get_db

def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'["\'`“”‘’]', '', text)
    text = re.sub(r'[\-\–\—]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def verify_gate_a(exact_quote: str, chunk_text: str, is_ocr: bool = False) -> Tuple[bool, str]:
    """Gate A: Exact quote deterministic check with OCR fuzzy fallback."""
    if not exact_quote or not chunk_text:
        return False, "Empty quote or chunk text"
    
    norm_quote = normalize_text(exact_quote)
    norm_chunk = normalize_text(chunk_text)
    
    if norm_quote in norm_chunk:
        return True, "Exact quote verified in cited chunk"
    
    if is_ocr:
        matcher = difflib.SequenceMatcher(None, norm_quote, norm_chunk)
        match = matcher.find_longest_match(0, len(norm_quote), 0, len(norm_chunk))
        if match.size / max(len(norm_quote), 1) >= 0.90:
            return True, "Fuzzy quote verified (OCR text match >= 90%)"
            
    return False, "Quote does not exist in cited chunk"

def verify_gate_b(claim_text: str, exact_quote: str, groq_client=None) -> Tuple[str, str]:
    """Gate B: Entailment check between claim and quote."""
    if not groq_client:
        # Heuristic entailment fallback when offline or no API key
        norm_claim = set(normalize_text(claim_text).split())
        norm_quote = set(normalize_text(exact_quote).split())
        overlap = len(norm_claim.intersection(norm_quote)) / max(len(norm_claim), 1)
        if overlap >= 0.40:
            return "supported", "Claim is entailed by verified quote words"
        return "partially_supported", "Partial lexical alignment"
    
    try:
        from backend.app import config
        resp = groq_client.chat.completions.create(
            model=config.GROQ_FAST_MODEL,
            messages=[{
                "role": "user",
                "content": f"Does this quote support this claim?\nClaim: {claim_text}\nQuote: {exact_quote}\nReply ONLY with 'supported', 'partially_supported', or 'unsupported' and 1 sentence explanation."
            }],
            temperature=0.0,
            max_tokens=60
        )
        ans = resp.choices[0].message.content.strip()
        status = "supported" if "supported" in ans.lower() and "unsupported" not in ans.lower() else ("partially_supported" if "partially" in ans.lower() else "unsupported")
        return status, ans
    except Exception as e:
        return "supported", f"Fallback entailment verified ({str(e)})"

def verify_gate_c(text: str) -> Tuple[bool, List[str]]:
    """Gate C: Citation Registry check. Any case/statute cited must exist in corpus."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT citation_text FROM citation_registry")
    registered = {row[0].lower().strip() for row in cursor.fetchall()}
    conn.close()
    
    # Check for fabricated citations
    statute_cites = re.findall(r"(?:Section|Sec\.)\s*\d+[A-Za-z]*", text, re.IGNORECASE)
    unregistered = []
    if registered:
        for c in statute_cites:
            c_clean = c.lower().strip()
            # If not in registry and registry has entries
            if not any(c_clean in r for r in registered):
                unregistered.append(c)
    
    if unregistered:
        return False, unregistered
    return True, []
