"""Fusing hybrid search results: RRF (reciprocal rank fusion).

Uses only each list's ranks, not raw scores, so vector similarity and BM25 scores don't need a
common scale or weights.
"""

RRF_K = 60  # common value; dampens the influence of low-ranked results


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))
