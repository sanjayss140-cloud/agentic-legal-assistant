# PROJECT CHARTER: Agentic Legal Assistant

MISSION: An agentic legal assistant where every fact and every citation is verifiable. Verifiability beats fluency.

JUDGING RUBRIC WE MUST WIN:
- Groundedness vs baseline: % of claims traceable to a real source (35%)
- Zero fabricated facts/citations (PASS/FAIL gate)
- Retrieval quality vs baseline (20%)
- Usefulness of the drafted/answered output (20%)
- Research contribution: ablation/comparison vs baseline (25%)
- Bonus: contradiction detection, missing-info report, extra workflows
Judges bring UNSEEN documents and queries with known correct sources.

WORKFLOWS: (1) Case review, (2) Legal drafting, (3) Legal research, (4) Grounded RAG chat. Depth beats breadth. Order of build: RAG chat, case review, drafting, research.

NON-NEGOTIABLE RULES:
R1. No claim without a source quote. Every claim = {text, chunk_id, exact_quote}.
R2. A quote must literally exist in the cited chunk (deterministic check).
R3. Any statute or case named in an answer must exist in the corpus citation registry, otherwise it is blocked.
R4. If evidence is missing, say "Not found in the provided documents". Never guess. Never fill facts from model memory.
R5. Temperature 0 to 0.2 for all generation.
R6. Never invent imports, APIs or library functions. Use only installed libraries, and verify an import works before using it.
R7. Secrets stay in .env, which is in .gitignore.
R8. The system is decision support for lawyers, not legal advice.

STACK: Python 3.11, FastAPI, PyMuPDF, pytesseract (OCR fallback), rank_bm25, sentence-transformers (bge-small-en or similar), FAISS, a cross-encoder reranker, Groq API, SQLite, React+Vite frontend.
