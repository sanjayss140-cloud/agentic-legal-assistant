import math
import sqlite3
from typing import List, Dict, Any, Optional
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
        from sentence_transformers import SentenceTransformer
        _dense_model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
    return _dense_model

def get_cross_encoder():
    global _cross_encoder_model
    if _cross_encoder_model is None:
        from sentence_transformers import CrossEncoder
        _cross_encoder_model = CrossEncoder(config.RERANKER_MODEL_NAME)
    return _cross_encoder_model

def get_all_chunks(doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    if doc_ids and len(doc_ids) > 0:
        placeholders = ",".join(["?"] * len(doc_ids))
        cursor.execute(f"""
        SELECT c.chunk_id, c.doc_id, c.page, c.chunk_index, c.text, c.ocr, d.title as doc_title
        FROM chunks c
        JOIN documents d ON c.doc_id = d.id
        WHERE c.doc_id IN ({placeholders})
        """, doc_ids)
    else:
        cursor.execute("""
        SELECT c.chunk_id, c.doc_id, c.page, c.chunk_index, c.text, c.ocr, d.title as doc_title
        FROM chunks c
        JOIN documents d ON c.doc_id = d.id
        """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def retrieve(query: str, doc_ids: Optional[List[str]] = None, mode: str = "hybrid_rerank", top_k: int = 8) -> List[Dict[str, Any]]:
    chunks = get_all_chunks(doc_ids)
    if not chunks:
        return []
    
    # 1. Sparse BM25 Retrieval
    corpus_tokens = [c["text"].lower().split() for c in chunks]
    bm25 = BM25Okapi(corpus_tokens)
    query_tokens = query.lower().split()
    bm25_scores = bm25.get_scores(query_tokens)
    
    # Sort by BM25
    bm25_ranked_indices = np.argsort(bm25_scores)[::-1]
    sparse_ranks = {chunks[idx]["chunk_id"]: rank + 1 for rank, idx in enumerate(bm25_ranked_indices)}
    
    # If mode is sparse_only (or for fast fallback)
    if mode == "sparse_only":
        results = []
        for rank, idx in enumerate(bm25_ranked_indices[:top_k]):
            item = dict(chunks[idx])
            item["sparse_score"] = float(bm25_scores[idx])
            item["score"] = float(bm25_scores[idx])
            results.append(item)
        return results

    # 2. Dense Embeddings Retrieval
    try:
        model = get_dense_model()
        chunk_texts = [c["text"] for c in chunks]
        chunk_embeddings = model.encode(chunk_texts, convert_to_numpy=True, normalize_embeddings=True)
        query_embedding = model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
        dense_scores = np.dot(chunk_embeddings, query_embedding)
        dense_ranked_indices = np.argsort(dense_scores)[::-1]
        dense_ranks = {chunks[idx]["chunk_id"]: rank + 1 for rank, idx in enumerate(dense_ranked_indices)}
    except Exception:
        # Fallback if sentence_transformers encoutered memory/timeout
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
        return results

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
    top_candidates = sorted_by_rrf[:30]

    if mode == "hybrid":
        for c in top_candidates[:top_k]:
            c["score"] = float(rrf_scores[c["chunk_id"]])
        return top_candidates[:top_k]

    # 4. Cross-Encoder Rerank
    try:
        ce = get_cross_encoder()
        pairs = [[query, c["text"]] for c in top_candidates]
        ce_scores = ce.predict(pairs)
        for i, c in enumerate(top_candidates):
            c["score"] = float(ce_scores[i])
        reranked = sorted(top_candidates, key=lambda c: c["score"], reverse=True)
        return reranked[:top_k]
    except Exception:
        # Fallback to RRF order
        for c in top_candidates[:top_k]:
            c["score"] = float(rrf_scores[c["chunk_id"]])
        return top_candidates[:top_k]
