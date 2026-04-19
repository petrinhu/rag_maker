from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
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
        self._refresh_file_list()

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Seleção de pasta ─────────────────────────────────────────────────
        path_group = QGroupBox("Pasta do corpus")
        path_layout = QHBoxLayout(path_group)
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Selecione a pasta com os seus documentos…")
        if self._container.config.paths.corpus_dir:
            self._path_edit.setText(str(self._container.config.paths.corpus_dir))
        browse_btn = QPushButton("Selecionar…")
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(self._path_edit, stretch=1)
        path_layout.addWidget(browse_btn)
        root.addWidget(path_group)

        # ── Ações + resumo ───────────────────────────────────────────────────
        action_row = QHBoxLayout()
        self._ingest_btn = QPushButton("⬆ Ingerir mudanças")
        self._ingest_btn.setToolTip("Processa apenas arquivos novos ou modificados")
        self._ingest_btn.clicked.connect(self._ingest_incremental)
        self._recreate_btn = QPushButton("↺ Reconstruir tudo")
        self._recreate_btn.setToolTip("Apaga o índice e re-ingere todos os arquivos do zero")
        self._recreate_btn.clicked.connect(self._ingest_full)
        refresh_btn = QPushButton("⟳ Atualizar lista")
        refresh_btn.setToolTip("Recarrega a lista de arquivos indexados")
        refresh_btn.clicked.connect(self._refresh_file_list)
        self._summary_label = QLabel("—")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        action_row.addWidget(self._ingest_btn)
        action_row.addWidget(self._recreate_btn)
        action_row.addWidget(refresh_btn)
        action_row.addStretch()
        action_row.addWidget(self._summary_label)
        root.addLayout(action_row)

        # ── Barra de progresso ───────────────────────────────────────────────
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setMinimum(0)
        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        root.addWidget(self._progress_bar)
        root.addWidget(self._progress_label)

        # ── Tabela de arquivos indexados ─────────────────────────────────────
        files_group = QGroupBox("Arquivos indexados")
        files_layout = QVBoxLayout(files_group)

        self._file_table = QTableWidget(0, 3)
        self._file_table.setHorizontalHeaderLabels(["Arquivo", "Chunks", "Caminho"])
        self._file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._file_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._file_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._file_table.setSortingEnabled(True)
        files_layout.addWidget(self._file_table)

        remove_btn = QPushButton("✕ Remover selecionado do índice")
        remove_btn.setToolTip("Remove o arquivo selecionado do banco vetorial (não apaga o arquivo original)")
        remove_btn.clicked.connect(self._remove_selected)
        files_layout.addWidget(remove_btn)

        root.addWidget(files_group, stretch=1)

        # ── Log ──────────────────────────────────────────────────────────────
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(110)
        self._log.setPlaceholderText("Aqui aparecem os detalhes das operações de ingestão…")
        log_layout.addWidget(self._log)
        root.addWidget(log_group)

    # ── Navegação ─────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta do corpus")
        if folder:
            self._path_edit.setText(folder)

    def _corpus_dir(self) -> Path | None:
        text = self._path_edit.text().strip()
        return Path(text) if text else None

    # ── Lista de arquivos ─────────────────────────────────────────────────────

    def _refresh_file_list(self) -> None:
        try:
            sources = self._container.store.list_sources()
        except Exception:
            sources = {}

        total_chunks = sum(sources.values())
        n_files = len(sources)
        self._summary_label.setText(
            f"{n_files} arquivo{'s' if n_files != 1 else ''} · {total_chunks} chunk{'s' if total_chunks != 1 else ''}"
            if n_files > 0
            else "Nenhum arquivo indexado"
        )

        self._file_table.setSortingEnabled(False)
        self._file_table.setRowCount(0)
        for source_path, chunk_count in sorted(sources.items()):
            p = Path(source_path)
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            self._file_table.setItem(row, 0, QTableWidgetItem(p.name))
            chunk_item = QTableWidgetItem()
            chunk_item.setData(Qt.ItemDataRole.DisplayRole, chunk_count)
            self._file_table.setItem(row, 1, chunk_item)
            self._file_table.setItem(row, 2, QTableWidgetItem(source_path))
        self._file_table.setSortingEnabled(True)

    def _remove_selected(self) -> None:
        row = self._file_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Remover", "Selecione um arquivo na lista primeiro.")
            return
        source_path = self._file_table.item(row, 2)
        if source_path is None:
            return
        path_str = source_path.text()
        answer = QMessageBox.question(
            self,
            "Remover do índice",
            f"Remover '{Path(path_str).name}' do banco vetorial?\n\n"
            "O arquivo original não será apagado.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._container.ingest.remove_file(path_str)
            self._log_append(f"✕ Removido do índice: {Path(path_str).name}")
            self._refresh_file_list()
        except Exception as exc:
            QMessageBox.critical(self, "Erro", str(exc))

    # ── Ingestão ──────────────────────────────────────────────────────────────

    def _ingest_incremental(self) -> None:
        self._start_ingest(full=False)

    def _ingest_full(self) -> None:
        answer = QMessageBox.question(
            self,
            "Reconstruir índice",
            "Apagar todo o índice e re-ingerir do zero?\n\nIsso pode demorar bastante.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_ingest(full=True)

    def _start_ingest(self, full: bool) -> None:
        corpus = self._corpus_dir()
        if corpus is None:
            QMessageBox.warning(self, "Atenção", "Selecione a pasta do corpus primeiro.")
            return
        if not corpus.is_dir():
            QMessageBox.warning(self, "Atenção", f"Pasta não encontrada:\n{corpus}")
            return

        self._set_busy(True)
        self._progress_bar.setValue(0)
        self._log_append(f"{'Reconstruindo' if full else 'Ingerindo'} corpus: {corpus}")

        self._worker = IngestWorker(self._container, corpus, full=full)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, filename: str, current: int, total: int) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_label.setText(f"[{current}/{total}] {filename}")

    def _on_done(self, report: IngestReport) -> None:
        self._set_busy(False)
        summary = (
            f"+{report.added} adicionados  ~{report.updated} atualizados  "
            f"-{report.removed} removidos  "
            f"{report.elapsed_ms / 1000:.1f}s"
        )
        self._log_append(f"✓ Concluído: {summary}")
        if report.errors:
            for path, msg in report.errors:
                self._log_append(f"  ⚠ Erro em {Path(path).name}: {msg}")
        self._refresh_file_list()
        self.ingest_done.emit(report)

    def _on_error(self, msg: str) -> None:
        self._set_busy(False)
        self._log_append(f"✗ Erro fatal: {msg}")
        QMessageBox.critical(self, "Erro na ingestão", msg)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self._ingest_btn.setEnabled(not busy)
        self._recreate_btn.setEnabled(not busy)
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if not busy:
            self._progress_label.setText("")

    def _log_append(self, msg: str) -> None:
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )
