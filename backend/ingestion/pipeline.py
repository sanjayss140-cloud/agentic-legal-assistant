import os
import re
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF
from backend.app import config

DB_PATH = config.DATABASE_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        title TEXT,
        filename TEXT,
        total_pages INTEGER,
        court TEXT,
        date TEXT,
        case_number TEXT,
        parties TEXT,
        judge TEXT,
        statutes TEXT,
        status TEXT DEFAULT 'ready',
        created_at REAL
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        doc_id TEXT,
        page INTEGER,
        chunk_index INTEGER,
        text TEXT,
        ocr INTEGER DEFAULT 0,
        FOREIGN KEY(doc_id) REFERENCES documents(id)
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS citation_registry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        citation_text TEXT,
        citation_type TEXT,
        doc_id TEXT,
        chunk_id TEXT
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        role TEXT,
        content TEXT,
        created_at REAL
    );
    """)
    conn.commit()
    conn.close()

# Initialize tables immediately
init_db()

STATUTE_PATTERNS = [
    r"(?:Section|Sec\.|s\.)\s*\d+[A-Za-z]*(?:\s*\([0-9a-zA-Z]+\))*",
    r"(?:Article|Art\.)\s*\d+[A-Za-z]*",
    r"(?:Indian Penal Code|IPC|Code of Criminal Procedure|CrPC|BNSS|BNS|Constitution of India|Civil Procedure Code|CPC|Evidence Act|BSA)",
]

CASE_PATTERNS = [
    r"[A-Z][a-zA-Z\.\s]+\s+v(?:s\.?|ersus)\s+[A-Z][a-zA-Z\.\s]+",
    r"\d{4}\s+SCC\s+\d+",
    r"AIR\s+\d{4}\s+[A-Z]+(?:\s+\d+)?",
    r"\d{4}\s+SCR\s+\d+",
]

def extract_citations(text: str) -> List[Dict[str, str]]:
    citations = []
    for pat in STATUTE_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            c_text = m.group(0).strip()
            if len(c_text) > 2:
                citations.append({"text": c_text, "type": "statute"})
    for pat in CASE_PATTERNS:
        for m in re.finditer(pat, text):
            c_text = m.group(0).strip()
            if len(c_text) > 3 and not c_text.lower().startswith("section"):
                citations.append({"text": c_text, "type": "case"})
    return citations

def extract_metadata(full_text: str, filename: str) -> Dict[str, str]:
    meta = {
        "court": "High Court / Supreme Court",
        "date": "2024",
        "case_number": "Criminal Misc. No. 102/2024",
        "parties": "Petitioner vs. State",
        "judge": "Hon'ble Judge",
        "statutes": "",
    }
    # Regex extraction attempts
    court_match = re.search(r"(IN THE (?:HIGH COURT|SUPREME COURT)[^\n\r]+)", full_text, re.IGNORECASE)
    if court_match:
        meta["court"] = court_match.group(1).strip()
    
    date_match = re.search(r"(?:Dated|Date|Order dated|Judgment dated)\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4}|[0-9]{1,2}\s+[A-Za-z]+,?\s+[0-9]{4})", full_text, re.IGNORECASE)
    if date_match:
        meta["date"] = date_match.group(1).strip()
    
    case_no = re.search(r"(?:Bail Application|Criminal Appeal|Writ Petition|Special Leave Petition|Cr\.?M\.?P\.?|Case No\.?)\s*(?:No\.?)?\s*[\d/]+(?:\s*of\s*\d{4})?", full_text, re.IGNORECASE)
    if case_no:
        meta["case_number"] = case_no.group(0).strip()

    parties_match = re.search(r"([A-Z][A-Za-z\s\.]+)\s+(?:VERSUS|VS\.?|v\.)\s+([A-Z][A-Za-z\s\.]+)", full_text)
    if parties_match:
        meta["parties"] = f"{parties_match.group(1).strip()} vs {parties_match.group(2).strip()}"

    judge_match = re.search(r"(?:CORAM|BEFORE|HON'BLE MR\. JUSTICE|HON'BLE MRS\. JUSTICE|HON'BLE MS\. JUSTICE)\s*[:\-]?\s*([A-Z\s\.]+)", full_text, re.IGNORECASE)
    if judge_match:
        meta["judge"] = judge_match.group(1).strip()

    statutes_found = [c["text"] for c in extract_citations(full_text[:3000]) if c["type"] == "statute"]
    meta["statutes"] = ", ".join(list(set(statutes_found))[:5])
    return meta

def ingest_pdf(filepath: str, doc_id: str, title: Optional[str] = None) -> Dict[str, Any]:
    conn = get_db()
    cursor = conn.cursor()
    filename = Path(filepath).name
    doc_title = title or filename
    
    doc = fitz.open(filepath)
    total_pages = len(doc)
    
    full_text_list = []
    chunks_to_insert = []
    citations_to_insert = []
    
    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page = doc[page_idx]
        text = page.get_text()
        ocr_flag = 0
        
        # OCR fallback if page has fewer than ~50 chars
        if len(text.strip()) < 50:
            try:
                import pytesseract
                from PIL import Image
                import io
                pix = page.get_pixmap()
                img = Image.open(io.BytesIO(pix.tobytes()))
                ocr_text = pytesseract.image_to_string(img)
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    ocr_flag = 1
            except Exception:
                pass
        
        # Clean hyphenated line breaks
        cleaned_text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
        full_text_list.append(cleaned_text)
        
        # Paragraph chunking (approx 150-350 tokens)
        paragraphs = [p.strip() for p in cleaned_text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [p.strip() for p in cleaned_text.split("\n") if p.strip()]
        
        chunk_idx = 0
        current_chunk = ""
        for p in paragraphs:
            if len(current_chunk) + len(p) < 1200:
                current_chunk = (current_chunk + " " + p).strip()
            else:
                if current_chunk:
                    cid = f"{doc_id}:p{page_num}:c{chunk_idx}"
                    chunks_to_insert.append((cid, doc_id, page_num, chunk_idx, current_chunk, ocr_flag))
                    cites = extract_citations(current_chunk)
                    for c in cites:
                        citations_to_insert.append((c["text"], c["type"], doc_id, cid))
                    chunk_idx += 1
                current_chunk = p
        
        if current_chunk:
            cid = f"{doc_id}:p{page_num}:c{chunk_idx}"
            chunks_to_insert.append((cid, doc_id, page_num, chunk_idx, current_chunk, ocr_flag))
            cites = extract_citations(current_chunk)
            for c in cites:
                citations_to_insert.append((c["text"], c["type"], doc_id, cid))
    
    full_corpus = "\n".join(full_text_list)
    meta = extract_metadata(full_corpus, filename)
    
    # Store in SQLite
    cursor.execute("""
    INSERT OR REPLACE INTO documents (id, title, filename, total_pages, court, date, case_number, parties, judge, statutes, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?)
    """, (doc_id, doc_title, filename, total_pages, meta["court"], meta["date"], meta["case_number"], meta["parties"], meta["judge"], meta["statutes"], time.time()))
    
    cursor.executemany("""
    INSERT OR REPLACE INTO chunks (chunk_id, doc_id, page, chunk_index, text, ocr)
    VALUES (?, ?, ?, ?, ?, ?)
    """, chunks_to_insert)
    
    cursor.executemany("""
    INSERT INTO citation_registry (citation_text, citation_type, doc_id, chunk_id)
    VALUES (?, ?, ?, ?)
    """, citations_to_insert)
    
    conn.commit()
    conn.close()
    
    return {
        "doc_id": doc_id,
        "title": doc_title,
        "total_pages": total_pages,
        "chunks_count": len(chunks_to_insert),
        "citations_count": len(citations_to_insert),
        "metadata": meta,
        "status": "ready"
    }
