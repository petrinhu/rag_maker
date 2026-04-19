from __future__ import annotations


def rrf_fuse(
    dense_hits: list[str],
    lexical_hits: list[str],
    k: int = 60,
) -> dict[str, float]:
    """Reciprocal Rank Fusion sobre dois rankings de chunk_ids.

    Retorna {chunk_id: rrf_score}. Função pura, sem I/O.
    """
    scores: dict[str, float] = {}
    for rank, cid in enumerate(dense_hits, start=1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    for rank, cid in enumerate(lexical_hits, start=1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores
