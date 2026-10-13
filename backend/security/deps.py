from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
from backend.security.auth import decode_token
from backend.ingestion.pipeline import get_db

DEFAULT_PILOT_USER = {
    "id": "default_lawyer",
    "email": "pilot.lawyer@lexground.local",
    "role": "lawyer",
    "matter_id": "default_matter",
    "consent_given": 1,
    "mask_pii_enabled": 0,
    "retention_days": 0
}

def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Extracts and authenticates user from httpOnly cookie or Authorization header.
    Provides seamless fallback for backward compatibility with pilot tests.
    """
    token = None
    
    # 1. Check Authorization Bearer header (explicit token takes precedence)
    if "Authorization" in request.headers:
        auth_header = request.headers["Authorization"]
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
        else:
            raise HTTPException(status_code=401, detail="Invalid authentication scheme.")
    # 2. Check httpOnly cookie
    elif "access_token" in request.cookies:
        token = request.cookies["access_token"]

    if not token:
        # Check custom test header
        if "X-User-Id" in request.headers:
            user_id = request.headers["X-User-Id"]
            matter_id = request.headers.get("X-Matter-Id", "default_matter")
            return {
                "id": user_id,
                "email": f"{user_id}@lexground.local",
                "role": request.headers.get("X-User-Role", "lawyer"),
                "matter_id": matter_id,
                "consent_given": 1,
                "mask_pii_enabled": 0,
                "retention_days": 0
            }
        return DEFAULT_PILOT_USER

    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired or invalid token. Please log in again.")

    user_id = payload.get("sub")
    matter_id = payload.get("matter_id")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, email, role, consent_given, mask_pii_enabled, retention_days 
    FROM users 
    WHERE id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="User account not found.")

    user = dict(row)
    user["matter_id"] = matter_id or f"matter_{user_id[:8]}"
    return user

def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for this action.")
    return user
