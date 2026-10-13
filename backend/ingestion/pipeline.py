import os
import re
import hashlib
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import fitz  # PyMuPDF
from backend.app import config

DB_PATH = config.DATABASE_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        title TEXT,
        filename TEXT,
        file_size INTEGER DEFAULT 0,
        content_hash TEXT,
        total_pages INTEGER,
        court TEXT,
        date TEXT,
        case_number TEXT,
        parties TEXT,
        judge TEXT,
        statutes TEXT,
        status TEXT DEFAULT 'ready',
        doc_type TEXT DEFAULT 'legal_case',
        case_type TEXT DEFAULT 'general',
        is_legal INTEGER DEFAULT 1,
        classification_confidence REAL DEFAULT 1.0,
        ocr_warning TEXT,
        language_warning TEXT,
        user_override INTEGER DEFAULT 0,
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
    # Ensure all columns exist for existing databases
    # Ensure multi-tenant and matter columns exist for all tables
    def add_col_if_missing(table, col_name, col_type):
        cols = [c[1] for c in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
        if col_name not in cols:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

    doc_cols = [
        ("file_size", "INTEGER DEFAULT 0"),
        ("content_hash", "TEXT"),
        ("doc_type", "TEXT DEFAULT 'legal_case'"),
        ("case_type", "TEXT DEFAULT 'general'"),
        ("is_legal", "INTEGER DEFAULT 1"),
        ("classification_confidence", "REAL DEFAULT 1.0"),
        ("ocr_warning", "TEXT"),
        ("language_warning", "TEXT"),
        ("user_override", "INTEGER DEFAULT 0"),
        ("user_id", "TEXT DEFAULT 'default_lawyer'"),
        ("matter_id", "TEXT DEFAULT 'default_matter'"),
        ("is_encrypted", "INTEGER DEFAULT 1"),
        ("storage_path", "TEXT"),
    ]
    for c_name, c_def in doc_cols:
        add_col_if_missing("documents", c_name, c_def)

    for tbl in ["chunks", "citation_registry", "chat_history"]:
        add_col_if_missing(tbl, "user_id", "TEXT DEFAULT 'default_lawyer'")
        add_col_if_missing(tbl, "matter_id", "TEXT DEFAULT 'default_matter'")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS drafts (
        id TEXT PRIMARY KEY,
        user_id TEXT DEFAULT 'default_lawyer',
        matter_id TEXT DEFAULT 'default_matter',
        doc_type TEXT,
        draft_text TEXT,
        groundedness_score REAL,
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
    r"(?:Indian Penal Code|IPC|Code of Criminal Procedure|CrPC|BNSS|BNS|Negotiable Instruments Act|NI Act|Constitution of India|Civil Procedure Code|CPC|Evidence Act|BSA)",
]

CASE_PATTERNS = [
    r"[A-Z][a-zA-Z\.\s]+\s+v(?:s\.?|ersus)\s+[A-Z][a-zA-Z\.\s]+",
    r"\d{4}\s+SCC\s+\d+",
    r"AIR\s+\d{4}\s+[A-Z]+(?:\s+\d+)?",
    r"\d{4}\s+SCR\s+\d+",
]

def calculate_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def detect_language(text: str) -> Optional[str]:
    # Check for Devanagari or Tamil unicode ranges
    devanagari = len(re.findall(r'[\u0900-\u097F]', text))
    tamil = len(re.findall(r'[\u0B80-\u0BFF]', text))
    if devanagari > 30:
        return "Contains Hindi/Devanagari text"
    if tamil > 30:
        return "Contains Tamil text"
    return None

def classify_document_type(full_text: str, filename: str) -> Tuple[str, str, bool, float, str]:
    """
    Classify document into:
    doc_type: legal_case | statute_or_act | contract_or_notice | not_legal | unreadable
    case_type: bail | cheque_bounce | criminal | civil | consumer | writ | contract | non_legal | other
    is_legal: bool
    confidence: float
    description: str
    """
    text_lower = full_text.lower()
    
    if len(full_text.strip()) < 30:
        return "unreadable", "unknown", False, 0.95, "File is empty or contains insufficient text"

    # Non-legal signals (recipes, coding, academic/hackathon, assignments)
    recipe_cues = ["recipe", "ingredients", "tablespoon", "teaspoon", "cook time", "boil", "bake", "cuisine", "calories"]
    code_cues = ["import ", "function ", "class ", "def ", "var ", "const ", "npm install", "git commit"]
    academic_cues = [
        "hackathon", "problem statement", "hacknex", "guidelines for submission", "evaluation criteria", 
        "rubric", "round 1", "round 2", "team members", "curriculum", "syllabus", "assignment", "deliverables",
        "benchmark dataset", "model architecture", "fine-tuning", "test set", "baseline rag"
    ]
    
    recipe_score = sum(1 for c in recipe_cues if c in text_lower)
    code_score = sum(1 for c in code_cues if c in text_lower)
    academic_score = sum(1 for c in academic_cues if c in text_lower)
    
    if recipe_score >= 3:
        return "not_legal", "non_legal", False, 0.98, "Cooking recipe / culinary document"
    if code_score >= 3 and "court" not in text_lower and "section" not in text_lower:
        return "not_legal", "non_legal", False, 0.95, "Source code / programming document"
    if academic_score >= 2 and not ("in the supreme court" in text_lower or "in the high court" in text_lower or "bail appln" in text_lower):
        return "not_legal", "non_legal", False, 0.95, "Non-legal document (Hackathon problem statements / technical document). Tick 'Use anyway' to analyze."

    # Strict judicial anchors
    judicial_anchors = [
        "supreme court of india", "high court of", "court of sessions", "court of magistrate",
        "district court", "sessions judge", "chief metropolitan magistrate", "metropolitan magistrate",
        "bail appln", "crl.m.c", "criminal appeal", "civil appeal", "special leave petition",
        "first information report", "fir no", "chargesheet", "police station", "state of", "union of india",
        "anticipatory bail", "regular bail", "quashing of proceedings", "section 439", "section 438", "section 482", "section 138"
    ]
    anchor_hits = sum(1 for a in judicial_anchors if a in text_lower)

    legal_signals = [
        "court", "petitioner", "respondent", "appellant", "applicant",
        "accused", "judgment", "fir", "crpc", "ipc", "bnss", "bns", "bail", "advocate", "affidavit"
    ]
    legal_hits = sum(1 for s in legal_signals if s in text_lower)
    
    if anchor_hits == 0 and legal_hits < 2:
        return "not_legal", "non_legal", False, 0.85, "General non-legal text"

    # Detect case type
    if "bail" in text_lower or "438" in text_lower or "439" in text_lower or "483 bnss" in text_lower:
        c_type = "bail"
    elif "138" in text_lower or "cheque" in text_lower or "dishonour" in text_lower or "negotiable instruments" in text_lower:
        c_type = "cheque_bounce"
    elif any(k in text_lower for k in ["fir", "accused", "ipc", "bns", "police station", "chargesheet", "custody"]):
        c_type = "criminal"
    elif "writ" in text_lower or "article 226" in text_lower or "article 32" in text_lower:
        c_type = "writ"
    elif "notice" in text_lower and ("advocate" in text_lower or "demand" in text_lower):
        c_type = "contract_or_notice"
    else:
        c_type = "civil"

    # Determine primary doc_type
    if "act, 19" in text_lower or "act, 20" in text_lower or "ordinance" in text_lower:
        d_type = "statute_or_act"
    elif "notice" in text_lower or "agreement" in text_lower:
        d_type = "contract_or_notice"
    else:
        d_type = "legal_case"

    confidence = min(0.70 + (anchor_hits * 0.10) + (legal_hits * 0.02), 0.99)
    return d_type, c_type, True, confidence, "Legal document"

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
        "court": "MISSING",
        "date": "MISSING",
        "case_number": "MISSING",
        "parties": "MISSING",
        "judge": "MISSING",
        "statutes": "",
    }
    first_pages_text = full_text[:4000]

    # Court regex
    court_match = re.search(
        r"(?:IN\s+THE\s+)?(SUPREME\s+COURT\s+OF\s+INDIA|HIGH\s+COURT\s+OF\s+[A-Z\s]+|COURT\s+OF\s+[A-Z\s]+(?:JUDGE|MAGISTRATE)|DISTRICT\s+(?:AND\s+SESSIONS\s+)?COURT[A-Z\s]*|SPECIAL\s+COURT\s+[A-Z\s]+)",
        first_pages_text,
        re.IGNORECASE
    )
    if court_match:
        meta["court"] = re.sub(r"\s+", " ", court_match.group(0).strip())

    # Date regex (header or footer)
    date_match = re.search(
        r"(?:ORDER\s+DATED|DATE\s+OF\s+ORDER|DATED|DELIVERED\s+ON|DECIDED\s+ON|JUDGMENT\s+DATED)\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4}|[0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})",
        first_pages_text,
        re.IGNORECASE
    )
    if not date_match and len(full_text) > 4000:
        date_match = re.search(
            r"\b([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})\b",
            full_text[-2000:],
            re.IGNORECASE
        )
    if date_match:
        meta["date"] = re.sub(r"\s+", " ", date_match.group(1).strip())

    # Case number regex
    case_no = re.search(
        r"(?:SPECIAL\s+LEAVE\s+PETITION\s*(?:\([A-Za-z\.]+\))?|CRIMINAL\s+APPEAL|CIVIL\s+APPEAL|WRIT\s+PETITION\s*(?:\([A-Za-z\.]+\))?|BAIL\s+APPLN\.?|CRL\.?\s*M\.?C\.?|CC\s+NO\.?|CRIMINAL\s+MISC\.?\s*NO\.?|CRIME\s+NO\.?|FIR\s+NO\.?|Cr\.?M\.?P\.?\s*No\.?|Case\s+No\.?|MISCELLANEOUS\s+APPLICATION\s+(?:NO\.?)?\s*[\d/]+(?:\s+OF\s+\d{4})?\s+IN\s+SPECIAL\s+LEAVE\s+PETITION[^\n\r]+)\s*(?:No\.?)?\s*[:\.]?\s*[\dA-Za-z\/\-]+(?:\s*OF\s*\d{4})?",
        first_pages_text,
        re.IGNORECASE
    )
    if case_no:
        meta["case_number"] = re.sub(r"\s+", " ", case_no.group(0).strip())

    # Parties regex
    p_matter = re.search(r"IN\s+THE\s+MATTER\s+OF:\s*([^\n\r]+?)(?:\s+vs\.?\s+|\s+VERSUS\s+)([^\n\r]+)", first_pages_text, re.IGNORECASE)
    if p_matter:
        meta["parties"] = f"{re.sub(r'\s+', ' ', p_matter.group(1).strip())} vs {re.sub(r'\s+', ' ', p_matter.group(2).strip())}"
    else:
        cause_title = re.search(r"([A-Z\s\.\,\(\)\&]{3,60}?)(?:\s*\.\.\.\s*(?:APPELLANT|PETITIONER|APPLICANT|ACCUSED|AP)[^\n\r]*)?\s+(?:VERSUS|VS\.?)\s+([A-Z\s\.\,\(\)\&]{3,60}?)(?:\s*\.\.\.\s*(?:RESPONDENT|STATE|DEFENDANT|RE)[^\n\r]*)?(?:\n|\r|$)", first_pages_text)
        if cause_title:
            p1 = re.sub(r"\s+", " ", cause_title.group(1).strip()).strip("., ")
            p2 = re.sub(r"\s+", " ", cause_title.group(2).strip()).strip("., ")
            if not any(k in p1.lower() or k in p2.lower() for k in ["groundedness", "baseline", "order", "court", "dated", "evaluation"]):
                if len(p1) > 2 and len(p2) > 2:
                    meta["parties"] = f"{p1} vs {p2}"

    # Judge regex
    judge_match = re.search(r"(?:HON'BLE\s+(?:MR\.|MS\.|MRS\.)?\s*JUSTICE|CORAM\s*[:\-]?\s*(?:HON'BLE)?\s*JUSTICE|Bench\s*[:\-]?\s*|Author\s*[:\-]?\s*)([A-Z\.\s,]{3,50})", first_pages_text, re.IGNORECASE)
    if judge_match:
        clean_j = re.sub(r"^(?:Bench|Author|CORAM)\s*[:\-]?\s*", "", judge_match.group(0).strip(), flags=re.IGNORECASE)
        meta["judge"] = re.sub(r"\s+", " ", clean_j.strip())

    statutes_found = [c["text"] for c in extract_citations(first_pages_text) if c["type"] == "statute"]
    meta["statutes"] = ", ".join(list(set(statutes_found))[:5])
    return meta

