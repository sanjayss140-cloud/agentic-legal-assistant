# PRIVACY POLICY & DATA PROTECTION NOTICE
*(Aligned with the Digital Personal Data Protection Act, 2023 — DPDP Act 2023, India)*

**Effective Date**: October 2026  
**Applicability**: Agentic Legal Assistant Pilot Deployment

---

### 1. Introduction & Scope
Agentic Legal Assistant is committed to safeguarding the privacy and confidentiality of advocates, law firms, and their clients. This Privacy Policy sets out how personal data and case file documents are processed, secured, and retained when using the **Agentic Legal Assistant** platform.

---

### 2. Roles Under the DPDP Act, 2023
- **Data Fiduciary**: The Law Firm or Advocate determining the purpose of processing client case data.
- **Data Processor**: Agentic Legal Assistant platform, acting on behalf of and under the instructions of the Data Fiduciary to perform semantic retrieval, citation verification, and petition drafting.
- **Data Principal**: The individual whose personal data is contained in the documents uploaded.

---

### 3. Categories of Data Processed
1. **Account Data**: Advocate email address, hashed credentials, role (`lawyer` / `admin`), and 2FA secrets.
2. **Case Matter Data**: Case folder names, client reference identifiers, case notes, and uploaded court records (PDFs, DOCX, TXT).
3. **Derived Semantic Data**: Text chunks, dense vector embeddings, and citation registry indices.
4. **Audit & Telemetry Logs**: Timestamps, action identifiers, latency metrics, and verification outcomes (strictly devoid of document text, prompts, or secrets).

---

### 4. Technical Safeguards & Encryption
- **Encryption at Rest**: Uploaded case files are encrypted at the application level using AES-256 (Fernet) prior to disk persistence. Keys are managed through environment secrets.
- **Encryption in Transit**: All communication is secured via TLS 1.3 / HTTPS with HSTS enforced.
- **Multi-Tenant Partitioning**: Strict user-level and matter-level isolation is enforced across database queries, vector indexes, and in-memory caches.

---

### 5. Third-Party LLM Provider Disclosure (Groq API)
- Natural language generation and entailment checks use the Groq API (LLaMA 3.3 70B and 3.1 8B models).
- **Zero Training Retention**: Document excerpts sent for retrieval inference are not logged or retained by the LLM provider for model training.
- **Client Redaction (Best-Effort PII Masking)**: When enabled under matter settings, email addresses, phone numbers, Aadhaar numbers, and PAN cards are pseudonymized with replacement tokens (`[TOKEN_N]`) prior to external transmission and re-hydrated locally upon display.

---

### 6. Data Principal Rights & Self-Service Controls
Under Chapter III of the DPDP Act, 2023, users are entitled to:
1. **Right to Access & Portability**: Download a complete export of all matters, documents (decrypted on demand), drafts, and audit logs via `/api/user/export-data` as a standard ZIP archive.
2. **Right to Correction**: Edit matter metadata, client references, and notes at any time.
3. **Right to Complete Erasure**: Permanently purge an entire matter (`DELETE /api/matters/{id}`) or delete the entire account (`DELETE /api/user/account`). This automatically removes physical disk files, database rows, chunk vectors, and chat history.

---

### 7. Grievance Redressal
In accordance with Section 13 of the DPDP Act, 2023, queries or grievances regarding data processing may be addressed to:  
**Data Protection Officer (DPO)**: `privacy@lexground.legal`
