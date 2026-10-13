#!/usr/bin/env python3
"""
Agentic Legal Assistant: Feedback Export Utility
Exports lawyer feedback ratings and notes to CSV and JSON for weekly product review.
"""

import sys
import csv
import json
import time
from pathlib import Path
from typing import Dict, Any

sys_path_root = str(Path(__file__).resolve().parent.parent)
if sys_path_root not in sys.path:
    sys.path.insert(0, sys_path_root)

from backend.ingestion.pipeline import get_db

def export_feedback(output_dir: str = "data/exports") -> Dict[str, Any]:
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    date_str = time.strftime("%Y%m%d_%H%M%S")

    csv_path = dest / f"feedback_export_{date_str}.csv"
    json_path = dest / f"feedback_export_{date_str}.json"

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, user_id, matter_id, message_id, rating, notes, prompt_version, model, verified_status, created_at
    FROM answer_feedback
    ORDER BY created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    records = [dict(r) for r in rows]

    # Write JSON
    json_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    # Write CSV
    if records:
        fieldnames = list(records[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
    else:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            f.write("id,user_id,matter_id,message_id,rating,notes,prompt_version,model,verified_status,created_at\n")

    total = len(records)
    pos = sum(1 for r in records if r.get("rating") == 1)
    neg = total - pos
    pct = round((pos / total * 100), 1) if total > 0 else 100.0

    return {
        "total_records": total,
        "positive": pos,
        "negative": neg,
        "satisfaction_pct": pct,
        "csv_path": str(csv_path),
        "json_path": str(json_path)
    }

if __name__ == "__main__":
    res = export_feedback()
    print("=" * 60)
    print("LAWYER FEEDBACK EXPORT COMPLETE")
    print("=" * 60)
    print(f"Total Feedback Records: {res['total_records']}")
    print(f"Thumbs Up: {res['positive']} | Thumbs Down: {res['negative']} ({res['satisfaction_pct']}%)")
    print(f"CSV Export:  {res['csv_path']}")
    print(f"JSON Export: {res['json_path']}")
    print("=" * 60)
