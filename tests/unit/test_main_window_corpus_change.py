from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QWidget

from rag_maker.adapters.driving.gui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app  # type: ignore[return-value]


class _StubCorpusPanel(QWidget):
    """Stub que expõe os signals e métodos do CorpusPanel real sem lógica."""

    corpus_change_requested = Signal(str)
    ingest_done = Signal(object)
    notification_requested = Signal(str, str)

    def __init__(self, *_a: object, **_kw: object) -> None:
        super().__init__()
        self.reload_after_rebind = MagicMock()
        self._busy = False

    def is_busy(self) -> bool:
        return self._busy


class _StubSettingsPanel(QWidget):
    corpus_change_requested = Signal(str)

    def __init__(self, *_a: object, **_kw: object) -> None:
        super().__init__()
        self.reload_after_rebind = MagicMock()


class _StubQueryPanel(QWidget):
    def __init__(self, *_a: object, **_kw: object) -> None:
        super().__init__()


@pytest.fixture()
def container_mock(tmp_path: Path) -> MagicMock:
    c = MagicMock()
    c.config.paths.corpus_dir = tmp_path / "corpus"
    (tmp_path / "corpus").mkdir()
    c.config.paths.resolved_db_dir.return_value = tmp_path / "corpus" / "rag"
    c.config.ollama.url = "http://127.0.0.1:11434"
    return c


@pytest.fixture()
def window(
    qapp: QApplication,
    container_mock: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> MainWindow:
    # Substitui as classes dos panels antes de construir MainWindow
    monkeypatch.setattr("rag_maker.adapters.driving.gui.main_window.CorpusPanel", _StubCorpusPanel)
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.SettingsPanel", _StubSettingsPanel
    )
    monkeypatch.setattr("rag_maker.adapters.driving.gui.main_window.QueryPanel", _StubQueryPanel)
    # Evita I/O real no statusbar
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.get_store_stats",
        lambda _cfg: MagicMock(chunk_count=0, initialized=False, embedding_dim=None),
    )
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.ollama_is_running",
        lambda _cfg: False,
    )
    return MainWindow(container_mock)


@pytest.mark.unit()
def test_valid_change_calls_rebind_and_reloads(
    window: MainWindow, container_mock: MagicMock, tmp_path: Path
) -> None:
    new_corpus = tmp_path / "new_corpus"
    new_corpus.mkdir()
    container_mock.rebind_to_corpus.return_value = True

    window._on_corpus_change_requested(str(new_corpus))

    container_mock.rebind_to_corpus.assert_called_once_with(Path(str(new_corpus)))
    window._corpus_panel.reload_after_rebind.assert_called_once()  # type: ignore[attr-defined]
    window._settings_panel.reload_after_rebind.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.unit()
def test_noop_change_skips_reloads(
    window: MainWindow, container_mock: MagicMock, tmp_path: Path
) -> None:
    same_corpus = tmp_path / "same"
    same_corpus.mkdir()
    container_mock.rebind_to_corpus.return_value = False

    window._on_corpus_change_requested(str(same_corpus))

    container_mock.rebind_to_corpus.assert_called_once()
    window._corpus_panel.reload_after_rebind.assert_not_called()  # type: ignore[attr-defined]
    window._settings_panel.reload_after_rebind.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.unit()
def test_busy_blocks_rebind(
    window: MainWindow,
    container_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.QMessageBox.information",
        lambda *a, **k: None,
    )
    window._corpus_panel._busy = True  # type: ignore[attr-defined]
    target = tmp_path / "busy_target"
    target.mkdir()

    window._on_corpus_change_requested(str(target))

    container_mock.rebind_to_corpus.assert_not_called()
    window._corpus_panel.reload_after_rebind.assert_not_called()  # type: ignore[attr-defined]


@pytest.mark.unit()
def test_value_error_shows_critical_and_restores(
    window: MainWindow,
    container_mock: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.QMessageBox.critical",
        lambda *a, **k: None,
    )
    container_mock.rebind_to_corpus.side_effect = ValueError("dim mismatch")

    window._on_corpus_change_requested(str(tmp_path / "x"))

    # reload_after_rebind foi chamado (restaurar campos), mas status nao
    window._corpus_panel.reload_after_rebind.assert_called_once()  # type: ignore[attr-defined]
    window._settings_panel.reload_after_rebind.assert_called_once()  # type: ignore[attr-defined]
