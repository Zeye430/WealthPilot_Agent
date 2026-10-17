"""混合检索：向量 + 关键词，RRF 融合，按来源配额组合结果。

检索范围（与适当性规则一致）：
- 未点名产品：只检索知识库（产品发现由 search_products 负责，RAG 不做推荐）。
- 点名产品：该产品说明书前 2 个章节 + 知识库 1 条。产品条款是主要依据，知识库补充一般解释。
  评估显示，不分配额时通用知识条目常排在产品自身条款之前（6/24 条未排第一）。
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
# 限定在某款产品说明书内检索时，这些词只是指代该产品，不参与关键词计分
PRODUCT_REFERENCE_WORDS = frozenset({"产品", "理财", "说明书"})
# 置信度阈值（未点名产品时）：向量相似度与关键词分数都低于阈值，视为「资料中未找到」。
# 依据评估集校准（2026-10-17）：正例相似度 0.53–0.82、BM25 5.2–33.2；
# 负例（个税、美股、保险等未覆盖话题）相似度 0.41–0.51、BM25 0–5.9。样本小，需随评估集扩充复核。
MIN_SIMILARITY = 0.55
MIN_KEYWORD_SCORE = 8.0


class VectorStore(Protocol):
    def search(self, query_vec: np.ndarray, allowed: set[str], k: int) -> list[tuple[str, float]]:
        """返回 (chunk_id, 余弦相似度)，按相似度降序。"""


class InMemoryVectorStore:
    """评估与单元测试用；线上使用 PgVectorStore（app/rag/store.py）。"""

    def __init__(self, chunks: list[Chunk], embedder: Embedder):
        self.ids = [c.chunk_id for c in chunks]
        self.vecs = embedder.embed_documents([c.search_text for c in chunks])

    def search(self, query_vec, allowed, k):
        sims = self.vecs @ query_vec
        order = [i for i in np.argsort(-sims) if self.ids[i] in allowed]
        return [(self.ids[i], float(sims[i])) for i in order[:k]]


class Hit(BaseModel):
    chunk: Chunk
    similarity: float | None  # 向量相似度（仅关键词命中时为 None）


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
            # 点名产品时，产品说明书一定相关，视为有依据
            confident = bool(doc_ranked)
        else:
            picked = kb_ranked[:KNOWLEDGE_ONLY_QUOTA]
            confident = kb_kw >= MIN_KEYWORD_SCORE or kb_sim >= MIN_SIMILARITY
        return RetrievalResult(
            hits=[Hit(chunk=self.by_id[cid], similarity=sim) for cid, sim in picked],
            confident=confident and bool(picked),
        )
