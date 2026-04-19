from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rag_maker.adapters.driving.gui.workers import IngestWorker
from rag_maker.application.ingest_use_case import IngestReport
from rag_maker.composition.container import Container


class CorpusPanel(QWidget):
    ingest_done = Signal(object)  # IngestReport

    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._worker: IngestWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Pasta do corpus
        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Pasta do corpus…")
        if self._container.config.paths.corpus_dir:
            self._path_edit.setText(str(self._container.config.paths.corpus_dir))
        browse_btn = QPushButton("Selecionar…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(QLabel("Corpus:"))
        path_row.addWidget(self._path_edit, stretch=1)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        # Botões de ação
        btn_row = QHBoxLayout()
        self._ingest_btn = QPushButton("Ingerir mudanças")
        self._ingest_btn.clicked.connect(self._ingest_incremental)
        self._recreate_btn = QPushButton("Reconstruir tudo")
        self._recreate_btn.clicked.connect(self._ingest_full)
        btn_row.addWidget(self._ingest_btn)
        btn_row.addWidget(self._recreate_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)
        layout.addStretch()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta do corpus")
        if folder:
            self._path_edit.setText(folder)

    def _corpus_dir(self) -> Path | None:
        text = self._path_edit.text().strip()
        return Path(text) if text else None

    def _ingest_incremental(self) -> None:
        self._start_ingest(full=False)

    def _ingest_full(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reconstruir índice",
            "Reconstruir o índice do zero? Isso pode demorar.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_ingest(full=True)

    def _start_ingest(self, full: bool) -> None:
        corpus = self._corpus_dir()
        if corpus is None:
            QMessageBox.warning(self, "Atenção", "Selecione a pasta do corpus primeiro.")
            return
        self._ingest_btn.setEnabled(False)
        self._recreate_btn.setEnabled(False)
        self._status_label.setText("Ingerindo…")
        self._worker = IngestWorker(self._container, corpus, full=full)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, report: IngestReport) -> None:
        self._ingest_btn.setEnabled(True)
        self._recreate_btn.setEnabled(True)
        self._status_label.setText(
            f"+{report.added} adicionados, ~{report.updated} atualizados, "
            f"-{report.removed} removidos ({report.elapsed_ms:.0f} ms)"
        )
        self.ingest_done.emit(report)

    def _on_error(self, msg: str) -> None:
        self._ingest_btn.setEnabled(True)
        self._recreate_btn.setEnabled(True)
        self._status_label.setText(f"Erro: {msg}")
        QMessageBox.critical(self, "Erro na ingestão", msg)
