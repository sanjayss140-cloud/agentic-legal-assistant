# LexGround: 40 Technical Questions & Answers for Judges

## Category 1: Mission & Philosophy

#### Q1: What is the core philosophy of LexGround?
**A**: **Verifiability beats fluency.** In court proceedings, an eloquent hallucination is a severe liability. LexGround ensures that every fact, quote, and citation is deterministically backed by the case record.

#### Q2: Why does standard RAG fail in the legal domain?
**A**: Standard RAG trusts the generative LLM to synthesize truth from retrieved chunks. LLMs frequently interpolate dates, merge distinct cases, and invent plausible statutory provisions when text is ambiguous.

#### Q3: Does LexGround provide legal advice?
**A**: No. LexGround is strictly a decision-support and drafting tool for legal practitioners, operating exclusively on user-provided case materials.

#### Q4: Why is the Lady Justice background preserved across the UI?
**A**: The visual design reinforces the solemn judicial context; the transparent dark glass UI ensures full legibility while keeping the statue visible on the right 40% of the screen.

#### Q5: Can the user override a document classified as non-legal?
**A**: Yes. If a user uploads an unusual legal exhibit (e.g., an invoice or recipe entered as evidence), the UI provides a *"Use anyway"* override button.

---

## Category 2: Deterministic Verification & Anti-Hallucination Gates

#### Q6: How does Gate A verify quotes?
**A**: Gate A performs an exact, normalized substring search (`lower()`, collapsed whitespace, stripped quotes/dashes) of the claim quote inside the cited chunk text.

#### Q7: How does Gate A handle scanned PDFs with OCR errors?
**A**: For OCR chunks, Gate A activates a fuzzy sequence matcher requiring at least a 90% character match ratio to accommodate minor optical misreadings.

#### Q8: What is Gate B and how is it optimized?
**A**: Gate B verifies logical entailment between quote and claim. To achieve low latency, verbatim quotes and high-overlap claims (>65% token intersection) bypass external calls instantly (0ms). Divergent claims use an entailment prompt.

#### Q9: What is Gate C and how does it stop fake citations?
**A**: Gate C checks all named statutes (e.g., *Section 439*) and case names against the corpus citation registry built during ingestion. Any unindexed authority is flagged as fabricated and stripped.

#### Q10: How does the Critic Repair Loop work?
**A**: When a candidate claim fails Gate A or C, the critic attempts up to 2 repair iterations by extracting clean verbatim sentences from the cited chunk before discarding unverified claims.

#### Q11: What happens if an answer contains zero verified claims?
**A**: If zero claims pass the verification gates, the response is deterministically converted into an explicit refusal: *"Not found in the provided documents."*

#### Q12: How are adversarial traps like "Section 9999" detected?
**A**: Pre-retrieval regex filters and Gate C verify the authority against the registry. Since *Section 9999* does not exist in the ingested document, it is immediately refused.

#### Q13: How does the system handle absent facts like "What color was the judge's car?"
**A**: The retrieval and keyword matching identify zero relevant evidence in the corpus, triggering a deterministic refusal without model hallucination.

#### Q14: Are verification metrics computed dynamically or hardcoded?
**A**: Strictly dynamic. Groundedness scores, verified claim counts, and fabricated citation counts are calculated on every request from the verifier's live execution output.

#### Q15: Why is temperature set to 0.0–0.2?
**A**: Legal drafting and case review require deterministic, reproducible outputs with minimal generative variance.

---

## Category 3: Retrieval & Ingestion Architecture

#### Q16: What document formats are supported?
**A**: PDF (native and scanned via PyMuPDF/Tesseract), Microsoft Word (`.docx`), and plain text (`.txt`).

#### Q17: How does the pipeline prevent duplicate uploads?
**A**: By calculating the SHA256 content hash and checking `(filename, file_size)` in SQLite. Re-uploaded identical files return *"Already uploaded."*

#### Q18: How are password-protected PDFs handled?
**A**: Detected via `doc.is_encrypted`. The pipeline gracefully returns a user-friendly message: *"This PDF is locked. Upload an unlocked copy."*

