"""Hybrid search: vector + keyword, fused with RRF, combined by per-source quotas.

Search scope (consistent with the suitability rules):
- No product named: knowledge base only (product discovery is search_products' job; RAG doesn't
recommend).
- Product named: the top 2 sections of its prospectus + 1 knowledge-base entry. Product terms are
the main basis; the knowledge base adds general explanation.
  Evaluation showed that without quotas, general entries often ranked above the product's own terms
  (6 of 24 not first).
"""

from typing import Protocol

import numpy as np
from pydantic import BaseModel

from app.rag.corpus import Chunk, ChunkKind
from app.rag.embeddings import Embedder
from app.rag.fusion import rrf
from app.rag.keyword import KeywordIndex

CANDIDATES_PER_ROUTE = 10
PRODUCT_QUOTA, KNOWLEDGE_QUOTA = 2, 1
KNOWLEDGE_ONLY_QUOTA = 3
# When searching within one product's prospectus, these words just refer to that product and don't
# score
PRODUCT_REFERENCE_WORDS = frozenset({"产品", "理财", "说明书"})
# Confidence thresholds (no product named): if both vector similarity and keyword score are below
# them, treat it as "not found in the sources".
# Calibrated on the evaluation set (2026-10-17): positives have similarity 0.53-0.82 and BM25
# 5.2-33.2;
# negatives (uncovered topics such as income tax, US stocks, insurance) 0.41-0.51 and BM25 0-5.9.
# Small sample; revisit as the set grows.
MIN_SIMILARITY = 0.55
MIN_KEYWORD_SCORE = 8.0


class VectorStore(Protocol):
    def search(self, query_vec: np.ndarray, allowed: set[str], k: int) -> list[tuple[str, float]]:
        """Return (chunk_id, cosine similarity), sorted by similarity descending."""


class InMemoryVectorStore:
    """For evaluation and unit tests; production uses PgVectorStore (app/rag/store.py)."""

    def __init__(self, chunks: list[Chunk], embedder: Embedder):
        self.ids = [c.chunk_id for c in chunks]
        self.vecs = embedder.embed_documents([c.search_text for c in chunks])

    def search(self, query_vec, allowed, k):
        sims = self.vecs @ query_vec
        order = [i for i in np.argsort(-sims) if self.ids[i] in allowed]
        return [(self.ids[i], float(sims[i])) for i in order[:k]]


class Hit(BaseModel):
    chunk: Chunk
    similarity: float | None  # vector similarity (None for keyword-only hits)


class RetrievalResult(BaseModel):
    hits: list[Hit]
    confident: bool


class Retriever:
    def __init__(self, chunks: list[Chunk], embedder: Embedder, store: VectorStore):
        self.by_id = {c.chunk_id: c for c in chunks}
        self.embedder = embedder
        self.store = store
        self.keyword = KeywordIndex(chunks)

    def _rank(self, query: str, query_vec: np.ndarray, allowed: set[str], drop=frozenset()):
        vec = self.store.search(query_vec, allowed, CANDIDATES_PER_ROUTE)
        kw = self.keyword.search(query, allowed, CANDIDATES_PER_ROUTE, drop)
        sims = dict(vec)
        fused = rrf([[cid for cid, _ in vec], [cid for cid, _ in kw]])
        top_kw = kw[0][1] if kw else 0.0
        return [(cid, sims.get(cid)) for cid, _ in fused], top_kw, max(sims.values(), default=0.0)

    def search(self, query: str, product_code: str | None = None) -> RetrievalResult:
        query_vec = self.embedder.embed_query(query)
        knowledge = {cid for cid, c in self.by_id.items() if c.kind is ChunkKind.KNOWLEDGE}
        kb_ranked, kb_kw, kb_sim = self._rank(query, query_vec, knowledge)

        if product_code:
            product = {cid for cid, c in self.by_id.items() if c.product_code == product_code}
            doc_ranked, _, _ = self._rank(query, query_vec, product, PRODUCT_REFERENCE_WORDS)
            picked = doc_ranked[:PRODUCT_QUOTA] + kb_ranked[:KNOWLEDGE_QUOTA]
            # When a product is named, its prospectus is always relevant, so the answer counts as
            # grounded
            confident = bool(doc_ranked)
        else:
            picked = kb_ranked[:KNOWLEDGE_ONLY_QUOTA]
            confident = kb_kw >= MIN_KEYWORD_SCORE or kb_sim >= MIN_SIMILARITY
        return RetrievalResult(
            hits=[Hit(chunk=self.by_id[cid], similarity=sim) for cid, sim in picked],
            confident=confident and bool(picked),
        )
