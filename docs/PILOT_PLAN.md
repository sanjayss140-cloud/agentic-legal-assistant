# PILOT PROGRAM RUNBOOK & ROLLOUT PLAN

**Project**: Agentic Legal Assistant  
**Target Audience**: Beta Pilot Law Firms & Practicing Advocates  
**Duration**: 4 Weeks

---

## 1. Executive Summary & Core Objective
The purpose of the Pilot Program is to evaluate **Agentic Legal Assistant** in a controlled, private environment with practicing advocates. The pilot validates that the platform accelerates case document review, chronology compilation, and petition drafting while maintaining a zero-fabrication standard through deterministic citation and entailment verification gates.

---

## 2. Four-Week Pilot Schedule

### Week 1: Onboarding, Setup & Baseline Testing
- **Day 1**: Run onboarding script (`scripts/onboard_pilot_firm.py`) to provision advocate accounts and initial walkthrough matters.
- **Day 2**: 45-minute live walkthrough with pilot advocates covering:
  - Multi-tenant matters and strict document scoping (ticking case files).
  - Lady Justice split-pane interface and verified citation chips.
  - Reviewing the pre-loaded synthetic bail petition record.
- **Day 3–5**: Advocates test routine workflows using anonymized judgments or public filings.
- **End of Week 1 Check-in**: Verification of account access, UX feedback on transparency, and bug triaging.

### Week 2: Case Review & Chronology Extraction
- **Focus**: Testing complex, multi-page case files across criminal, civil, and commercial matters.
- **Workflows Used**:
  - Automated Case Review (Parties, Sections, FIR number, Missing Info audit).
  - Chronology Timeline generation and OpenXML `.docx` / `.csv` export.
  - Dates and Deadlines calendar extraction and `.ics` export.
- **Mid-Pilot Check-in**: Collect lawyer feedback via thumbs up/down and notes on timeline precision.

### Week 3: Legal Drafting & Citation Checking
- **Focus**: Evaluating draft quality, `[MISSING: ...]` placeholder discipline, and citation auditing.
- **Workflows Used**:
  - 5 Formal Indian Legal Templates: Bail Application, Section 138 Complaint, Section 138 Notice, Consumer Complaint, and Writ Synopsis.
  - Citation Checker: Pasting external draft briefs to verify facts and citations against scoped case files.
  - Document Comparison: Side-by-side comparison of impugned orders vs petition grounds.
- **End of Week 3 Check-in**: Review draft completeness and statutory accuracy.

### Week 4: Final Evaluation, Exit Interviews & Data Destruction
- **Focus**: Quantitative evaluation against success metrics and post-pilot transition.
- **Activities**:
  - Run `scripts/export_feedback.py` to dump complete ratings matrix.
  - Conduct 30-minute structured exit interviews with participating advocates.
  - Execute Data Destruction Procedure for firms concluding the trial.

---

## 3. Success Criteria & Metrics

| Criterion | Target Threshold | Measured Via |
| :--- | :--- | :--- |
| **Groundedness Ratio** | $\ge 90\%$ of factual claims backed by exact verbatim quotes | Gate A & Gate B Verifiers |
| **Citation Fabrication** | **Zero (0)** unindexed statutes or cases permitted in final outputs | Gate C Corpus Registry Audit |
| **Chronology Utility** | $\ge 85\%$ rating from lawyers on dated timeline accuracy | Answer Feedback Ratings |
| **Drafting Time Saved** | $\ge 60\%$ reduction in first-draft generation time | Lawyer Exit Interviews |
| **System Reliability** | $\ge 99.5\%$ uptime with 0 unhandled 500 errors | Prometheus Telemetry (`/metrics`) |

---

## 4. Weekly Check-In Agenda Template

```markdown
### Weekly Pilot Sync Agenda (30 Minutes)
1. **Usage Review (5 min)**: Number of matters created, documents uploaded, workflows triggered.
2. **Verification Check (10 min)**: Review instances where Gate A or Gate B repaired or omitted a claim.
3. **Lawyer UX Feedback (10 min)**: Review notes from answer feedback; assess UI clarity.
4. **Action Items & Next Week Focus (5 min)**: Priority workflow targets for next 7 days.
```

---

## 5. Structured Exit Interview Questions

1. **Verifiability vs Fluency**: Did the exact quote citation chips increase your confidence when reviewing drafted petitions compared to conventional generative AI?
2. **Omission Discipline**: When facts were absent from your documents, did the assistant properly state *"Not found in the provided documents"* rather than guessing?
3. **Draft Quality**: How practical were the `[MISSING: description]` placeholders for highlighting missing client instructions?
4. **Timeline & Deadlines**: Did the case chronology and calendar export save time when preparing briefing notes?
5. **UI & Usability**: Was the black-and-white glass interface and Source Drawer intuitive to navigate?
6. **Commercial Viability**: Would your firm adopt this platform for daily litigation preparation?

---

## 6. End-of-Pilot Data Destruction Procedure

Upon completion of the pilot or receipt of a termination notice under the Pilot Agreement:
1. **Data Export**: The advocate downloads all case drafts, chronologies, and data via `/api/user/export-data`.
2. **One-Click Account Purge**: The advocate triggers `DELETE /api/user/account`.
3. **Automated Verification**:
   - Application-level Fernet encrypted disk files in `data/corpus/{user_id}` are unlinked.
   - Database rows in `users`, `matters`, `documents`, `chunks`, `citation_registry`, `chat_history`, `drafts`, and `audit_logs` are deleted.
   - Vector embedding caches and BM25 memory structures for `{user_id}` are cleared.
4. **Certificate of Destruction**: Provider issues a signed confirmation of complete data erasure pursuant to the DPDP Act, 2023.