def extract_text_from_file(filepath: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Extracts text page by page with full validation for PDF, TXT, DOCX.
    Detects password protection, corrupted files, runs OCR fallback, and transparently
    decrypts application-level encrypted files at rest in memory.
    """
    path = Path(filepath)
    ext = path.suffix.lower()
    file_size = path.stat().st_size
    
    if file_size == 0:
        return [], {"error": "I couldn't read this file (empty file).", "error_code": "empty_file"}

    with open(filepath, "rb") as f:
        raw_bytes = f.read()

    # Detect application-level encryption at rest (Fernet token prefix b"gAAAAA")
    if raw_bytes.startswith(b"gAAAAA"):
        from backend.security.crypto import decrypt_bytes
        try:
            file_bytes = decrypt_bytes(raw_bytes)
        except Exception:
            file_bytes = raw_bytes
    else:
        file_bytes = raw_bytes

    pages_data = []

    if ext == ".txt":
        try:
            content = file_bytes.decode("utf-8", errors="ignore")
            pages_data.append({"page": 1, "text": content, "ocr": 0})
            return pages_data, {}
        except Exception as e:
            return [], {"error": f"I couldn't read this file: {str(e)}", "error_code": "corrupted"}

    elif ext == ".docx":
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            import io
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as docx:
                xml_content = docx.read('word/document.xml')
                tree = ET.fromstring(xml_content)
                paragraphs = []
                for p in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                    texts = [node.text for node in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if node.text]
                    if texts:
                        paragraphs.append("".join(texts))
                content = "\n\n".join(paragraphs)
                pages_data.append({"page": 1, "text": content, "ocr": 0})
                return pages_data, {}
        except Exception:
            return [], {"error": "I couldn't read this file (corrupted or invalid DOCX).", "error_code": "corrupted"}

    elif ext == ".pdf":
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception:
            return [], {"error": "I couldn't read this file (corrupted or unreadable PDF).", "error_code": "corrupted"}

        if doc.is_encrypted or doc.needs_pass:
            doc.close()
            return [], {"error": "This PDF is locked. Upload an unlocked copy.", "error_code": "locked"}

        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            return [], {"error": "I couldn't read this file (0 pages found).", "error_code": "empty_file"}

        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page = doc[page_idx]
            text = page.get_text()
            ocr_flag = 0

            # Automatic OCR fallback if page has fewer than 50 chars
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

            cleaned_text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
            pages_data.append({"page": page_num, "text": cleaned_text, "ocr": ocr_flag})

        doc.close()
        return pages_data, {}
    else:
        return [], {"error": "This file type isn't supported. Upload PDF, DOCX or TXT.", "error_code": "unsupported_type"}

def ingest_document(
    filepath: str, 
    doc_id: str, 
    title: Optional[str] = None,
    user_id: str = "default_lawyer",
    matter_id: str = "default_matter",
    encrypt_at_rest: bool = False
) -> Dict[str, Any]:
    """Robust document ingestion with classification, duplicate handling, multi-tenant matter isolation, and optional encryption at rest."""
    conn = get_db()
    cursor = conn.cursor()
    filename = Path(filepath).name
    doc_title = title or filename
    file_size = Path(filepath).stat().st_size
    content_hash = calculate_sha256(filepath)

    # 1. Duplicate check strictly scoped by user_id and matter_id
    cursor.execute("""
    SELECT id, title, doc_type, case_type, is_legal FROM documents 
    WHERE (content_hash = ? OR (filename = ? AND file_size = ?)) AND user_id = ? AND matter_id = ?
    """, (content_hash, filename, file_size, user_id, matter_id))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        is_leg = bool(existing["is_legal"])
        c_type = existing["case_type"] or "general"
        d_type = existing["doc_type"] or "not_legal"
        msg = "Already uploaded." if is_leg else f"Already uploaded. This document doesn't look like a case file ({d_type})."
        return {
            "status": "duplicate",
            "message": msg,
            "doc_id": existing["id"],
            "title": existing["title"],
            "doc_type": d_type,
            "case_type": c_type,
            "is_legal": is_leg
        }

    # 2. Extract text with validation
    pages_data, err = extract_text_from_file(filepath)
    if err:
        conn.close()
        return {
            "status": "error",
            "message": err["error"],
            "error_code": err.get("error_code", "generic_error"),
            "filename": filename
        }

    # Optional encryption at rest
    if encrypt_at_rest:
        try:
            from backend.security.crypto import encrypt_bytes
            with open(filepath, "rb") as f:
                raw_bytes = f.read()
            if not raw_bytes.startswith(b"gAAAAA"):
                enc = encrypt_bytes(raw_bytes)
                with open(filepath, "wb") as f:
                    f.write(enc)
        except Exception:
            pass

    full_text_list = [p["text"] for p in pages_data]
    full_text = "\n".join(full_text_list)

    # 3. Language & OCR quality checks
    lang_warning = detect_language(full_text)
    ocr_pages = sum(1 for p in pages_data if p["ocr"] == 1)
    ocr_warning = "Scanned document (OCR applied). If text is poor, answers may be unreliable." if ocr_pages > 0 else None

    # 4. Document Type Classification
    doc_type, case_type, is_legal, confidence, type_desc = classify_document_type(full_text, filename)

    # 5. Metadata extraction
    meta = extract_metadata(full_text, filename)

    # 6. Chunking
    chunks_to_insert = []
    citations_to_insert = []

    for p_info in pages_data:
        page_num = p_info["page"]
        p_text = p_info["text"]
        paragraphs = [p.strip() for p in p_text.split("\n\n") if p.strip()] or [p_text.strip()]
        
        chunk_idx = 0
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) < 1200:
                current_chunk = (current_chunk + " " + para).strip()
            else:
                if current_chunk:
                    cid = f"{doc_id}:p{page_num}:c{chunk_idx}"
                    chunks_to_insert.append((cid, doc_id, page_num, chunk_idx, current_chunk, p_info["ocr"], user_id, matter_id))
                    for c in extract_citations(current_chunk):
                        citations_to_insert.append((c["text"], c["type"], doc_id, cid, user_id, matter_id))
                    chunk_idx += 1
                current_chunk = para
        if current_chunk:
            cid = f"{doc_id}:p{page_num}:c{chunk_idx}"
            chunks_to_insert.append((cid, doc_id, page_num, chunk_idx, current_chunk, p_info["ocr"], user_id, matter_id))
            for c in extract_citations(current_chunk):
                citations_to_insert.append((c["text"], c["type"], doc_id, cid, user_id, matter_id))

    # 7. Persist to DB with user_id and matter_id
    cursor.execute("""
    INSERT OR REPLACE INTO documents 
    (id, title, filename, file_size, content_hash, total_pages, court, date, case_number, parties, judge, statutes, status, doc_type, case_type, is_legal, classification_confidence, ocr_warning, language_warning, user_id, matter_id, is_encrypted, storage_path, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        doc_id, doc_title, filename, file_size, content_hash, len(pages_data),
        meta["court"], meta["date"], meta["case_number"], meta["parties"],
        meta["judge"], meta["statutes"], doc_type, case_type, 1 if is_legal else 0,
        confidence, ocr_warning, lang_warning, user_id, matter_id, 1 if encrypt_at_rest else 0, str(filepath), time.time()
    ))

    cursor.executemany("""
    INSERT OR REPLACE INTO chunks (chunk_id, doc_id, page, chunk_index, text, ocr, user_id, matter_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, chunks_to_insert)

    cursor.executemany("""
    INSERT INTO citation_registry (citation_text, citation_type, doc_id, chunk_id, user_id, matter_id)
    VALUES (?, ?, ?, ?, ?, ?)
    """, citations_to_insert)

    conn.commit()
    conn.close()

    result_status = "ready" if is_legal else "not_legal"
    friendly_msg = "Document ingested and ready." if is_legal else f"This doesn't look like a case file or legal document (looks like: {type_desc}). Upload a court judgment, order, FIR, petition, notice or statute."

    return {
        "status": result_status,
        "message": friendly_msg,
        "doc_id": doc_id,
        "title": doc_title,
        "filename": filename,
        "total_pages": len(pages_data),
        "chunks_count": len(chunks_to_insert),
        "citations_count": len(citations_to_insert),
        "doc_type": doc_type,
        "case_type": case_type,
        "is_legal": is_legal,
        "confidence": round(confidence, 2),
        "ocr_warning": ocr_warning,
        "language_warning": lang_warning,
        "user_id": user_id,
        "matter_id": matter_id,
        "metadata": meta
    }

# Backward compatible alias for existing calls
ingest_pdf = ingest_document