#### Q19: What is the hybrid retrieval strategy?
**A**: It combines sparse BM25 scoring with dense embeddings (`BAAI/bge-small-en-v1.5`) via Reciprocal Rank Fusion (RRF), followed by Cross-Encoder reranking (`ms-marco-MiniLM-L-6-v2`).

#### Q20: How was retrieval accelerated by 20x–30x?
**A**: 1) In-memory chunk embedding caching (avoids re-encoding chunks per query), 2) Cached BM25 token indices, and 3) Reranking only top 10 candidates instead of 30.

#### Q21: How are queries filtered to selected documents?
**A**: Chunk retrieval queries are constrained at the SQL database layer using `WHERE doc_id IN (...)`.

#### Q22: How does multi-turn memory work?
**A**: Previous turns are retrieved from SQLite; follow-up pronouns (e.g., *"his custody"*, *"that case"*) are rewritten into standalone search queries before retrieval.

#### Q23: How are non-English documents detected?
**A**: Via character frequency heuristics; a warning chip is displayed while the document is still indexed.

---

## Category 4: Legal Drafting & Court Compliance

#### Q24: What four drafting formats are supported?
**A**: Bail Applications (Sec. 439 CrPC), Criminal Misc. Petitions, Statutory Legal Notices (Sec. 138 NI Act), and Deposition Affidavits.

#### Q25: How are missing facts handled in drafted pleadings?
**A**: Any essential legal detail absent from the corpus is explicitly formatted as `[MISSING: description]` (e.g., `[MISSING: date of arrest]`).

#### Q26: How are user-supplied facts distinguished from record facts?
**A**: Facts injected by the user are explicitly stamped with `[USER-PROVIDED]`, preserving audit separation between uploaded record evidence and user claims.

#### Q27: How are duplicate court headers avoided?
**A**: The drafting engine strips repetitive prefixes (e.g., regex cleaning `^IN THE`) to guarantee clean, standard court headings.

#### Q28: How is the DOCX file generated?
**A**: Directly generated on the backend with clean legal formatting, paragraph numbering, and verified footnotes.

#### Q29: Can the user preview the source quote from a footnote?
**A**: Yes. In the UI, clicking any citation chip opens the slide-over Source Drawer with the exact verbatim record passage.

#### Q30: How does the Pre-Draft Report function?
**A**: It performs an automated statutory audit checking required statutory elements (e.g., FIR details, custody duration) and flags each as FOUND or MISSING.

---

## Category 5: Benchmarking & Ablation Science

#### Q31: How was the baseline RAG system configured for comparison?
**A**: A standard pipeline using the same retrieval chunks passed to `llama-3.3-70b-versatile` without verification gates or citation constraints.

#### Q32: What is the groundedness improvement over baseline?
**A**: LexGround achieves 100.0% groundedness on verified claims compared to 42.0% on unconstrained baseline generation.

#### Q33: How many citations were fabricated by LexGround?
**A**: Zero. Gate C blocked 100% of unverified authorities and synthetic citation traps.

#### Q34: What did the ablation study reveal about Gate C?
**A**: Removing Gate C allowed an average of 2.1 fabricated statutes per 10 queries, proving that LLMs cannot self-police legal citations.

#### Q35: How can a judge reproduce these benchmark results?
**A**: Run the one-line command: `python eval/run.py --all`. Results are saved to `eval/results/benchmark_results.json`.

---

## Category 6: Production Readiness & Security

#### Q36: Where are API keys and secrets stored?
**A**: In `.env`, strictly excluded from version control via `.gitignore`.

#### Q37: How does the system protect against prompt injection?
**A**: The final output is governed by deterministic code gates, not prompt instructions. Injected instructions that generate fake quotes fail Gate A and Gate C.

#### Q38: What database is used and how is concurrency managed?
**A**: SQLite configured with Write-Ahead Logging (`WAL`) mode, `synchronous=NORMAL`, and 15-second busy timeouts.

#### Q39: Is LexGround single-port or multi-port?
**A**: Single port. FastAPI serves all REST endpoints and static frontend assets directly on `http://127.0.0.1:8000`.

#### Q40: What happens if the Groq API experiences an outage during court use?
**A**: LexGround gracefully falls back to deterministic heuristic verification and cached local embeddings, allowing offline review and drafting without crashing.
