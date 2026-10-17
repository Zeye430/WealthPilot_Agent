"""混合检索的结果融合：RRF（倒数排名融合）。

只看各路结果的排名、不看原始分数，因此不必把向量相似度与 BM25 分数换算到同一尺度，也不需要调权重。
"""

RRF_K = 60  # 常用取值，抑制排名靠后结果的影响


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))
