from __future__ import annotations

from pathlib import Path

import pytest

from rag_maker.adapters.driven.lancedb.vector_store import LanceVectorStore
from rag_maker.adapters.driven.loaders import loader_for
from rag_maker.application.config import AppConfig
from rag_maker.application.ingest_use_case import IngestUseCase
from rag_maker.application.query_use_case import QueryUseCase
from rag_maker.domain.models import RankedChunk, RetrievedChunk

CORPUS_MINI = Path(__file__).parent.parent / "fixtures" / "corpus_mini"
_DIM = 4


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _FakeEmbedder:
    @property
    def dim(self) -> int:
        return _DIM

    def embed(self, text: str) -> tuple[float, ...]:
        seed = sum(ord(c) for c in text[:10]) % 100
        return tuple(float(seed + i) / 100.0 for i in range(_DIM))

    def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self.embed(t) for t in texts]


class _FakeReranker:
    """Reranker determinístico: score = comprimento do conteúdo (normalizado)."""

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RankedChunk]:
        scored = sorted(chunks, key=lambda c: len(c.chunk.content), reverse=True)
        return [
            RankedChunk(
                chunk=rc.chunk,
                rerank_score=float(len(rc.chunk.content)),
                rrf_score=rc.rrf_score,
            )
            for rc in scored[:top_k]
        ]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "db"
    p.mkdir()
    return p


@pytest.fixture()
def cfg(db_path: Path) -> AppConfig:
    return AppConfig.model_validate({
        "paths": {"db_dir": str(db_path)},
        "retrieval": {"coarse_top_n": 50, "rerank_top_k": 3},
    })


@pytest.fixture()
def populated_store(db_path: Path, cfg: AppConfig) -> LanceVectorStore:
    store = LanceVectorStore(db_path=db_path, embedding_dim=_DIM)
    embedder = _FakeEmbedder()
    uc = IngestUseCase(embedder=embedder, store=store, loader_for=loader_for, config=cfg)
    uc.ingest_incremental(CORPUS_MINI)
    return store


@pytest.fixture()
def query_uc(populated_store: LanceVectorStore, cfg: AppConfig) -> QueryUseCase:
    return QueryUseCase(
        embedder=_FakeEmbedder(),
        store=populated_store,
        reranker=_FakeReranker(),
        config=cfg,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration()
def test_answer_returns_query_result(query_uc: QueryUseCase) -> None:
    result = query_uc.answer("filosofia da mente")
    assert result.query == "filosofia da mente"
    assert len(result.ranked_chunks) > 0
    assert result.latency_ms > 0


@pytest.mark.integration()
def test_answer_respects_top_k(query_uc: QueryUseCase) -> None:
    result = query_uc.answer("texto", top_k=2)
    assert len(result.ranked_chunks) <= 2


@pytest.mark.integration()
def test_rerank_scores_are_non_increasing(query_uc: QueryUseCase) -> None:
    result = query_uc.answer("conhecimento", top_k=3)
    scores = [c.rerank_score for c in result.ranked_chunks]
    assert scores == sorted(scores, reverse=True), f"scores não decrescentes: {scores}"


@pytest.mark.integration()
def test_answer_empty_store_returns_empty(db_path: Path, cfg: AppConfig) -> None:
    store = LanceVectorStore(db_path=db_path, embedding_dim=_DIM)
    uc = QueryUseCase(
        embedder=_FakeEmbedder(),
        store=store,
        reranker=_FakeReranker(),
        config=cfg,
    )
    result = uc.answer("qualquer coisa")
    assert result.ranked_chunks == ()
