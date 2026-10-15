from __future__ import annotations
import time
import math
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from rank_bm25 import BM25Okapi
import numpy as np
from backend.ingestion.pipeline import get_db
from backend.app import config

# Global cache for BM25 and embeddings
_bm25_cache = {}
_dense_model = None
_cross_encoder_model = None

def get_dense_model():
    global _dense_model
    if _dense_model is None:
        try:
            import torch
            torch.set_num_threads(1)
        except Exception:
            pass
        from sentence_transformers import SentenceTransformer
        _dense_model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
    return _dense_model

def get_cross_encoder():
    global _cross_encoder_model
    if _cross_encoder_model is None:
        try:
            import torch
            torch.set_num_threads(1)
        except Exception:
            pass
        from sentence_transformers import CrossEncoder
        _cross_encoder_model = CrossEncoder(config.RERANKER_MODEL_NAME)
    return _cross_encoder_model

def rewrite_query_with_history(query: str, history: List[Dict[str, str]], groq_client=None) -> str:

    """Rewrite follow-up queries using prior chat turns to make them standalone."""
    if not history:
        return query
    
    import re
    # Check if follow-up pronoun or reference exists with word boundaries
    follow_up_patterns = [
        r"\bhe\b", r"\bshe\b", r"\bthey\b", r"\bhis\b", r"\bher\b", r"\btheir\b",
        r"\bsecond accused\b", r"\bco-accused\b", r"\bthat case\b", r"\bsame order\b",
        r"\bwhat about\b", r"\band then\b"
    ]
    is_follow_up = any(re.search(pattern, query.lower()) for pattern in follow_up_patterns)
    
    if not is_follow_up:
        return query

    if groq_client:
        try:
            turns = "\n".join([f"{h['role']}: {h['content']}" for h in history[-3:]])
            resp = groq_client.chat.completions.create(
                model=config.GROQ_FAST_MODEL,
                messages=[{
                    "role": "user",
                    "content": f"Given the conversation history:\n{turns}\n\nRewrite this follow-up into a standalone legal search query:\n\"{query}\"\nReturn ONLY the rewritten query."
                }],
                temperature=0.0,
                max_tokens=60
            )
            rewritten = resp.choices[0].message.content.strip().replace('"', '')
            if len(rewritten) > 5:
                return rewritten
        except Exception:
            pass

    # Heuristic resolution: prepend last user question context
    last_user_turn = next((h["content"] for h in reversed(history) if h["role"] == "user"), "")
    return f"{last_user_turn} {query}".strip()


def get_all_chunks(
    doc_ids: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    if not doc_ids:
        return []
    conn = get_db()
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(doc_ids))
    params = list(doc_ids)

    query = f"""
    SELECT c.chunk_id, c.doc_id, c.page, c.chunk_index, c.text, c.ocr, d.title as doc_title, c.user_id, c.matter_id
    FROM chunks c
    JOIN documents d ON c.doc_id = d.id
    WHERE c.doc_id IN ({placeholders})
    """
    if user_id:
        query += " AND (c.user_id = ? OR d.user_id = ?)"
        params.extend([user_id, user_id])
    if matter_id:
        query += " AND (c.matter_id = ? OR d.matter_id = ?)"
        params.extend([matter_id, matter_id])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

_chunk_embedding_cache: Dict[Tuple[str, str], np.ndarray] = {}
_bm25_cache: Dict[Tuple[str, str, tuple], BM25Okapi] = {}

def get_cached_bm25(chunks: List[Dict[str, Any]], user_id: str = "default_lawyer", matter_id: str = "default_matter") -> BM25Okapi:
    global _bm25_cache
    cache_key = (user_id, matter_id, tuple(c["chunk_id"] for c in chunks))
    if cache_key in _bm25_cache:
        return _bm25_cache[cache_key]
    corpus_tokens = [c["text"].lower().split() for c in chunks]
    bm25 = BM25Okapi(corpus_tokens)
    if len(_bm25_cache) > 50:
        _bm25_cache.clear()
    _bm25_cache[cache_key] = bm25
    return bm25

