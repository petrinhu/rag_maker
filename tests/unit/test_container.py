from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from rag_maker.application.config import AppConfig
from rag_maker.application.ingest_use_case import IngestUseCase
from rag_maker.application.query_use_case import QueryUseCase
from rag_maker.composition.container import Container, build_container
from rag_maker.domain.models import RankedChunk, RetrievedChunk
from rag_maker.domain.ports.embedder import EmbedderPort
from rag_maker.domain.ports.reranker import RerankerPort
from rag_maker.domain.ports.vector_store import VectorStorePort

_DIM = 4


# ── Fakes ─────────────────────────────────────────────────────────────────────


class _FakeEmbedder:
    @property
    def dim(self) -> int:
        return _DIM

    def embed(self, text: str) -> tuple[float, ...]:
        return (0.1, 0.2, 0.3, 0.4)

    def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self.embed(t) for t in texts]


class _FakeStore:
    def upsert(self, chunks: list[Any]) -> None: ...

    def delete_by_source(self, source_path: str) -> None: ...

    def hybrid_search(
        self, vector: tuple[float, ...], text: str, top_n: int
    ) -> list[RetrievedChunk]:
        return []

    def count(self) -> int:
        return 0

    def stats(self) -> dict[str, Any]:
        return {}

    def list_sources(self) -> dict[str, int]:
        return {}

    def ensure_fts_index(self) -> None: ...

    def ensure_vector_index(self) -> None: ...


class _FakeReranker:
    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RankedChunk]:
        return []


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def container(tmp_path: Path) -> Container:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[paths]\ndb_dir = "{tmp_path / "db"}"\n')
    return build_container(
        config_path=cfg_file,
        embedder=_FakeEmbedder(),
        store=_FakeStore(),
        reranker=_FakeReranker(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
def test_container_has_correct_types(container: Container) -> None:
    assert isinstance(container.embedder, EmbedderPort)
    assert isinstance(container.store, VectorStorePort)
    assert isinstance(container.reranker, RerankerPort)
    assert isinstance(container.ingest, IngestUseCase)
    assert isinstance(container.query, QueryUseCase)


@pytest.mark.unit()
def test_ingest_use_case_shares_embedder(container: Container) -> None:
    assert container.ingest._embedder is container.embedder


@pytest.mark.unit()
def test_ingest_use_case_shares_store(container: Container) -> None:
    assert container.ingest._store is container.store


@pytest.mark.unit()
def test_query_use_case_shares_embedder(container: Container) -> None:
    assert container.query._embedder is container.embedder


@pytest.mark.unit()
def test_query_use_case_shares_store(container: Container) -> None:
    assert container.query._store is container.store


@pytest.mark.unit()
def test_query_use_case_shares_reranker(container: Container) -> None:
    assert container.query._reranker is container.reranker


@pytest.mark.unit()
def test_config_is_app_config(container: Container) -> None:
    assert isinstance(container.config, AppConfig)


@pytest.mark.unit()
def test_build_container_propagates_reranker_revision_pin(tmp_path: Path) -> None:
    """AUD-SEC-5 / F12.18 fim-a-fim: o pin `[reranker].revision` do TOML

    precisa chegar ao `CrossEncoderReranker` construído por `build_container`
    no caminho de produção (sem override de `reranker=`) — caso contrário o
    pin fica inerte na CLI/GUI mesmo configurado. Não instancia o modelo real
    (lazy load só ocorre em `rerank()`/`_get_model()`).
    """
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        f'[paths]\ndb_dir = "{tmp_path / "db"}"\n[reranker]\nrevision = "deadbeef"\n'
    )

    result = build_container(
        config_path=cfg_file,
        embedder=_FakeEmbedder(),
        store=_FakeStore(),
        # reranker NÃO sobrescrito: exercita a construção real de
        # CrossEncoderReranker dentro de build_container.
    )

    assert result.config.reranker.revision == "deadbeef"
    assert result.reranker._revision == "deadbeef"  # type: ignore[attr-defined]
