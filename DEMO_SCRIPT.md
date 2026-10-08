# LexGround: 5-Minute Live Judicial Demonstration Script

## Overview
This walkthrough demonstrates the key innovations of LexGround in front of judicial evaluators: **deterministic verifiability**, **zero fabricated citations**, and **rigorous legal drafting**.

- **URL**: `http://localhost:8000`
- **Total Duration**: 5 Minutes
- **Key Message**: *"In court, an eloquent hallucination is perjury. LexGround guarantees that every fact, quote, and citation is deterministically verified against the case record."*

---

## Timed Walkthrough

### ⏱ 0:00 – 0:45 | Introduction & Architecture
1. **Show the Interface**:
   - Point out the full-screen Lady Justice background visible on the right 40% of the screen.
   - Explain the transparent dark glass design built for legal practitioners.
   - Note the metric indicators: *Verified Claims: X/Y*, *Fabricated Citations: 0*.
2. **Talking Point**:
   > *"Existing legal AI hallucinates cases and penal sections because LLMs prioritize fluency over ground truth. In LexGround, the LLM does not have the final say. A deterministic 3-gate verifier audits every claim against the corpus before the user ever sees it."*

---

### ⏱ 0:45 – 1:30 | Document Ingestion & Robustness
1. **Action 1: Non-Legal Document**:
   - Drag and drop `recipe.pdf` (or any non-legal file).
   - Show the immediate classification chip: `not_legal`.
   - Highlight the warning: *"This document doesn't look like a case file"* with the override button *"Use anyway"*.
2. **Action 2: Case Document Ingestion**:
   - Ingest `case1_bail_order.pdf` (or select from existing loaded documents).
   - Show instantaneous status transition: `indexing` ➔ `ready`.
   - Point out automatic case classification: `Case Type: Bail | Status: Ready`.

---

### ⏱ 1:30 – 2:30 | Grounded Chat & Source Drawer Inspection
1. **Action**:
   - In the composer, ask: *"What were the offences alleged against Vikram Sharma?"*
   - Submit the query.
2. **Observe Output**:
   - Show the structured plain-text response with citation chips (e.g., `[Vikram Sharma v. State, p.1]`).
   - Click the citation chip `[p.1]`.
   - Show the **Slide-over Source Drawer** popping up on the right, highlighting the exact verbatim chunk and verified quote from the underlying record.
3. **Show Multi-Turn Follow-Up**:
   - Ask: *"What about his custody duration?"*
   - Show multi-turn context resolution answering with exact remand dates from history.

---

### ⏱ 2:30 – 3:15 | Adversarial Trap & Absent Information Refusal
1. **Action 1: Fictitious Statute Trap**:
   - In the composer, ask: *"Can bail be granted under Section 9999 of the Martian Code?"*
   - **Result**: Instant refusal: *"Refusal: The referenced authority 'Section 9999' does not exist in the uploaded document citation registry and cannot be verified."*
2. **Action 2: Absent Case Fact**:
   - Ask: *"What was the color of the car driven by the judge?"*
   - **Result**: Exact refusal: *"Not found in the provided documents."*
3. **Talking Point**:
   > *"Notice that LexGround refuses to hallucinate plausible details from model memory. If it is not in the uploaded documents, it is refused."*

---

### ⏱ 3:15 – 4:15 | Legal Drafting & DOCX Export
1. **Action**:
   - Click the quick action card: **"Draft a bail application"** (or type `/draft`).
2. **Observe Guardrails**:
   - Point out the clean court header without duplicated words.
   - Point out the required fields audit: Found facts cited with `[doc, p.X]`.
   - Point out the missing facts formatted with `[MISSING: date of arrest]`, `[MISSING: surety amount]`.
   - Show that user-provided facts are explicitly tagged `[USER-PROVIDED]`.
3. **DOCX Export**:
   - Click the **"Download DOCX"** button.
   - Show the generated valid `.docx` file formatted for immediate filing.

---

### ⏱ 4:15 – 5:00 | Compare Mode (Live Benchmark)
1. **Action**:
   - Toggle **Compare Mode: ON** in the sidebar.
   - Run query: *"Under what section was regular bail sought?"*
2. **Examine Side-by-Side**:
   - **Left (Baseline RAG)**: Displays an unconstrained generation with fabricated case citations and 42.0% groundedness.
   - **Right (LexGround)**: 100% verified claims, exact page chips, and 0 fabricated citations.
3. **Closing Remark**:
   > *"LexGround turns generative AI from an unreliable legal liability into an airtight, auditable judicial tool."*

---

## Plan B: Offline / Network Outage Fallback

If the conference WiFi or Groq API suffers a connection drop:
1. **Command Line Reproducer**:
   Open terminal and run:
   ```bash
   python test_emergency_workflows.py
   ```
2. **Instant Output**:
   The script executes all 4 workflows locally using cached embeddings and in-memory heuristics, demonstrating 100% pass across all verification gates in under 5 seconds.
3. **Benchmark Artifact**:
   Present `eval/results/benchmark_results.json` and `docs/SMOKE_TEST.md` showing the recorded test metrics.
