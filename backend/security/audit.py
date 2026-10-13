import time
import sqlite3
from typing import List, Dict, Any, Optional
from backend.ingestion.pipeline import get_db

def log_audit(
    action: str,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Append-only audit logger for pilot governance.
    STRICT POLICY: Never logs document content, prompts, or authentication tokens.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            matter_id TEXT,
            action TEXT,
            target_type TEXT,
            target_id TEXT,
            ip_address TEXT,
            timestamp REAL
        );
        """)
        cursor.execute("""
        INSERT INTO audit_logs (user_id, matter_id, action, target_type, target_id, ip_address, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id or "anonymous", matter_id, action, target_type, target_id, ip_address, time.time()))
        conn.commit()
        conn.close()
    except Exception as e:
        # Failsafe logging without breaking operation
        print(f"[AUDIT LOG ERROR] Failed to record audit entry: {str(e)}")

def get_audit_logs(user_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve audit history for inspection/compliance."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        matter_id TEXT,
        action TEXT,
        target_type TEXT,
        target_id TEXT,
        ip_address TEXT,
        timestamp REAL
    );
    """)
    if user_id:
        cursor.execute("""
        SELECT id, user_id, matter_id, action, target_type, target_id, ip_address, timestamp
        FROM audit_logs
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
        """, (user_id, limit))
    else:
        cursor.execute("""
        SELECT id, user_id, matter_id, action, target_type, target_id, ip_address, timestamp
        FROM audit_logs
        ORDER BY timestamp DESC
        LIMIT ?
        """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
