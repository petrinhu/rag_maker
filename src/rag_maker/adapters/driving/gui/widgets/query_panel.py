from __future__ import annotations

import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from rag_maker.adapters.driving.gui.workers import QueryWorker
from rag_maker.composition.container import Container, get_store_stats
from rag_maker.domain.models import QueryResult, RankedChunk


class QueryPanel(QWidget):
    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._worker: QueryWorker | None = None
        self._results: list[RankedChunk] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Linha de busca
        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Consulta em linguagem natural…")
        self._search_edit.returnPressed.connect(self._do_search)
        self._search_btn = QPushButton("Buscar")
        self._search_btn.clicked.connect(self._do_search)
        search_row.addWidget(self._search_edit, stretch=1)
        search_row.addWidget(self._search_btn)
        layout.addLayout(search_row)

        # Top-K slider
        k_row = QHBoxLayout()
        k_row.addWidget(QLabel("Top-K:"))
        self._k_label = QLabel("8")
        self._k_slider = QSlider(Qt.Orientation.Horizontal)
        self._k_slider.setRange(1, 20)
        self._k_slider.setValue(8)
        self._k_slider.valueChanged.connect(lambda v: self._k_label.setText(str(v)))
        k_row.addWidget(self._k_slider)
        k_row.addWidget(self._k_label)
        layout.addLayout(k_row)

        # Tabela de resultados + preview
        splitter = QSplitter(Qt.Orientation.Vertical)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Score", "Arquivo", "Página", "Trecho"])
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.doubleClicked.connect(self._open_file)
        self._table.currentCellChanged.connect(
            lambda row, _col, _pr, _pc: self._update_preview(row)
        )
        splitter.addWidget(self._table)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        splitter.addWidget(self._preview)
        splitter.setSizes([400, 150])
        layout.addWidget(splitter)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    def _do_search(self) -> None:
        query = self._search_edit.text().strip()
        if not query:
            self._search_edit.setPlaceholderText("⚠ Digite uma consulta antes de buscar")
            self._search_edit.setFocus()
            return

        stats = get_store_stats(self._container.config)
        if not stats.initialized or stats.chunk_count == 0:
            QMessageBox.information(
                self,
                "Corpus vazio",
                "Nenhum documento indexado.\n\nVá para a aba Corpus, selecione uma pasta e clique em 'Ingerir mudanças'.",
            )
            return

        top_k = self._k_slider.value()
        self._search_btn.setEnabled(False)
        self._search_edit.setPlaceholderText("Consulta em linguagem natural…")
        self._status_label.setText("Buscando… (primeira query pode demorar enquanto o modelo carrega)")
        self._worker = QueryWorker(self._container.query, query, top_k)
        self._worker.finished.connect(self._on_results)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_results(self, result: QueryResult) -> None:
        self._search_btn.setEnabled(True)
        self._results = list(result.ranked_chunks)
        self._table.setRowCount(0)
        for rc in self._results:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(f"{rc.rerank_score:.4f}"))
            self._table.setItem(row, 1, QTableWidgetItem(rc.chunk.document_path.name))
            self._table.setItem(row, 2, QTableWidgetItem(str(rc.chunk.page or "—")))
            self._table.setItem(row, 3, QTableWidgetItem(rc.chunk.content[:120].replace("\n", " ")))
        if self._results:
            self._status_label.setText(f"{len(self._results)} resultados em {result.latency_ms:.0f} ms")
        else:
            self._status_label.setText(f"Nenhum resultado encontrado ({result.latency_ms:.0f} ms)")

    def _on_error(self, msg: str) -> None:
        self._search_btn.setEnabled(True)
        self._status_label.setText(f"Erro: {msg}")
        QMessageBox.critical(self, "Erro na busca", msg)

    def _update_preview(self, row: int) -> None:
        if 0 <= row < len(self._results):
            rc = self._results[row]
            self._preview.setPlainText(rc.chunk.content)

    def _open_file(self) -> None:
        row = self._table.currentRow()
        if 0 <= row < len(self._results):
            path = self._results[row].chunk.document_path
            if path.exists():
                if sys.platform == "linux":
                    subprocess.Popen(["xdg-open", str(path)])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(path)])
                else:
                    subprocess.Popen(["start", str(path)], shell=True)
