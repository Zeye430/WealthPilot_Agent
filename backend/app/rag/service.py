"""Search service entry point: build the corpus for a date (knowledge-base expiry depends on it),
sync the index and return a retriever."""

import logging
from datetime import date
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db.session import get_engine
from app.knowledge.kb import load_knowledge_base
from app.products.catalog import load_catalog
from app.rag.corpus import build_corpus
from app.rag.embeddings import get_embedder
from app.rag.retriever import InMemoryVectorStore, Retriever
from app.rag.store import PgVectorStore, sync_index

logger = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def get_retriever(today: date) -> Retriever:
    """Built at most once a day: once an entry passes its review date, it drops out of the corpus
    automatically."""
    chunks = build_corpus(load_knowledge_base(), load_catalog(), today)
    embedder = get_embedder()
    try:
        factory = sessionmaker(bind=get_engine())
        with factory() as session:
            session.execute(text("SELECT 1"))
            sync_index(session, chunks, embedder)
        store = PgVectorStore(factory, embedder.model_name)
    except Exception:
        # If the database is down, fall back to in-memory search so Q&A keeps working; log it for
        # investigation
        logger.warning("pgvector unavailable, falling back to in-memory vectors", exc_info=True)
        store = InMemoryVectorStore(chunks, embedder)
    return Retriever(chunks, embedder, store)
