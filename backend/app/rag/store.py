"""pgvector store and incremental index sync.

document_chunks is a derived index that can be rebuilt any time: the only source of the corpus is
the knowledge-base and prospectus files.
Sync compares content hashes, recomputes vectors only for new or changed chunks, and deletes chunks
no longer in the corpus
(e.g. a knowledge-base entry that expired or was retired leaves the index at the next sync).
"""

import logging

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk
from app.rag.corpus import Chunk
from app.rag.embeddings import Embedder

logger = logging.getLogger(__name__)


class PgVectorStore:
    def __init__(self, session_factory, model_name: str):
        self.session_factory = session_factory
        self.model_name = model_name

    def search(self, query_vec: np.ndarray, allowed: set[str], k: int) -> list[tuple[str, float]]:
        distance = DocumentChunk.embedding.cosine_distance(query_vec.tolist())
        with self.session_factory() as session:
            rows = session.execute(
                select(DocumentChunk.chunk_id, distance)
                .where(
                    DocumentChunk.chunk_id.in_(allowed),
                    DocumentChunk.embedding_model == self.model_name,
                )
                .order_by(distance)
                .limit(k)
            ).all()
        return [(cid, 1.0 - float(d)) for cid, d in rows]


def sync_index(session: Session, chunks: list[Chunk], embedder: Embedder) -> dict[str, int]:
    existing = {
        cid: (h, model)
        for cid, h, model in session.execute(
            select(
                DocumentChunk.chunk_id, DocumentChunk.content_hash, DocumentChunk.embedding_model
            )
        )
    }
    current = {c.chunk_id: c for c in chunks}
    changed = [
        c for c in chunks if existing.get(c.chunk_id) != (c.content_hash, embedder.model_name)
    ]
    removed = set(existing) - set(current)

    if changed:
        vectors = embedder.embed_documents([c.search_text for c in changed])
        for chunk, vec in zip(changed, vectors, strict=True):
            session.merge(
                DocumentChunk(
                    chunk_id=chunk.chunk_id,
                    kind=chunk.kind.value,
                    product_code=chunk.product_code,
                    content_hash=chunk.content_hash,
                    embedding_model=embedder.model_name,
                    embedding=vec.tolist(),
                )
            )
    if removed:
        session.execute(delete(DocumentChunk).where(DocumentChunk.chunk_id.in_(removed)))
    session.commit()
    stats = {"total": len(chunks), "embedded": len(changed), "removed": len(removed)}
    logger.info("document index synced: %s", stats)
    return stats
