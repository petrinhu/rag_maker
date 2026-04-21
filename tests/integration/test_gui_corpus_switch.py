from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from rag_maker.adapters.driving.gui.main_window import MainWindow
from rag_maker.composition.container import build_container
from rag_maker.domain.models import RankedChunk, RetrievedChunk

_DIM = 4


class _FakeScanWorker(QObject):
    """Stub de ScanWorker que nao cria QThread; e nao emite nada automaticamente."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, *_a: object, **_kw: object) -> None:
        super().__init__()

    def start(self) -> None:
        # No-op: evita criar thread real que manteria o processo vivo.
        return

    def isRunning(self) -> bool:
        return False


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
    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_k: int
    ) -> list[RankedChunk]:
        return []


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app  # type: ignore[return-value]


@pytest.mark.integration()
def test_corpus_switch_updates_config_and_panels(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rag_maker.application import config as config_mod
    from rag_maker.composition import container as container_mod

    monkeypatch.setattr(container_mod, "LanceVectorStore", _FakeStore)

    corpus_a = tmp_path / "corpus_a"
    corpus_a.mkdir()
    corpus_b = tmp_path / "corpus_b"
    corpus_b.mkdir()

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[paths]\ncorpus_dir = "{corpus_a}"\n')

    # Aponta o XDG do TOML loader para o arquivo de teste em ambos os modulos
    # (container_mod tem uma referencia local a _xdg_config_file via import).
    monkeypatch.setattr(config_mod, "_xdg_config_file", lambda: cfg_file)
    monkeypatch.setattr(container_mod, "_xdg_config_file", lambda: cfg_file)

    container = build_container(
        config_path=cfg_file,
        embedder=_FakeEmbedder(),
        store=_FakeStore(),
        reranker=_FakeReranker(),
    )
    container.config = container.config.model_copy(update={"embedding_dim": _DIM})

    # Evita probes de rede ao Ollama durante construcao/atualizacao dos paineis
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.ollama_is_running",
        lambda _cfg: False,
    )
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.widgets.settings_panel.detect_ollama_url",
        lambda: "http://127.0.0.1:11434",
    )
    # Substitui ScanWorker (QThread) por stub sem thread — evita que o
    # processo fique vivo aguardando a thread terminar ao final do teste.
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.widgets.corpus_panel.ScanWorker",
        _FakeScanWorker,
    )

    window = MainWindow(container)

    # Dispara a troca pelo CorpusPanel
    window._corpus_panel.corpus_change_requested.emit(str(corpus_b))

    # Verifica que config foi persistida
    with open(cfg_file, "rb") as f:
        data = tomllib.load(f)
    assert data["paths"]["corpus_dir"] == str(corpus_b.resolve())
    assert data["paths"]["db_dir"] == str((corpus_b / "rag").resolve())

    # Verifica que a pasta rag foi criada
    assert (corpus_b / "rag").is_dir()

    # Verifica que o container trocou
    assert container.config.paths.corpus_dir == corpus_b.resolve()

    # Verifica que o CorpusPanel refletiu a mudanca
    assert str(corpus_b) in window._corpus_panel._path_edit.text()

    # Cleanup: fecha a janela e processa eventos pendentes para que o Qt
    # libere recursos antes do proximo teste.
    window.close()
    qapp.processEvents()