def get_cached_chunk_embeddings(chunks: List[Dict[str, Any]], model, user_id: str = "default_lawyer") -> np.ndarray:
    global _chunk_embedding_cache
    missing = [c for c in chunks if (user_id, c["chunk_id"]) not in _chunk_embedding_cache]
    if missing:
        missing_texts = [c["text"] for c in missing]
        embs = model.encode(missing_texts, convert_to_numpy=True, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
        for c, emb in zip(missing, embs):
            _chunk_embedding_cache[(user_id, c["chunk_id"])] = emb
    
    return np.array([_chunk_embedding_cache[(user_id, c["chunk_id"])] for c in chunks])

def retrieve(
    query: str, 
    doc_ids: Optional[List[str]] = None, 
    mode: str = "hybrid_rerank", 
    top_k: int = 8,
    user_id: Optional[str] = None,
    matter_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    start_time = time.time()
    chunks = get_all_chunks(doc_ids, user_id=user_id, matter_id=matter_id)
    if not chunks:
        from backend.services.metrics import record_retrieval_latency
        record_retrieval_latency(time.time() - start_time)
        return []
    
    eff_user = user_id or "default_lawyer"
    eff_matter = matter_id or "default_matter"
    
    # 1. Sparse BM25 Retrieval (Cached index partitioned per user & matter)
    bm25 = get_cached_bm25(chunks, user_id=eff_user, matter_id=eff_matter)
    query_tokens = query.lower().split()
    bm25_scores = bm25.get_scores(query_tokens)
    
    # Sort by BM25
    bm25_ranked_indices = np.argsort(bm25_scores)[::-1]
    sparse_ranks = {chunks[idx]["chunk_id"]: rank + 1 for rank, idx in enumerate(bm25_ranked_indices)}
    
    def _finish(res):
        from backend.services.metrics import record_retrieval_latency
        record_retrieval_latency(time.time() - start_time)
        return res

    # If mode is sparse_only
    if mode == "sparse_only":
        results = []
        for rank, idx in enumerate(bm25_ranked_indices[:top_k]):
            item = dict(chunks[idx])
            item["sparse_score"] = float(bm25_scores[idx])
            item["score"] = float(bm25_scores[idx])
            results.append(item)
        return _finish(results)

    # 2. Dense Embeddings Retrieval (Cached chunk vectors)
    try:
        model = get_dense_model()
        chunk_embeddings = get_cached_chunk_embeddings(chunks, model, user_id=eff_user)
        query_embedding = model.encode([query], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)[0]
        dense_scores = np.dot(chunk_embeddings, query_embedding)
        dense_ranked_indices = np.argsort(dense_scores)[::-1]
        dense_ranks = {chunks[idx]["chunk_id"]: rank + 1 for rank, idx in enumerate(dense_ranked_indices)}
    except Exception:
        dense_scores = bm25_scores
        dense_ranked_indices = bm25_ranked_indices
        dense_ranks = sparse_ranks

    if mode == "dense_only":
        results = []
        for rank, idx in enumerate(dense_ranked_indices[:top_k]):
            item = dict(chunks[idx])
            item["dense_score"] = float(dense_scores[idx])
            item["score"] = float(dense_scores[idx])
            results.append(item)
        return _finish(results)

    # 3. Reciprocal Rank Fusion (RRF)
    # RRF score = 1 / (60 + rank_dense) + 1 / (60 + rank_sparse)
    rrf_scores = {}
    for c in chunks:
        cid = c["chunk_id"]
        d_rank = dense_ranks.get(cid, 999)
        s_rank = sparse_ranks.get(cid, 999)
        rrf = (1.0 / (60.0 + d_rank)) + (1.0 / (60.0 + s_rank))
        rrf_scores[cid] = rrf

    sorted_by_rrf = sorted(chunks, key=lambda c: rrf_scores[c["chunk_id"]], reverse=True)
    top_candidates = sorted_by_rrf[:min(10, len(sorted_by_rrf))]

    if mode == "hybrid":
        for c in top_candidates[:top_k]:
            c["score"] = float(rrf_scores[c["chunk_id"]])
        return _finish(top_candidates[:top_k])

    # 4. Cross-Encoder Rerank (top 10 candidates for 10x faster inference)
    try:
        ce = get_cross_encoder()
        pairs = [[query, c["text"]] for c in top_candidates]
        ce_scores = ce.predict(pairs)
        for i, c in enumerate(top_candidates):
            c["score"] = float(ce_scores[i])
        reranked = sorted(top_candidates, key=lambda c: c["score"], reverse=True)
        return _finish(reranked[:top_k])
    except Exception:
        for c in top_candidates[:top_k]:
            c["score"] = float(rrf_scores[c["chunk_id"]])
        return _finish(top_candidates[:top_k])
