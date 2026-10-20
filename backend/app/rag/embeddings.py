"""Embedding model adapter (fastembed: local ONNX inference, no GPU or external API)."""

from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

from app.core.config import get_settings


class Embedder:
    def __init__(self, model_name: str, query_instruction: str = ""):
        self.model_name = model_name
        self.query_instruction = query_instruction
        cache = get_settings().embedding_cache_dir
        self._model = TextEmbedding(model_name, cache_dir=str(cache) if cache else None)

    @property
    def dim(self) -> int:
        return len(self.embed_query("测试"))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.array(list(self._model.embed(texts)), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        # BGE Chinese models recommend a retrieval instruction on the query side only, not on
        # documents
        return np.array(
            next(iter(self._model.embed([self.query_instruction + text]))), dtype=np.float32
        )


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    return Embedder(s.embedding_model, s.embedding_query_instruction)
