from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
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

from rag_maker.adapters.driving.gui.workers import IngestWorker, ScanWorker
from rag_maker.application.ingest_use_case import ChangeReport, IngestReport
from rag_maker.composition.container import Container, set_config_value

_STATUS_NEW       = ("⬆ Novo",       "#1565C0")  # azul
_STATUS_MODIFIED  = ("↻ Modificado", "#E65100")  # laranja
_STATUS_INDEXED   = ("✓ Indexado",   "#1B5E20")  # verde
_STATUS_REMOVED   = ("✕ Removido",   "#8B0000")  # vermelho


class CorpusPanel(QWidget):
    ingest_done = Signal(object)       # IngestReport
    corpus_dir_changed = Signal(str)   # novo caminho do corpus

    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._ingest_worker: IngestWorker | None = None
        self._scan_worker: ScanWorker | None = None
        self._build_ui()
        # scan inicial se já há corpus configurado
        if self._container.config.paths.corpus_dir:
            self._trigger_scan()

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
        self._path_edit.textChanged.connect(self.corpus_dir_changed)
        browse_btn = QPushButton("Selecionar…")
        browse_btn.clicked.connect(self._browse)
        self._scan_btn = QPushButton("🔍 Escanear")
        self._scan_btn.setToolTip("Analisa quais obras estão indexadas, novas ou modificadas")
        self._scan_btn.clicked.connect(self._trigger_scan)
        path_layout.addWidget(self._path_edit, stretch=1)
        path_layout.addWidget(browse_btn)
        path_layout.addWidget(self._scan_btn)
        root.addWidget(path_group)

        self._recursive_chk = QCheckBox("Incluir subpastas")
        self._recursive_chk.setChecked(True)
        self._recursive_chk.setToolTip(
            "Marcado: varre a pasta do corpus e todas as suas subpastas recursivamente.\n"
            "Desmarcado: considera apenas os arquivos na raiz da pasta selecionada."
        )
        root.addWidget(self._recursive_chk)

        # ── Resumo + ações ───────────────────────────────────────────────────
        action_row = QHBoxLayout()
        self._ingest_btn = QPushButton("⬆ Ingerir mudanças")
        self._ingest_btn.setToolTip("Processa apenas arquivos novos ou modificados")
        self._ingest_btn.clicked.connect(self._ingest_incremental)
        self._recreate_btn = QPushButton("↺ Reconstruir tudo")
        self._recreate_btn.setToolTip("Apaga o índice e re-ingere todos os arquivos do zero")
        self._recreate_btn.clicked.connect(self._ingest_full)
        self._summary_label = QLabel("—")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        action_row.addWidget(self._ingest_btn)
        action_row.addWidget(self._recreate_btn)
        action_row.addStretch()
        action_row.addWidget(self._summary_label)
        root.addLayout(action_row)

        # ── Progresso (visível só durante operações) ─────────────────────────
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        root.addWidget(self._progress_bar)
        root.addWidget(self._progress_label)

        # ── Tabela de obras ──────────────────────────────────────────────────
        files_group = QGroupBox("Obras do corpus")
        files_layout = QVBoxLayout(files_group)

        self._file_table = QTableWidget(0, 4)
        self._file_table.setHorizontalHeaderLabels(["Obra", "Status", "Chunks", "Caminho"])
        hdr = self._file_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._file_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._file_table.setSortingEnabled(True)
        files_layout.addWidget(self._file_table)

        remove_btn = QPushButton("✕ Remover selecionado do índice")
        remove_btn.setToolTip("Remove do banco vetorial (não apaga o arquivo original)")
        remove_btn.clicked.connect(self._remove_selected)
        files_layout.addWidget(remove_btn)

        root.addWidget(files_group, stretch=1)

        # ── Log ──────────────────────────────────────────────────────────────
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(110)
        self._log.setPlaceholderText("Aqui aparecem os detalhes das operações…")
        log_layout.addWidget(self._log)
        root.addWidget(log_group)

    # ── Navegação ─────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        current = self._path_edit.text().strip()
        if current and Path(current).is_dir():
            start_dir = current
        else:
            docs = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.DocumentsLocation
            )
            start_dir = docs or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta do corpus", start_dir)
        if folder:
            self._path_edit.setText(folder)
            set_config_value("paths.corpus_dir", folder)
            self._trigger_scan()

    def _corpus_dir(self) -> Path | None:
        text = self._path_edit.text().strip()
        return Path(text) if text else None

    # ── Scan (análise sem embedding) ──────────────────────────────────────────

    def _trigger_scan(self) -> None:
        corpus = self._corpus_dir()
        if corpus is None or not corpus.is_dir():
            return
        self._scan_btn.setEnabled(False)
        self._summary_label.setText("Analisando…")
        self._scan_worker = ScanWorker(self._container.ingest, corpus, recursive=self._recursive_chk.isChecked())
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_done(self, report: ChangeReport) -> None:
        self._scan_btn.setEnabled(True)
        try:
            sources = self._container.store.list_sources()
        except Exception:
            sources = {}

        n_new      = len(report.new)
        n_modified = len(report.modified)
        n_removed  = len(report.removed)
        n_indexed  = len(report.unchanged)
        total = n_new + n_modified + n_removed + n_indexed

        parts = []
        if n_indexed:
            parts.append(f"<font color='#1B5E20'>{n_indexed} indexado{'s' if n_indexed != 1 else ''}</font>")
        if n_new:
            parts.append(f"<font color='#1565C0'>{n_new} novo{'s' if n_new != 1 else ''}</font>")
        if n_modified:
            parts.append(f"<font color='#E65100'>{n_modified} modificado{'s' if n_modified != 1 else ''}</font>")
        if n_removed:
            parts.append(f"<font color='#8B0000'>{n_removed} removido{'s' if n_removed != 1 else ''}</font>")
        self._summary_label.setText(" · ".join(parts) if parts else f"{total} obras encontradas")

        self._file_table.setSortingEnabled(False)
        self._file_table.setRowCount(0)

        def _add_row(path_str: str, label: str, color: str) -> None:
            p = Path(path_str)
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)

            name_item = QTableWidgetItem(p.name)
            self._file_table.setItem(row, 0, name_item)

            status_item = QTableWidgetItem(label)
            status_item.setForeground(QColor(color))
            self._file_table.setItem(row, 1, status_item)

            chunks = sources.get(path_str, 0)
            chunk_item = QTableWidgetItem()
            chunk_item.setData(Qt.ItemDataRole.DisplayRole, chunks if chunks else None)
            self._file_table.setItem(row, 2, chunk_item)

            self._file_table.setItem(row, 3, QTableWidgetItem(path_str))

        for p in report.unchanged:
            _add_row(str(p), *_STATUS_INDEXED)
        for p in report.new:
            _add_row(str(p), *_STATUS_NEW)
        for p in report.modified:
            _add_row(str(p), *_STATUS_MODIFIED)
        for s in report.removed:
            _add_row(s, *_STATUS_REMOVED)

        self._file_table.setSortingEnabled(True)

        db_dir = self._container.config.paths.resolved_db_dir()
        if db_dir.exists():
            self._log_append(f"Banco de dados rag encontrado em: {db_dir}")
        else:
            self._log_append(f"Banco de dados ainda não existe em: {db_dir}")

        if n_new or n_modified:
            self._log_append(
                f"Scan concluído: {n_new} nova(s), {n_modified} modificada(s), "
                f"{n_indexed} já indexada(s), {n_removed} removida(s)."
            )

    def _on_scan_error(self, msg: str) -> None:
        self._scan_btn.setEnabled(True)
        self._summary_label.setText("Erro no scan")
        self._log_append(f"✗ Erro no scan: {msg}")

    # ── Remoção ───────────────────────────────────────────────────────────────

    def _remove_selected(self) -> None:
        selected = self._file_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Remover", "Selecione uma ou mais obras na lista primeiro.")
            return
        paths = []
        for index in selected:
            path_item = self._file_table.item(index.row(), 3)
            if path_item:
                paths.append(path_item.text())
        if not paths:
            return
        if len(paths) == 1:
            msg = f"Remover '{Path(paths[0]).name}' do banco vetorial?\n\nO arquivo original não será apagado."
        else:
            names = "\n".join(f"  • {Path(p).name}" for p in paths)
            msg = f"Remover {len(paths)} obras do banco vetorial?\n\n{names}\n\nOs arquivos originais não serão apagados."
        answer = QMessageBox.question(
            self, "Remover do índice", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        errors = []
        for path_str in paths:
            try:
                self._container.ingest.remove_file(path_str)
                self._log_append(f"✕ Removido do índice: {Path(path_str).name}")
            except Exception as exc:
                errors.append(f"{Path(path_str).name}: {exc}")
        if errors:
            QMessageBox.critical(self, "Erro ao remover", "\n".join(errors))
        self._trigger_scan()

    # ── Ingestão ──────────────────────────────────────────────────────────────

    def _ingest_incremental(self) -> None:
        self._start_ingest(full=False)

    def _ingest_full(self) -> None:
        answer = QMessageBox.question(
            self, "Reconstruir índice",
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
        self._ingest_worker = IngestWorker(self._container, corpus, full=full, recursive=self._recursive_chk.isChecked())
        self._ingest_worker.progress.connect(self._on_progress)
        self._ingest_worker.finished.connect(self._on_ingest_done)
        self._ingest_worker.error.connect(self._on_ingest_error)
        self._ingest_worker.start()

    def _on_progress(self, filename: str, current: int, total: int) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_label.setText(f"[{current}/{total}] {filename}")

    def _on_ingest_done(self, report: IngestReport) -> None:
        self._set_busy(False)
        self._log_append(
            f"✓ Concluído: +{report.added} adicionados  ~{report.updated} atualizados  "
            f"-{report.removed} removidos  {report.elapsed_ms / 1000:.1f}s"
        )
        if report.errors:
            for path, msg in report.errors:
                self._log_append(f"  ⚠ {Path(path).name}: {msg}")
        self._trigger_scan()
        self.ingest_done.emit(report)

    def _on_ingest_error(self, msg: str) -> None:
        self._set_busy(False)
        self._log_append(f"✗ Erro fatal: {msg}")
        QMessageBox.critical(self, "Erro na ingestão", msg)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self._ingest_btn.setEnabled(not busy)
        self._recreate_btn.setEnabled(not busy)
        self._scan_btn.setEnabled(not busy)
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        if not busy:
            self._progress_label.setText("")

    def _log_append(self, msg: str) -> None:
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())
