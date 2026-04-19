from __future__ import annotations

import time
from pathlib import Path

import pytest

from rag_maker.adapters.driven.lancedb.vector_store import LanceVectorStore
from rag_maker.adapters.driven.loaders import loader_for
from rag_maker.application.config import AppConfig
from rag_maker.application.ingest_use_case import IngestUseCase
from rag_maker.domain.models import EmbeddingError

CORPUS_MINI = Path(__file__).parent.parent / "fixtures" / "corpus_mini"


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _FakeEmbedder:
    _DIM = 4

    @property
    def dim(self) -> int:
        return self._DIM

    def embed(self, text: str) -> tuple[float, ...]:
        seed = sum(ord(c) for c in text[:10]) % 100
        return tuple(float(seed + i) / 100.0 for i in range(self._DIM))

    def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self.embed(t) for t in texts]


class _FailingEmbedder:
    @property
    def dim(self) -> int:
        return 4

    def embed(self, text: str) -> tuple[float, ...]:
        raise EmbeddingError("embedding sempre falha")

    def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
        raise EmbeddingError("embedding sempre falha")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "db"
    p.mkdir()
    return p


@pytest.fixture()
def cfg(db_path: Path) -> AppConfig:
    return AppConfig.model_validate({"paths": {"db_dir": str(db_path)}})


@pytest.fixture()
def store(db_path: Path) -> LanceVectorStore:
    return LanceVectorStore(db_path=db_path, embedding_dim=_FakeEmbedder._DIM)


@pytest.fixture()
def use_case(store: LanceVectorStore, cfg: AppConfig) -> IngestUseCase:
    return IngestUseCase(
        embedder=_FakeEmbedder(),
        store=store,
        loader_for=loader_for,
        config=cfg,
    )


# ── scan_changes ──────────────────────────────────────────────────────────────

@pytest.mark.integration()
def test_scan_all_new_when_manifest_empty(use_case: IngestUseCase) -> None:
    report = use_case.scan_changes(CORPUS_MINI)
    assert len(report.new) == len(list(CORPUS_MINI.rglob("*")))
    assert report.modified == []
    assert report.removed == []
    assert report.unchanged == 0


@pytest.mark.integration()
def test_scan_unchanged_after_ingest(use_case: IngestUseCase) -> None:
    use_case.ingest_incremental(CORPUS_MINI)
    report = use_case.scan_changes(CORPUS_MINI)
    assert report.new == []
    assert report.modified == []
    assert report.removed == []
    assert report.unchanged == len(list(CORPUS_MINI.rglob("*")))


@pytest.mark.integration()
def test_scan_detects_removed_file(use_case: IngestUseCase, tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    f = corpus / "a.txt"
    f.write_text("conteúdo de teste")
    use_case.ingest_incremental(corpus)

    f.unlink()
    report = use_case.scan_changes(corpus)
    assert str(f) in report.removed


@pytest.mark.integration()
def test_scan_detects_modified_file(use_case: IngestUseCase, tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    f = corpus / "b.txt"
    f.write_text("versão original")
    use_case.ingest_incremental(corpus)

    # força mtime diferente
    time.sleep(0.05)
    f.write_text("versão modificada")

    report = use_case.scan_changes(corpus)
    assert f in report.modified


# ── ingest_incremental ────────────────────────────────────────────────────────

@pytest.mark.integration()
def test_incremental_adds_chunks_to_store(use_case: IngestUseCase, store: LanceVectorStore) -> None:
    report = use_case.ingest_incremental(CORPUS_MINI)
    assert report.added > 0
    assert report.errors == []
    assert store.count() > 0


@pytest.mark.integration()
def test_incremental_is_idempotent(use_case: IngestUseCase, store: LanceVectorStore) -> None:
    use_case.ingest_incremental(CORPUS_MINI)
    count_after_first = store.count()
    report2 = use_case.ingest_incremental(CORPUS_MINI)
    assert report2.added == 0
    assert store.count() == count_after_first


@pytest.mark.integration()
def test_incremental_removes_deleted_source(
    store: LanceVectorStore, cfg: AppConfig, tmp_path: Path
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    f = corpus / "c.txt"
    f.write_text("texto para remover depois")
    uc = IngestUseCase(embedder=_FakeEmbedder(), store=store, loader_for=loader_for, config=cfg)
    uc.ingest_incremental(corpus)
    assert store.count() > 0

    f.unlink()
    report = uc.ingest_incremental(corpus)
    assert report.removed == 1
    assert store.count() == 0


@pytest.mark.integration()
def test_embedding_error_recorded_not_raised(
    store: LanceVectorStore, cfg: AppConfig
) -> None:
    uc = IngestUseCase(
        embedder=_FailingEmbedder(),
        store=store,
        loader_for=loader_for,
        config=cfg,
    )
    report = uc.ingest_incremental(CORPUS_MINI)
    assert len(report.errors) > 0
    assert store.count() == 0


# ── recreate_all ──────────────────────────────────────────────────────────────

@pytest.mark.integration()
def test_recreate_all_rebuilds_index(use_case: IngestUseCase, store: LanceVectorStore) -> None:
    use_case.ingest_incremental(CORPUS_MINI)
    count_initial = store.count()

    report = use_case.recreate_all(CORPUS_MINI)
    assert report.added > 0
    assert report.errors == []
    assert store.count() == count_initial
