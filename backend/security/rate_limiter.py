import os
import time
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
from fastapi import Request, HTTPException, Depends
from backend.ingestion.pipeline import get_db

# Configurable quotas
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "60"))
MAX_DOCS_PER_MATTER = int(os.getenv("MAX_DOCS_PER_MATTER", "50"))
DAILY_TOKEN_BUDGET = int(os.getenv("DAILY_TOKEN_BUDGET", "100000"))

# In-memory storage for sliding windows and daily usage
_user_requests: Dict[str, List[float]] = defaultdict(list)
_daily_tokens: Dict[Tuple[str, str], int] = defaultdict(int)  # (user_id, YYYY-MM-DD) -> token_count

def reset_rate_limits():
    """Resets in-memory rate limiters (primarily for test fixtures)."""
    _user_requests.clear()
    _daily_tokens.clear()

def check_rate_limit(user_id: str, rpm_limit: Optional[int] = None) -> Tuple[bool, int, str]:
    """
    Checks per-user RPM using a sliding 60-second window.
    Returns: (is_allowed, retry_after_seconds, message)
    """
    limit = rpm_limit if rpm_limit is not None else RATE_LIMIT_RPM
    now = time.time()
    window_start = now - 60.0

    # Prune timestamps older than 60s
    reqs = [t for t in _user_requests[user_id] if t > window_start]
    _user_requests[user_id] = reqs

    if len(reqs) >= limit:
        # Earliest request within window determines retry-after
        oldest_in_window = reqs[0]
        retry_after = max(1, int(60.0 - (now - oldest_in_window)))
        return False, retry_after, f"Rate limit of {limit} requests per minute exceeded. Try again in {retry_after} seconds."

    # Record current request
    _user_requests[user_id].append(now)
    return True, 0, "OK"

def check_matter_document_quota(user_id: str, matter_id: str, max_docs: Optional[int] = None) -> Tuple[bool, str]:
    """
    Enforces maximum number of documents per matter quota.
    """
    limit = max_docs if max_docs is not None else MAX_DOCS_PER_MATTER
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as doc_count FROM documents WHERE user_id = ? AND matter_id = ?",
        (user_id, matter_id)
    )
    row = cursor.fetchone()
    count = row["doc_count"] if row else 0
    conn.close()

    if count >= limit:
        return False, f"Matter document quota of {limit} documents reached. Please archive or remove older documents."
    return True, "OK"

def get_today_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())

def record_token_usage(user_id: str, tokens: int):
    """Records LLM tokens consumed by a user today."""
    today = get_today_key()
    _daily_tokens[(user_id, today)] += max(0, tokens)

def check_token_budget(user_id: str, max_daily_tokens: Optional[int] = None) -> Tuple[bool, int, str]:
    """
    Checks daily token budget.
    Returns: (is_allowed, remaining_tokens, message)
    """
    limit = max_daily_tokens if max_daily_tokens is not None else DAILY_TOKEN_BUDGET
    today = get_today_key()
    used = _daily_tokens.get((user_id, today), 0)
    remaining = max(0, limit - used)

    if used >= limit:
        return False, 0, f"Daily token budget of {limit:,} tokens exhausted for today. Resets at 00:00 UTC."
    return True, remaining, "OK"

def enforce_rate_limit(user_id: str, rpm_limit: Optional[int] = None):
    """Raises HTTPException 429 with Retry-After header if limit exceeded."""
    allowed, retry_after, msg = check_rate_limit(user_id, rpm_limit=rpm_limit)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limit_exceeded", "message": msg, "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)}
        )
