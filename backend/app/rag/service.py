"""检索服务入口：按日期构建语料（知识库过期判断依赖日期），同步索引并返回检索器。"""

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
    """每天最多构建一次：跨过某条知识的复核到期日后，它会自动退出语料。"""
    chunks = build_corpus(load_knowledge_base(), load_catalog(), today)
    embedder = get_embedder()
    try:
        factory = sessionmaker(bind=get_engine())
        with factory() as session:
            session.execute(text("SELECT 1"))
            sync_index(session, chunks, embedder)
        store = PgVectorStore(factory, embedder.model_name)
    except Exception:
        # 数据库不可用时退化为内存检索，保证问答可用；日志中记录以便排查
        logger.warning("pgvector unavailable, falling back to in-memory vectors", exc_info=True)
        store = InMemoryVectorStore(chunks, embedder)
    return Retriever(chunks, embedder, store)
