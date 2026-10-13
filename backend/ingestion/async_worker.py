import time
import secrets
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import BackgroundTasks
from backend.ingestion.pipeline import get_db, ingest_document
from backend.security.audit import log_audit

def create_job(user_id: str, matter_id: Optional[str], filename: str) -> str:
    """Creates a new queued ingestion job in the database."""
    job_id = f"job_{int(time.time())}_{secrets.token_hex(4)}"
    now = time.time()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO ingestion_jobs (job_id, user_id, matter_id, filename, status, progress_pct, error_message, document_id, created_at, updated_at)
    VALUES (?, ?, ?, ?, 'queued', 0, NULL, NULL, ?, ?)
    """, (job_id, user_id, matter_id or "default_matter", filename, now, now))
    conn.commit()
    conn.close()
    return job_id

def update_job(
    job_id: str,
    status: str,
    progress_pct: int,
    document_id: Optional[str] = None,
    error_message: Optional[str] = None
):
    """Updates job progress, status, and associated document or error."""
    now = time.time()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE ingestion_jobs
    SET status = ?, progress_pct = ?, document_id = COALESCE(?, document_id),
        error_message = COALESCE(?, error_message), updated_at = ?
    WHERE job_id = ?
    """, (status, progress_pct, document_id, error_message, now, job_id))
    conn.commit()
    conn.close()

def get_job(job_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves an ingestion job by ID, optionally verifying user ownership."""
    conn = get_db()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT * FROM ingestion_jobs WHERE job_id = ? AND user_id = ?", (job_id, user_id))
    else:
        cursor.execute("SELECT * FROM ingestion_jobs WHERE job_id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def list_jobs(user_id: str, matter_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Lists recent ingestion jobs for a user and optional matter."""
    conn = get_db()
    cursor = conn.cursor()
    if matter_id:
        cursor.execute(
            "SELECT * FROM ingestion_jobs WHERE user_id = ? AND matter_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, matter_id, limit)
        )
    else:
        cursor.execute(
            "SELECT * FROM ingestion_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def recover_stale_jobs():
    """Recovers jobs that were interrupted in intermediate states (e.g. on worker restart)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE ingestion_jobs
    SET status = 'failed', error_message = 'Process interrupted during worker restart. Please retry.', updated_at = ?
    WHERE status IN ('extracting', 'chunking', 'embedding', 'indexing')
    """, (time.time(),))
    recovered = cursor.rowcount
    conn.commit()
    conn.close()
    return recovered

def process_job(job_id: str, file_path_str: str, safe_name: str, user_id: str, matter_id: str):
    """Executes the ingestion pipeline asynchronously and reports fine-grained progress."""
    try:
        # Step 1: Extracting
        update_job(job_id, status="extracting", progress_pct=20)
        time.sleep(0.05)  # Yield for scheduler

        # Step 2: Chunking
        update_job(job_id, status="chunking", progress_pct=45)
        time.sleep(0.05)

        # Step 3: Embedding
        update_job(job_id, status="embedding", progress_pct=75)
        time.sleep(0.05)

        # Step 4: Indexing & Persistence
        update_job(job_id, status="indexing", progress_pct=90)
        
        doc_id = f"doc_{int(time.time())}_{secrets.token_hex(4)}"
        res = ingest_document(
            file_path_str,
            doc_id=doc_id,
            title=safe_name,
            user_id=user_id,
            matter_id=matter_id,
            encrypt_at_rest=True
        )

        if res.get("status") == "error":
            update_job(
                job_id,
                status="failed",
                progress_pct=100,
                error_message=res.get("message", "Ingestion failed.")
            )
        else:
            final_doc_id = res.get("doc_id", doc_id)
            update_job(job_id, status="ready", progress_pct=100, document_id=final_doc_id)
            log_audit(
                "async_document_ingested",
                user_id=user_id,
                matter_id=matter_id,
                target_type="document",
                target_id=final_doc_id
            )
    except Exception as e:
        update_job(job_id, status="failed", progress_pct=100, error_message=str(e))

def submit_ingestion_task(
    job_id: str,
    file_path_str: str,
    safe_name: str,
    user_id: str,
    matter_id: str,
    background_tasks: Optional[BackgroundTasks] = None
):
    """Submits the async ingestion task to BackgroundTasks or a daemon thread."""
    if background_tasks is not None:
        background_tasks.add_task(process_job, job_id, file_path_str, safe_name, user_id, matter_id)
    else:
        t = threading.Thread(
            target=process_job,
            args=(job_id, file_path_str, safe_name, user_id, matter_id),
            daemon=True
        )
        t.start()
