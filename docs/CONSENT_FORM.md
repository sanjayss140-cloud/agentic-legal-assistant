# FIRST-LOGIN CONSENT & ACKNOWLEDGEMENT FORM

*(Presented on first login before access to the Platform)*

---

### Welcome to Agentic Legal Assistant (Pilot Release)

Before proceeding, please review and acknowledge the terms of use, privacy framework, and operational boundaries of the Platform:

---

#### 1. Professional Decision Support Acknowledgement
- [x] **I understand that Agentic Legal Assistant is a decision-support and legal research assistant, NOT a substitute for independent legal judgment or professional counsel.**
- [x] **I acknowledge that as an advocate, I have an ethical duty to independently verify all statutory sections, case holdings, dates, and claims before submitting any document to a court, tribunal, or client.**

#### 2. Data Processing & External Inference
- [x] **I understand that uploaded documents are encrypted at rest with AES-256 and partitioned to my account and matters.**
- [x] **I acknowledge that scoped document excerpts are transmitted to Groq API for synthesis and entailment evaluation under zero-training enterprise terms.**
- [x] **I understand that I can enable "Mask Personal Identifiers" in matter settings to redact phone numbers, emails, and Indian tax/identity numbers (PAN/Aadhaar) on a best-effort basis.**

#### 3. Pilot Scope & Data Rights
- [x] **I understand that during this pilot, using public domain judgments, redacted petitions, or anonymized case records is recommended.**
- [x] **I acknowledge that I retain full ownership of my work product and can export or permanently delete my matters and account at any time.**

---

**Affirmation Button**:  
`[I Agree & Accept Terms]` -> Calls `POST /api/user/consent` with timestamp recording.
