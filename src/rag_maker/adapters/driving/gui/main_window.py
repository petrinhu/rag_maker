from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
)

from rag_maker.adapters.driving.gui.widgets.corpus_panel import CorpusPanel
from rag_maker.adapters.driving.gui.widgets.query_panel import QueryPanel
from rag_maker.adapters.driving.gui.widgets.settings_panel import SettingsPanel
from rag_maker.composition.container import (
    Container,
    StoreStats,
    get_store_stats,
    ollama_is_running,
)


class MainWindow(QMainWindow):
    def __init__(self, container: Container) -> None:
        super().__init__()
        self._container = container
        self.setWindowTitle("rag-maker")
        self.resize(900, 650)
        self._build_ui()
        self._start_status_timer()

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        self._corpus_panel = CorpusPanel(self._container)
        self._corpus_panel.ingest_done.connect(self._refresh_status)
        self._settings_panel = SettingsPanel()
        self._corpus_panel.corpus_dir_changed.connect(self._settings_panel.set_corpus_dir)
        tabs.addTab(self._corpus_panel, "Corpus")
        tabs.addTab(QueryPanel(self._container), "Consulta")
        tabs.addTab(self._settings_panel, "Configurações")
        self.setCentralWidget(tabs)

        bar = QStatusBar()
        self._ollama_label = QLabel("Ollama: …")
        self._chunks_label = QLabel("Chunks: …")
        bar.addPermanentWidget(self._ollama_label)
        bar.addPermanentWidget(QLabel(" | "))
        bar.addPermanentWidget(self._chunks_label)
        self.setStatusBar(bar)

    def _start_status_timer(self) -> None:
        self._refresh_status()
        timer = QTimer(self)
        timer.setInterval(10_000)
        timer.timeout.connect(self._refresh_status)
        timer.start()

    def _refresh_status(self, *_: object) -> None:
        running = ollama_is_running(self._container.config)
        self._ollama_label.setText(
            "Ollama: <font color='#1B5E20'>online</font>"
            if running
            else "Ollama: <font color='#8B0000'>offline</font>"
        )
        stats: StoreStats = get_store_stats(self._container.config)
        count = stats.chunk_count if stats.chunk_count is not None else "—"
        self._chunks_label.setText(f"Chunks: {count}")
