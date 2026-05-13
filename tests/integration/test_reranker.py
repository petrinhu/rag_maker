from __future__ import annotations

from pathlib import Path

import pytest

from rag_maker.adapters.driven.cross_encoder.reranker import CrossEncoderReranker
from rag_maker.domain.models import Chunk, RankedChunk, RetrievedChunk

_HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"
_MODEL_CACHED = (_HF_CACHE / "models--BAAI--bge-reranker-v2-m3").exists()


def _make_retrieved(chunk_id: str, content: str, rrf: float = 0.5) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=chunk_id,
        document_path=Path("doc.txt"),
        content=content,
        char_offset=0,
        mtime=0.0,
    )
    return RetrievedChunk(chunk=chunk, dense_score=rrf, lexical_score=rrf, rrf_score=rrf)


@pytest.mark.integration
class TestCrossEncoderReranker:
    def test_empty_chunks_returns_empty(self) -> None:
        reranker = CrossEncoderReranker()
        result = reranker.rerank("query", [], top_k=5)
        assert result == []

    @pytest.mark.skipif(
        not _MODEL_CACHED,
        reason="BAAI/bge-reranker-v2-m3 não está no cache HuggingFace (~500MB). "
        "Execute 'rag doctor' ou baixe o modelo antes de rodar este teste.",
    )
    def test_rerank_orders_by_relevance(self) -> None:
        reranker = CrossEncoderReranker()
        chunks = [
            _make_retrieved("irrelevante", "receita de bolo de chocolate"),
            _make_retrieved("relevante", "hermetismo e filosofia ocidental"),
        ]
        results = reranker.rerank("filosofia hermética", chunks, top_k=2)
        assert isinstance(results, list)
        assert all(isinstance(r, RankedChunk) for r in results)
        assert results[0].chunk.chunk_id == "relevante"

    @pytest.mark.skipif(
        not _MODEL_CACHED,
        reason="BAAI/bge-reranker-v2-m3 não está no cache HuggingFace (~500MB).",
    )
    def test_top_k_respected(self) -> None:
        reranker = CrossEncoderReranker()
        chunks = [_make_retrieved(f"c{i}", f"texto {i}") for i in range(5)]
        results = reranker.rerank("texto", chunks, top_k=2)
        assert len(results) == 2

    @pytest.mark.skipif(
        not _MODEL_CACHED,
        reason="BAAI/bge-reranker-v2-m3 não está no cache HuggingFace (~500MB).",
    )
    def test_scores_descending(self) -> None:
        reranker = CrossEncoderReranker()
        chunks = [_make_retrieved(f"c{i}", f"documento {i}") for i in range(3)]
        results = reranker.rerank("documento relevante", chunks, top_k=3)
        scores = [r.rerank_score for r in results]
        assert scores == sorted(scores, reverse=True)
