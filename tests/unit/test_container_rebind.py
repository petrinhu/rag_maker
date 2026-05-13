from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rag_maker.composition.container import Container, build_container
from rag_maker.domain.models import RankedChunk, RetrievedChunk

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
    def __init__(self, db_path: Path | None = None, embedding_dim: int = _DIM) -> None:
        self.db_path = db_path
        self.embedding_dim = embedding_dim

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


class _FakeReranker:
    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RankedChunk]:
        return []


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def cfg_file(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    corpus = tmp_path / "corpus_A"
    corpus.mkdir()
    cfg.write_text(f'[paths]\ncorpus_dir = "{corpus}"\ndb_dir = "{corpus / "rag"}"\n')
    return cfg


@pytest.fixture()
def container(cfg_file: Path, monkeypatch: pytest.MonkeyPatch) -> Container:
    # Redireciona qualquer leitura/escrita ao arquivo XDG para o cfg_file do teste,
    # evitando que o teste mexa em ~/.config/rag_maker/config.toml.
    from rag_maker.application import config as config_mod
    from rag_maker.composition import container as container_mod

    monkeypatch.setattr(config_mod, "_xdg_config_file", lambda: cfg_file)
    monkeypatch.setattr(container_mod, "_xdg_config_file", lambda: cfg_file)
    monkeypatch.setattr(container_mod, "LanceVectorStore", _FakeStore)

    c = build_container(
        config_path=cfg_file,
        embedder=_FakeEmbedder(),
        store=_FakeStore(),
        reranker=_FakeReranker(),
    )
    c.config = c.config.model_copy(update={"embedding_dim": _DIM})
    return c


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.unit()
def test_rebind_to_new_dir_returns_true_and_creates_rag(
    container: Container, tmp_path: Path
) -> None:
    new_corpus = tmp_path / "corpus_B"
    new_corpus.mkdir()

    changed = container.rebind_to_corpus(new_corpus)

    assert changed is True
    assert (new_corpus / "rag").is_dir()


@pytest.mark.unit()
def test_rebind_to_same_dir_returns_false(container: Container) -> None:
    current = container.config.paths.corpus_dir
    assert current is not None

    changed = container.rebind_to_corpus(current)

    assert changed is False


@pytest.mark.unit()
def test_rebind_to_nonexistent_raises_value_error(container: Container, tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"

    with pytest.raises(ValueError, match="nao encontrada"):
        container.rebind_to_corpus(missing)


@pytest.mark.unit()
def test_rebind_with_incompatible_dim_raises(container: Container, tmp_path: Path) -> None:
    new_corpus = tmp_path / "corpus_C"
    rag = new_corpus / "rag"
    rag.mkdir(parents=True)
    (rag / "meta.json").write_text(json.dumps({"embedding_dim": 9999}))

    original_store = container.store
    original_corpus = container.config.paths.corpus_dir

    with pytest.raises(ValueError, match="embedding dim"):
        container.rebind_to_corpus(new_corpus)

    assert container.store is original_store
    assert container.config.paths.corpus_dir == original_corpus


@pytest.mark.unit()
def test_rebind_preserves_embedding_dim(container: Container, tmp_path: Path) -> None:
    new_corpus = tmp_path / "corpus_D"
    new_corpus.mkdir()

    container.rebind_to_corpus(new_corpus)

    assert container.config.embedding_dim == _DIM


@pytest.mark.unit()
def test_rebind_swaps_store_ingest_query(container: Container, tmp_path: Path) -> None:
    old_store = container.store
    old_ingest = container.ingest
    old_query = container.query

    new_corpus = tmp_path / "corpus_E"
    new_corpus.mkdir()
    container.rebind_to_corpus(new_corpus)

    assert container.store is not old_store
    assert container.ingest is not old_ingest
    assert container.query is not old_query
    assert container.ingest._embedder is container.embedder
    assert container.query._reranker is container.reranker
