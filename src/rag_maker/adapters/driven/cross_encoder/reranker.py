from __future__ import annotations

from typing import Any

from sentence_transformers import CrossEncoder

from rag_maker.domain.models import RankedChunk, RetrievedChunk


class CrossEncoderReranker:
    """Implementa RerankerPort com BAAI/bge-reranker-v2-m3 (singleton lazy).

    O modelo é carregado na primeira chamada a rerank() — pode demorar ~30s.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "auto",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model: CrossEncoder | None = None

    def _get_model(self) -> CrossEncoder:
        if self._model is None:
            self._model = CrossEncoder(self._model_name, device=self._device)
        return self._model

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RankedChunk]:
        if not chunks:
            return []
        model = self._get_model()
        pairs: Any = [(query, c.chunk.content) for c in chunks]
        raw_scores: list[float] = model.predict(pairs).tolist()
        ranked = sorted(zip(chunks, raw_scores, strict=True), key=lambda x: x[1], reverse=True)
        return [
            RankedChunk(chunk=rc.chunk, rerank_score=float(s), rrf_score=rc.rrf_score)
            for rc, s in ranked[:top_k]
        ]
