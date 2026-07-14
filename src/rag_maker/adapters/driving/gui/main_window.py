# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QStyle,
    QSystemTrayIcon,
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
        self._tray: QSystemTrayIcon | None = None
        self._build_ui()
        self._setup_tray()
        self._start_status_timer()

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        self._corpus_panel = CorpusPanel(self._container)
        self._corpus_panel.ingest_done.connect(self._refresh_status)
        self._corpus_panel.notification_requested.connect(self._show_notification)
        self._settings_panel = SettingsPanel()
        self._corpus_panel.corpus_change_requested.connect(self._on_corpus_change_requested)
        self._settings_panel.corpus_change_requested.connect(self._on_corpus_change_requested)
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

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self._tray.setIcon(icon)
        self._tray.show()

    def _show_notification(self, title: str, msg: str) -> None:
        if self._tray is not None:
            self._tray.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, 5000)

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

    def _on_corpus_change_requested(self, new_path: str) -> None:
        """Orquestra a troca de corpus: valida busy, delega ao container,
        atualiza ambos os panels.
        """
        if self._corpus_panel.is_busy():
            QMessageBox.information(
                self,
                "Aguarde",
                "Aguarde a operação em andamento terminar antes de trocar de corpus.",
            )
            return

        try:
            changed = self._container.rebind_to_corpus(Path(new_path))
        except (ValueError, PermissionError, OSError) as exc:
            QMessageBox.critical(self, "Erro ao trocar corpus", str(exc))
            # Restaura campos para o valor real da config
            self._corpus_panel.reload_after_rebind()
            self._settings_panel.reload_after_rebind()
            return

        if changed:
            self._corpus_panel.reload_after_rebind()
            self._settings_panel.reload_after_rebind()
            self._refresh_status()
