"""向量模型适配层（fastembed，本地 ONNX 推理，无需 GPU 与外部 API）。"""

from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

from app.core.config import get_settings


class Embedder:
    def __init__(self, model_name: str, query_instruction: str = ""):
        self.model_name = model_name
        self.query_instruction = query_instruction
        self._model = TextEmbedding(model_name)

    @property
    def dim(self) -> int:
        return len(self.embed_query("测试"))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.array(list(self._model.embed(texts)), dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        # BGE 中文模型建议查询一侧加检索指令；文档一侧不加
        return np.array(
            next(iter(self._model.embed([self.query_instruction + text]))), dtype=np.float32
        )


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    return Embedder(s.embedding_model, s.embedding_query_instruction)
