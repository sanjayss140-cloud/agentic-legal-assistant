#!/usr/bin/env python3
"""
Agentic Legal Assistant: Law Firm Pilot Onboarding Utility
Creates pilot firm accounts, initial matters, and loads public sample cases.
"""

import sys
import secrets
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to sys.path
sys_path_root = str(Path(__file__).resolve().parent.parent)
if sys_path_root not in sys.path:
    sys.path.insert(0, sys_path_root)

from backend.ingestion.pipeline import get_db, ingest_document
from backend.security.auth import create_user
from backend.security.crypto import encrypt_bytes

def onboard_firm(
    firm_name: str,
    admin_email: str,
    lawyer_emails: List[str],
    preload_sample_case: bool = True
) -> Dict[str, Any]:
    """
    Provisions a pilot firm with:
    1. Managing Admin account
    2. Lawyer accounts with temporary passwords
    3. Dedicated default matters for each lawyer
    4. Pre-loaded public case file for immediate walkthrough testing
    """
    credentials = []

    # 1. Create Admin Account
    admin_pass = secrets.token_urlsafe(12) + "!A1"
    ok, msg, admin_user = create_user(admin_email, admin_pass, role="admin")
    if not ok:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, email, role FROM users WHERE email = ?", (admin_email,))
        admin_user = dict(c.fetchone())
        conn.close()

    credentials.append({
        "role": "admin",
        "email": admin_email,
        "temporary_password": admin_pass if ok else "[Existing User - Password Unchanged]",
        "user_id": admin_user["id"]
    })

    # 2. Create Lawyer Accounts & Initial Matters
    lawyer_records = []
    for email in lawyer_emails:
        lawyer_pass = secrets.token_urlsafe(12) + "!L1"
        l_ok, l_msg, l_user = create_user(email, lawyer_pass, role="lawyer")
        if not l_ok:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT id, email, role FROM users WHERE email = ?", (email,))
            l_user = dict(c.fetchone())
            conn.close()

        uid = l_user["id"]
        # Create initial matters
        conn = get_db()
        cursor = conn.cursor()
        mat_id = f"mat_{uid[:8]}_walkthrough"
        cursor.execute("""
        INSERT OR REPLACE INTO matters (id, user_id, name, client_ref, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            mat_id,
            uid,
            f"{firm_name} - Pilot Walkthrough Case",
            "DEMO-001",
            "Preloaded synthetic sample case for pilot training and evaluation.",
            time.time()
        ))
        conn.commit()
        conn.close()

        # Preload sample public case file if requested
        if preload_sample_case:
            try:
                sample_pdf = Path(sys_path_root) / "backend" / "tests" / "fixtures" / "synthetic_bail.pdf"
                if sample_pdf.exists():
                    user_corpus = Path(sys_path_root) / "data" / "corpus" / uid
                    user_corpus.mkdir(parents=True, exist_ok=True)
                    dest_file = user_corpus / "State_v_Sharma_Bail.pdf"
                    
                    raw_bytes = sample_pdf.read_bytes()
                    dest_file.write_bytes(encrypt_bytes(raw_bytes))

                    doc_id = f"doc_{uid[:8]}_sample_bail"
                    ingest_document(
                        str(dest_file),
                        doc_id=doc_id,
                        title="State v. Sharma Bail Petition Record",
                        user_id=uid,
                        matter_id=mat_id,
                        encrypt_at_rest=True
                    )
            except Exception as e:
                print(f"[Warning] Sample case preload error: {e}")

        credentials.append({
            "role": "lawyer",
            "email": email,
            "temporary_password": lawyer_pass if l_ok else "[Existing User - Password Unchanged]",
            "user_id": uid,
            "matter_id": mat_id
        })

    return {
        "status": "success",
        "firm_name": firm_name,
        "onboarded_count": len(credentials),
        "accounts": credentials
    }

if __name__ == "__main__":
    firm = sys.argv[1] if len(sys.argv) > 1 else "Apex Legal LLP"
    admin = sys.argv[2] if len(sys.argv) > 2 else "admin@apexlegal.firm"
    lawyers = sys.argv[3].split(",") if len(sys.argv) > 3 else ["rajesh.sharma@apexlegal.firm", "priya.nair@apexlegal.firm"]

    res = onboard_firm(firm, admin, lawyers)
    print("=" * 65)
    print(f"PILOT FIRM ONBOARDING COMPLETE: {res['firm_name']}")
    print("=" * 65)
    for acc in res["accounts"]:
        print(f"[{acc['role'].upper()}] {acc['email']}")
        print(f"  Password: {acc['temporary_password']}")
        if "matter_id" in acc:
            print(f"  Default Matter: {acc['matter_id']}")
        print()
    print("=" * 65)
