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
    assert report.unchanged == []


@pytest.mark.integration()
def test_scan_unchanged_after_ingest(use_case: IngestUseCase) -> None:
    use_case.ingest_incremental(CORPUS_MINI)
    report = use_case.scan_changes(CORPUS_MINI)
    assert report.new == []
    assert report.modified == []
    assert report.removed == []
    assert len(report.unchanged) == len(list(CORPUS_MINI.rglob("*")))


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


@pytest.mark.integration()
def test_scan_ignores_dir_does_not_match_sibling_by_prefix(
    store: LanceVectorStore, db_path: Path, tmp_path: Path
) -> None:
    """F12.19/AUD-SEC-6 (regressão): filtro de `ignored` usava `str.startswith`,
    que casa por PREFIXO de string — 'corpus/secret' "casa" com
    'corpus/secret2/notas.txt' porque a string 'corpus/secret2/notas.txt'
    começa com 'corpus/secret'. Isso excluía silenciosamente um diretório
    IRMÃO não relacionado ao que o usuário pediu para ignorar.

    Repro do dossiê: ignorar `corpus/secret` NÃO deve afetar `corpus/secret2/`.
    """
    corpus = tmp_path / "corpus"
    secret_dir = corpus / "secret"
    secret2_dir = corpus / "secret2"
    secret_dir.mkdir(parents=True)
    secret2_dir.mkdir(parents=True)
    (secret_dir / "confidencial.txt").write_text("segredo real")
    sibling_file = secret2_dir / "notas.txt"
    sibling_file.write_text("notas públicas, diretório irmão")

    cfg = AppConfig.model_validate(
        {
            "paths": {"db_dir": str(db_path)},
            "ignored": {"paths": [str(secret_dir)]},
        }
    )
    uc = IngestUseCase(embedder=_FakeEmbedder(), store=store, loader_for=loader_for, config=cfg)

    report = uc.scan_changes(corpus)
    new_paths = {str(p) for p in report.new}

    assert str(sibling_file) not in report.removed  # nem sequer deveria existir no manifest
    assert str(sibling_file) in new_paths, "diretório irmão 'secret2' não deve ser ignorado"
    assert str(secret_dir / "confidencial.txt") not in new_paths, (
        "conteúdo de 'secret' deve continuar ignorado"
    )


@pytest.mark.integration()
def test_scan_ignores_files_inside_ignored_dir_including_deep_subdirs(
    store: LanceVectorStore, db_path: Path, tmp_path: Path
) -> None:
    """Caso legítimo: arquivos DENTRO do diretório ignorado continuam
    ignorados, inclusive em subdiretórios profundos (não é regressão do fix
    de F12.19 — is_relative_to() deve manter esse comportamento)."""
    corpus = tmp_path / "corpus"
    secret_dir = corpus / "secret"
    deep_dir = secret_dir / "sub" / "deep"
    deep_dir.mkdir(parents=True)
    (secret_dir / "top.txt").write_text("segredo raiz")
    (deep_dir / "buried.txt").write_text("segredo enterrado")
    (corpus / "public.txt").write_text("público")

    cfg = AppConfig.model_validate(
        {
            "paths": {"db_dir": str(db_path)},
            "ignored": {"paths": [str(secret_dir)]},
        }
    )
    uc = IngestUseCase(embedder=_FakeEmbedder(), store=store, loader_for=loader_for, config=cfg)

    report = uc.scan_changes(corpus)
    new_paths = {str(p) for p in report.new}

    assert str(corpus / "public.txt") in new_paths
    assert str(secret_dir / "top.txt") not in new_paths
    assert str(deep_dir / "buried.txt") not in new_paths


@pytest.mark.integration()
def test_scan_ignores_db_dir_inside_corpus(store: LanceVectorStore, tmp_path: Path) -> None:
    """db_dir localizado dentro do corpus continua ignorado (evita o índice
    LanceDB tentar auto-indexar seus próprios arquivos de dados)."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    db_dir = corpus / ".rag_maker_db"
    db_dir.mkdir()
    (corpus / "doc.txt").write_text("documento normal")

    cfg = AppConfig.model_validate({"paths": {"db_dir": str(db_dir)}})
    uc = IngestUseCase(embedder=_FakeEmbedder(), store=store, loader_for=loader_for, config=cfg)

    report = uc.scan_changes(corpus)
    new_paths = {str(p) for p in report.new}

    assert str(corpus / "doc.txt") in new_paths
    assert not any(str(db_dir) in p for p in new_paths)


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
def test_incremental_removes_orphan_chunks_when_file_shrinks(
    store: LanceVectorStore, cfg: AppConfig, tmp_path: Path
) -> None:
    """AUD-CORRECT-1 (regressão): chunk_id = sha256(path:offset) NUNCA depende
    de conteúdo. upsert() faz merge_insert("chunk_id") — só update/insert,
    nunca delete. No branch `modified` de ingest_incremental, reingerir sem
    delete_by_source antes deixava os chunks antigos (de offsets que não
    existem mais na versão nova) órfãos para sempre no LanceDB, e eles
    continuavam sendo retornados por hybrid_search como se fossem atuais.

    Repro do achado: 'A' * 3000 -> 4 chunks (size=1000/overlap=200 default);
    editar para 'B' * 20 -> 1 chunk só. Sem o fix, count ficava em 4 (3
    chunks 'AAAA...' órfãos); com o fix, count deve virar 1.
    """
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    f = corpus / "shrinking.txt"
    f.write_text("A" * 3000)
    uc = IngestUseCase(embedder=_FakeEmbedder(), store=store, loader_for=loader_for, config=cfg)

    report1 = uc.ingest_incremental(corpus)
    assert report1.added == 1
    assert report1.errors == []
    count_before = store.count()
    assert count_before == 4, "fixture pressupõe 4 chunks para 'A'*3000 com size=1000/overlap=200"

    time.sleep(0.05)  # garante mtime diferente para scan_changes detectar 'modified'
    f.write_text("B" * 20)
    report2 = uc.ingest_incremental(corpus)
    assert report2.updated == 1
    assert report2.errors == []

    # Nenhum chunk órfão: count bate exatamente com o conteúdo NOVO (1 chunk).
    assert store.count() == 1
    sources = store.list_sources()
    assert sources[str(f)] == 1

    # Conjunto de chunk_ids/conteúdo bate com o novo texto — nenhum resquício
    # da versão antiga ('AAAA...') sobrevive no índice.
    query_vec = tuple(_FakeEmbedder().embed("B" * 20))
    results = store.hybrid_search(query_vec, "B" * 20, top_n=10)
    assert len(results) == 1
    assert results[0].chunk.content == "B" * 20
    assert all("A" * 10 not in r.chunk.content for r in results)


@pytest.mark.integration()
def test_embedding_error_recorded_not_raised(store: LanceVectorStore, cfg: AppConfig) -> None:
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
