from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from rag_maker.adapters.driven.lancedb.vector_store import LanceVectorStore
from rag_maker.adapters.driving.cli import main as cli_main
from rag_maker.application.config import AppConfig
from rag_maker.application.ingest_use_case import IngestReport
from rag_maker.application.query_use_case import QueryUseCase
from rag_maker.composition.container import StoreStats
from rag_maker.domain.models import (
    Chunk,
    EmbeddingError,
    IndexedChunk,
    ModelNotFoundError,
    OllamaUnavailableError,
    QueryResult,
    RankedChunk,
)

# AUD-TEST-6 / F12.22: a maior parte dos testes roda in-process via
# `typer.testing.CliRunner` — subprocess.run() sem COVERAGE_PROCESS_START
# deixa cli/main.py com 0% de coverage mesmo exercitado. Subprocess fica
# reservado para o smoke de que o entrypoint real (`python -m ...`) funciona.
_RAG = [sys.executable, "-m", "rag_maker.adapters.driving.cli.main"]
_ENV_BASE = {**os.environ, "FORCE_COLOR": "0", "NO_COLOR": "1"}

runner = CliRunner()


def _run(*args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**_ENV_BASE, **(extra_env or {})}
    return subprocess.run([*_RAG, *args], capture_output=True, text=True, env=env)


def _isolated_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    # Isola XDG_CONFIG_HOME E o DB_DIR default: sem isto, comandos que fazem
    # db_dir.mkdir() (ex.: doctor) poluem ~/.local/share/rag_maker/db do HOME real.
    return {
        "XDG_CONFIG_HOME": str(tmp_path / "xdg_config"),
        "RAG_MAKER_PATHS__DB_DIR": str(tmp_path / "db"),
        **extra,
    }


# ── smoke via subprocess (isolamento real de processo) ─────────────────────────


@pytest.mark.e2e()
def test_version_flag() -> None:
    r = _run("--version")
    assert r.returncode == 0
    assert "." in r.stdout  # semver


@pytest.mark.e2e()
def test_help_flag() -> None:
    r = _run("--help")
    assert r.returncode == 0
    assert "rag" in r.stdout.lower() or "rag" in r.stderr.lower()


# ── status ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_status_json(tmp_path: Path) -> None:
    db = str(tmp_path / "db")
    r = runner.invoke(
        cli_main.app,
        ["status", "--json"],
        env=_isolated_env(tmp_path, RAG_MAKER_PATHS__DB_DIR=db),
    )
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert "version" in data
    assert "store" in data
    assert "ollama" in data
    assert data["store"]["corrupted"] is False


@pytest.mark.e2e()
def test_status_table_output(tmp_path: Path) -> None:
    db = str(tmp_path / "db")
    r = runner.invoke(
        cli_main.app,
        ["status"],
        env=_isolated_env(tmp_path, RAG_MAKER_PATHS__DB_DIR=db),
    )
    assert r.exit_code == 0, r.output
    assert "Versão" in r.stdout
    assert "DB dir" in r.stdout


# ── config ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_config_path(tmp_path: Path) -> None:
    r = runner.invoke(cli_main.app, ["config", "path"], env=_isolated_env(tmp_path))
    assert r.exit_code == 0, r.output
    assert "rag_maker" in r.output


@pytest.mark.e2e()
def test_config_set_and_get(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    r_set = runner.invoke(cli_main.app, ["config", "set", "ollama.timeout_seconds", "120"], env=env)
    assert r_set.exit_code == 0, r_set.output

    r_get = runner.invoke(cli_main.app, ["config", "get", "ollama.timeout_seconds"], env=env)
    assert r_get.exit_code == 0, r_get.output
    assert "120" in r_get.output


@pytest.mark.e2e()
def test_config_set_failure_exits_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(key: str, value: str) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(cli_main, "set_config_value", _raise)

    r = runner.invoke(
        cli_main.app,
        ["config", "set", "ollama.url", "http://x"],
        env=_isolated_env(tmp_path),
    )
    assert r.exit_code == cli_main.EXIT_CONFIG, r.output


@pytest.mark.e2e()
def test_config_get_no_key_without_file_prints_message(tmp_path: Path) -> None:
    r = runner.invoke(cli_main.app, ["config", "get"], env=_isolated_env(tmp_path))
    assert r.exit_code == 0, r.output
    assert "config.toml" in r.output.lower()


@pytest.mark.e2e()
def test_config_get_no_key_with_file_prints_json(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    r_set = runner.invoke(cli_main.app, ["config", "set", "ollama.timeout_seconds", "99"], env=env)
    assert r_set.exit_code == 0, r_set.output

    r_get = runner.invoke(cli_main.app, ["config", "get"], env=env)
    assert r_get.exit_code == 0, r_get.output
    data = json.loads(r_get.output)
    assert data["ollama"]["timeout_seconds"] == 99


@pytest.mark.e2e()
def test_config_get_unknown_key_exits_user(tmp_path: Path) -> None:
    r = runner.invoke(
        cli_main.app, ["config", "get", "naochave.inexistente"], env=_isolated_env(tmp_path)
    )
    assert r.exit_code == cli_main.EXIT_USER, r.output


@pytest.mark.e2e()
def test_invalid_config_toml_exits_config(tmp_path: Path) -> None:
    cfg_home = tmp_path / "xdg_config"
    cfg_dir = cfg_home / "rag_maker"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.toml").write_text("isto nao e toml valido [[[")

    r = runner.invoke(cli_main.app, ["status"], env={"XDG_CONFIG_HOME": str(cfg_home)})
    assert r.exit_code == cli_main.EXIT_CONFIG, r.output


# ── ignore ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_ignore_add_list_rm(tmp_path: Path) -> None:
    env = _isolated_env(tmp_path)
    target = str(tmp_path / "pasta_ignorada")

    r_add = runner.invoke(cli_main.app, ["ignore", "add", target], env=env)
    assert r_add.exit_code == 0, r_add.output

    r_list = runner.invoke(cli_main.app, ["ignore", "list"], env=env)
    assert r_list.exit_code == 0, r_list.output
    assert target in r_list.output

    r_rm = runner.invoke(cli_main.app, ["ignore", "rm", target], env=env)
    assert r_rm.exit_code == 0, r_rm.output


@pytest.mark.e2e()
def test_ignore_list_empty_prints_dim_message(tmp_path: Path) -> None:
    r = runner.invoke(cli_main.app, ["ignore", "list"], env=_isolated_env(tmp_path))
    assert r.exit_code == 0, r.output
    assert "Nenhum caminho ignorado" in r.stdout


@pytest.mark.e2e()
def test_ignore_rm_missing_path_exits_user(tmp_path: Path) -> None:
    r = runner.invoke(
        cli_main.app,
        ["ignore", "rm", str(tmp_path / "nunca-foi-adicionado")],
        env=_isolated_env(tmp_path),
    )
    assert r.exit_code == cli_main.EXIT_USER, r.output


# ── query: exit codes ────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_query_empty_store_returns_exit_6(tmp_path: Path) -> None:
    db = str(tmp_path / "db")
    r = runner.invoke(
        cli_main.app,
        ["query", "teste", "--json"],
        env=_isolated_env(tmp_path, RAG_MAKER_PATHS__DB_DIR=db),
    )
    assert r.exit_code == cli_main.EXIT_CORPUS, r.output


@pytest.mark.e2e()
def test_unknown_command_exits_nonzero() -> None:
    r = runner.invoke(cli_main.app, ["naoexiste"])
    assert r.exit_code != 0


# ── F12.15 / AUD-INPUT-4: --top-k <= 0 ──────────────────────────────────────


@pytest.mark.e2e()
def test_query_top_k_negative_rejected_at_cli_boundary(tmp_path: Path) -> None:
    r = runner.invoke(
        cli_main.app,
        ["query", "teste", "--top-k", "-2"],
        env=_isolated_env(tmp_path),
    )
    assert r.exit_code == 2, r.output
    assert "top-k" in r.output.lower()


@pytest.mark.e2e()
def test_query_top_k_zero_rejected_at_cli_boundary(tmp_path: Path) -> None:
    r = runner.invoke(
        cli_main.app,
        ["query", "teste", "--top-k", "0"],
        env=_isolated_env(tmp_path),
    )
    assert r.exit_code == 2, r.output


@pytest.mark.unit()
def test_query_use_case_rejects_non_positive_top_k() -> None:
    """Guard defensivo em QueryUseCase.answer: a borda CLI (Click min=1) já
    bloqueia, mas a use case é chamável por qualquer driving adapter futuro
    sem essa validação — sem o guard, `ranked[:top_k]` negativo usaria a
    semântica de slice do Python e devolveria um subconjunto errado em
    silêncio (AUD-INPUT-4)."""

    class _FakeEmbedder:
        def embed(self, text: str) -> tuple[float, ...]:
            return (0.1, 0.2, 0.3, 0.4)

        def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
            return [self.embed(t) for t in texts]

    class _FakeStore:
        def hybrid_search(self, vector: tuple[float, ...], text: str, top_n: int) -> list[object]:
            raise AssertionError("não deveria alcançar a store com top_k inválido")

    class _FakeReranker:
        def rerank(self, query: str, chunks: list[object], top_k: int) -> list[object]:
            raise AssertionError("não deveria alcançar o reranker com top_k inválido")

    uc = QueryUseCase(
        embedder=_FakeEmbedder(),  # type: ignore[arg-type]
        store=_FakeStore(),  # type: ignore[arg-type]
        reranker=_FakeReranker(),  # type: ignore[arg-type]
        config=AppConfig(),
    )
    with pytest.raises(ValueError, match="top_k"):
        uc.answer("teste", top_k=-2)
    with pytest.raises(ValueError, match="top_k"):
        uc.answer("teste", top_k=0)


# ── F12.8 / AUD-CIDOCS-2: banco corrompido → EXIT_DB=5 ──────────────────────


def _make_corrupted_db(tmp_path: Path) -> Path:
    """Cria um LanceVectorStore real com 1 chunk e corrompe o data file.

    Reproduz o cenário do dossiê: `count_rows()` continua reportando a
    contagem do manifest (não é "vazio"), mas ler os dados levanta
    RuntimeError — isso é o sinal de corrupção real, distinto de "nunca
    ingerido".
    """
    db_dir = tmp_path / "db"
    store = LanceVectorStore(db_path=db_dir, embedding_dim=4)
    chunk = Chunk(
        chunk_id="c1",
        document_path=tmp_path / "doc.txt",
        content="conteudo de teste",
        char_offset=0,
        mtime=0.0,
        page=None,
        section=None,
    )
    store.upsert([IndexedChunk(chunk=chunk, vector=(0.1, 0.2, 0.3, 0.4))])
    (db_dir / "meta.json").write_text(json.dumps({"embedding_dim": 4}))

    data_files = list((db_dir / "chunks.lance" / "data").glob("*.lance"))
    assert data_files, "setup do teste: nenhum data file criado pelo upsert"
    for f in data_files:
        f.write_bytes(b"GARBAGE-NOT-LANCE-DATA" * 200)
    return db_dir


@pytest.mark.e2e()
def test_query_corrupted_store_exits_5(tmp_path: Path) -> None:
    db_dir = _make_corrupted_db(tmp_path)
    r = runner.invoke(
        cli_main.app,
        ["query", "teste", "--json"],
        env=_isolated_env(tmp_path, RAG_MAKER_PATHS__DB_DIR=str(db_dir)),
    )
    assert r.exit_code == cli_main.EXIT_DB, r.output
    assert r.exit_code == 5


@pytest.mark.e2e()
def test_status_corrupted_store_exits_5(tmp_path: Path) -> None:
    db_dir = _make_corrupted_db(tmp_path)
    r = runner.invoke(
        cli_main.app,
        ["status", "--json"],
        env=_isolated_env(tmp_path, RAG_MAKER_PATHS__DB_DIR=str(db_dir)),
    )
    assert r.exit_code == cli_main.EXIT_DB, r.output


@pytest.mark.e2e()
def test_status_corrupted_store_reports_corrupted_true_before_abort(tmp_path: Path) -> None:
    db_dir = _make_corrupted_db(tmp_path)
    r = runner.invoke(
        cli_main.app,
        ["status", "--json"],
        env=_isolated_env(tmp_path, RAG_MAKER_PATHS__DB_DIR=str(db_dir)),
    )
    data = json.loads(r.stdout)
    assert data["store"]["corrupted"] is True


# ── ingest: fluxo via fakes injetados no container (sem Ollama real) ───────


@pytest.mark.e2e()
def test_ingest_no_corpus_configured_exits_config(tmp_path: Path) -> None:
    r = runner.invoke(cli_main.app, ["ingest"], env=_isolated_env(tmp_path))
    assert r.exit_code == cli_main.EXIT_CONFIG, r.output


@pytest.mark.e2e()
def test_ingest_missing_corpus_dir_exits_user(tmp_path: Path) -> None:
    r = runner.invoke(
        cli_main.app,
        ["ingest", "--corpus", str(tmp_path / "nao-existe")],
        env=_isolated_env(tmp_path),
    )
    assert r.exit_code == cli_main.EXIT_USER, r.output


@pytest.mark.e2e()
def test_ingest_full_without_yes_prompts_and_aborts_on_no(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    monkeypatch.setattr(cli_main, "ensure_ollama_ready", lambda config: None)

    r = runner.invoke(
        cli_main.app,
        ["ingest", "--corpus", str(corpus_dir), "--full"],
        input="n\n",
        env=_isolated_env(tmp_path),
    )
    assert r.exit_code != 0


@pytest.mark.e2e()
def test_ingest_full_yes_calls_recreate_all_and_reports_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    class _FakeIngest:
        def recreate_all(self, corpus_dir: Path) -> IngestReport:
            return IngestReport(added=3, updated=0, removed=0, errors=[], elapsed_ms=12.5)

        def ingest_incremental(self, corpus_dir: Path) -> IngestReport:
            raise AssertionError("--full deveria chamar recreate_all, não ingest_incremental")

    fake_container = SimpleNamespace(ingest=_FakeIngest())
    monkeypatch.setattr(cli_main, "ensure_ollama_ready", lambda config: None)
    monkeypatch.setattr(cli_main, "build_container", lambda: fake_container)

    r = runner.invoke(
        cli_main.app,
        ["ingest", "--corpus", str(corpus_dir), "--full", "--yes", "--json"],
        env=_isolated_env(tmp_path),
    )
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["added"] == 3
    assert data["errors"] == []


@pytest.mark.e2e()
def test_ingest_incremental_calls_ingest_incremental_and_aggregates_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    class _FakeIngest:
        def ingest_incremental(self, corpus_dir: Path) -> IngestReport:
            return IngestReport(
                added=1,
                updated=2,
                removed=0,
                errors=[("bad.pdf", "arquivo corrompido")],
                elapsed_ms=5.0,
            )

        def recreate_all(self, corpus_dir: Path) -> IngestReport:
            raise AssertionError("sem --full não deveria chamar recreate_all")

    fake_container = SimpleNamespace(ingest=_FakeIngest())
    monkeypatch.setattr(cli_main, "ensure_ollama_ready", lambda config: None)
    monkeypatch.setattr(cli_main, "build_container", lambda: fake_container)

    r = runner.invoke(
        cli_main.app,
        ["ingest", "--corpus", str(corpus_dir), "--json"],
        env=_isolated_env(tmp_path),
    )
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["added"] == 1
    assert data["updated"] == 2
    assert data["errors"] == [{"path": "bad.pdf", "error": "arquivo corrompido"}]


@pytest.mark.e2e()
def test_ingest_incremental_human_readable_output_lists_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem --json: erros vão para stderr, resumo com contadores para stdout."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    class _FakeIngest:
        def ingest_incremental(self, corpus_dir: Path) -> IngestReport:
            return IngestReport(
                added=1,
                updated=0,
                removed=0,
                errors=[("bad.pdf", "arquivo corrompido")],
                elapsed_ms=5.0,
            )

    fake_container = SimpleNamespace(ingest=_FakeIngest())
    monkeypatch.setattr(cli_main, "ensure_ollama_ready", lambda config: None)
    monkeypatch.setattr(cli_main, "build_container", lambda: fake_container)

    r = runner.invoke(
        cli_main.app,
        ["ingest", "--corpus", str(corpus_dir)],
        env=_isolated_env(tmp_path),
    )
    assert r.exit_code == 0, r.output
    assert "bad.pdf" in r.stderr
    assert "1 erros" in r.stdout
    assert "adicionados" in r.stdout


@pytest.mark.e2e()
def test_ingest_ollama_unavailable_exits_ollama(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    def _raise(config: object) -> None:
        raise OllamaUnavailableError("daemon offline")

    monkeypatch.setattr(cli_main, "ensure_ollama_ready", _raise)

    r = runner.invoke(
        cli_main.app, ["ingest", "--corpus", str(corpus_dir)], env=_isolated_env(tmp_path)
    )
    assert r.exit_code == cli_main.EXIT_OLLAMA, r.output


@pytest.mark.e2e()
def test_ingest_model_not_found_exits_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    def _raise(config: object) -> None:
        raise ModelNotFoundError("bge-m3:latest")

    monkeypatch.setattr(cli_main, "ensure_ollama_ready", _raise)

    r = runner.invoke(
        cli_main.app, ["ingest", "--corpus", str(corpus_dir)], env=_isolated_env(tmp_path)
    )
    assert r.exit_code == cli_main.EXIT_MODEL, r.output


@pytest.mark.e2e()
def test_ingest_build_container_failure_exits_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    def _raise_build() -> object:
        raise RuntimeError("falha ao conectar no LanceDB")

    monkeypatch.setattr(cli_main, "ensure_ollama_ready", lambda config: None)
    monkeypatch.setattr(cli_main, "build_container", _raise_build)

    r = runner.invoke(
        cli_main.app, ["ingest", "--corpus", str(corpus_dir)], env=_isolated_env(tmp_path)
    )
    assert r.exit_code == cli_main.EXIT_INTERNAL, r.output


@pytest.mark.e2e()
def test_ingest_use_case_failure_exits_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    class _FakeIngest:
        def ingest_incremental(self, corpus_dir: Path) -> IngestReport:
            raise RuntimeError("falha ao ler corpus")

    fake_container = SimpleNamespace(ingest=_FakeIngest())
    monkeypatch.setattr(cli_main, "ensure_ollama_ready", lambda config: None)
    monkeypatch.setattr(cli_main, "build_container", lambda: fake_container)

    r = runner.invoke(
        cli_main.app, ["ingest", "--corpus", str(corpus_dir)], env=_isolated_env(tmp_path)
    )
    assert r.exit_code == cli_main.EXIT_INTERNAL, r.output


# ── query: fluxo de sucesso e erros via fakes (F12.22) ──────────────────────


def _stub_query_flow(monkeypatch: pytest.MonkeyPatch, *, chunk_count: int = 1) -> None:
    monkeypatch.setattr(
        cli_main,
        "get_store_stats",
        lambda config: StoreStats(initialized=True, chunk_count=chunk_count, embedding_dim=4),
    )
    monkeypatch.setattr(cli_main, "ensure_ollama_ready", lambda config: None)


@pytest.mark.e2e()
def test_query_success_json_reports_chunks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chunk = Chunk(
        chunk_id="c1",
        document_path=tmp_path / "doc.txt",
        content="conteudo de teste",
        char_offset=0,
        mtime=0.0,
        page=3,
        section="intro",
    )
    result = QueryResult(
        query="teste",
        ranked_chunks=(RankedChunk(chunk=chunk, rerank_score=0.9, rrf_score=0.5),),
        latency_ms=12.3,
    )

    class _FakeQuery:
        def answer(self, text: str, top_k: int | None, alpha: float | None) -> QueryResult:
            return result

    _stub_query_flow(monkeypatch)
    monkeypatch.setattr(cli_main, "build_container", lambda: SimpleNamespace(query=_FakeQuery()))

    r = runner.invoke(cli_main.app, ["query", "teste", "--json"], env=_isolated_env(tmp_path))
    assert r.exit_code == 0, r.output
    data = json.loads(r.stdout)
    assert data["chunks"][0]["chunk_id"] == "c1"
    assert data["chunks"][0]["page"] == 3


@pytest.mark.e2e()
def test_query_success_table_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    chunk = Chunk(
        chunk_id="c1",
        document_path=tmp_path / "doc.txt",
        content="conteudo de teste para a tabela",
        char_offset=0,
        mtime=0.0,
        page=None,
        section=None,
    )
    result = QueryResult(
        query="teste",
        ranked_chunks=(RankedChunk(chunk=chunk, rerank_score=0.9, rrf_score=0.5),),
        latency_ms=12.3,
    )

    class _FakeQuery:
        def answer(self, text: str, top_k: int | None, alpha: float | None) -> QueryResult:
            return result

    _stub_query_flow(monkeypatch)
    monkeypatch.setattr(cli_main, "build_container", lambda: SimpleNamespace(query=_FakeQuery()))

    r = runner.invoke(cli_main.app, ["query", "teste"], env=_isolated_env(tmp_path))
    assert r.exit_code == 0, r.output
    assert "conteudo de teste" in r.stdout
    assert "Latência" in r.stdout


@pytest.mark.e2e()
def test_query_success_no_results_prints_dim_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = QueryResult(query="teste", ranked_chunks=(), latency_ms=1.0)

    class _FakeQuery:
        def answer(self, text: str, top_k: int | None, alpha: float | None) -> QueryResult:
            return result

    _stub_query_flow(monkeypatch)
    monkeypatch.setattr(cli_main, "build_container", lambda: SimpleNamespace(query=_FakeQuery()))

    r = runner.invoke(cli_main.app, ["query", "teste"], env=_isolated_env(tmp_path))
    assert r.exit_code == 0, r.output
    assert "Nenhum resultado encontrado" in r.stdout


@pytest.mark.e2e()
def test_query_ollama_unavailable_exits_ollama(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli_main,
        "get_store_stats",
        lambda config: StoreStats(initialized=True, chunk_count=1, embedding_dim=4),
    )

    def _raise(config: object) -> None:
        raise OllamaUnavailableError("daemon offline")

    monkeypatch.setattr(cli_main, "ensure_ollama_ready", _raise)

    r = runner.invoke(cli_main.app, ["query", "teste"], env=_isolated_env(tmp_path))
    assert r.exit_code == cli_main.EXIT_OLLAMA, r.output


@pytest.mark.e2e()
def test_query_model_not_found_exits_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_main,
        "get_store_stats",
        lambda config: StoreStats(initialized=True, chunk_count=1, embedding_dim=4),
    )

    def _raise(config: object) -> None:
        raise ModelNotFoundError("bge-m3:latest")

    monkeypatch.setattr(cli_main, "ensure_ollama_ready", _raise)

    r = runner.invoke(cli_main.app, ["query", "teste"], env=_isolated_env(tmp_path))
    assert r.exit_code == cli_main.EXIT_MODEL, r.output


@pytest.mark.e2e()
def test_query_embedding_error_exits_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeQuery:
        def answer(self, text: str, top_k: int | None, alpha: float | None) -> QueryResult:
            raise EmbeddingError("dimensão incompatível")

    _stub_query_flow(monkeypatch)
    monkeypatch.setattr(cli_main, "build_container", lambda: SimpleNamespace(query=_FakeQuery()))

    r = runner.invoke(cli_main.app, ["query", "teste"], env=_isolated_env(tmp_path))
    assert r.exit_code == cli_main.EXIT_INTERNAL, r.output


@pytest.mark.e2e()
def test_query_generic_error_exits_internal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeQuery:
        def answer(self, text: str, top_k: int | None, alpha: float | None) -> QueryResult:
            raise RuntimeError("falha inesperada")

    _stub_query_flow(monkeypatch)
    monkeypatch.setattr(cli_main, "build_container", lambda: SimpleNamespace(query=_FakeQuery()))

    r = runner.invoke(cli_main.app, ["query", "teste"], env=_isolated_env(tmp_path))
    assert r.exit_code == cli_main.EXIT_INTERNAL, r.output


# ── doctor ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_doctor_ollama_offline_exits_user(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_main, "ollama_is_running", lambda config: False)

    r = runner.invoke(cli_main.app, ["doctor"], env=_isolated_env(tmp_path))
    assert r.exit_code == cli_main.EXIT_USER, r.output
    assert "Ollama daemon" in r.output


@pytest.mark.e2e()
def test_doctor_checks_model_only_when_ollama_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli_main, "ollama_is_running", lambda config: True)
    monkeypatch.setattr(
        cli_main,
        "list_ollama_models",
        lambda config: (calls.append("list_ollama_models"), ["bge-m3:latest"])[1],
    )

    runner.invoke(cli_main.app, ["doctor"], env=_isolated_env(tmp_path))
    assert calls == ["list_ollama_models"]
