from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
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

_STATUS_NEW      = "⬆ Novo"
_STATUS_MODIFIED = "↻ Modificado"
_STATUS_INDEXED  = "✓ Indexado"
_STATUS_REMOVED  = "✕ Removido"

_NOTIFY_THRESHOLD_S = 10.0  # notificação de sistema só para operações longas


def _is_dark() -> bool:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def _status_styles() -> dict[str, tuple[str, QColor]]:
    """Retorna (fg_hex, bg_qcolor) por status, adaptado ao esquema de cores atual."""
    if _is_dark():
        return {
            _STATUS_NEW:      ("#82B1FF", QColor(20,  45,  90)),
            _STATUS_MODIFIED: ("#FFAB40", QColor(70,  40,  10)),
            _STATUS_INDEXED:  ("#69F0AE", QColor(15,  50,  25)),
            _STATUS_REMOVED:  ("#FF5252", QColor(75,  20,  20)),
        }
    return {
        _STATUS_NEW:      ("#1565C0", QColor(227, 242, 253)),
        _STATUS_MODIFIED: ("#E65100", QColor(255, 243, 224)),
        _STATUS_INDEXED:  ("#1B5E20", QColor(232, 245, 233)),
        _STATUS_REMOVED:  ("#8B0000", QColor(255, 235, 238)),
    }


class _DroppableLineEdit(QLineEdit):
    folder_dropped = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).is_dir():
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            folder = url.toLocalFile()
            if Path(folder).is_dir():
                self.setText(folder)
                self.folder_dropped.emit(folder)
                event.acceptProposedAction()
                return
        event.ignore()


class CorpusPanel(QWidget):
    ingest_done            = Signal(object)   # IngestReport
    corpus_dir_changed     = Signal(str)      # novo caminho do corpus
    notification_requested = Signal(str, str) # title, message

    def __init__(self, container: Container, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._ingest_worker: IngestWorker | None = None
        self._scan_worker: ScanWorker | None = None
        self._active_status_filter: str | None = None
        self._ingest_start_time: float = 0.0
        self._build_ui()
        if self._container.config.paths.corpus_dir:
            self._trigger_scan()

    # ── Construção da UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Seleção de pasta ─────────────────────────────────────────────────
        path_group = QGroupBox("Pasta do corpus")
        path_layout = QHBoxLayout(path_group)
        self._path_edit = _DroppableLineEdit()
        self._path_edit.setPlaceholderText("Selecione ou arraste a pasta com os seus documentos…")
        if self._container.config.paths.corpus_dir:
            self._path_edit.setText(str(self._container.config.paths.corpus_dir))
        self._path_edit.textChanged.connect(self.corpus_dir_changed)
        self._path_edit.folder_dropped.connect(self._on_folder_dropped)
        browse_btn = QPushButton("Selecionar…")
        browse_btn.clicked.connect(self._browse)
        self._scan_btn = QPushButton("Escanear")
        self._scan_btn.setToolTip("Analisa quais obras estão indexadas, novas ou modificadas")
        self._scan_btn.clicked.connect(self._trigger_scan)
        path_layout.addWidget(self._path_edit, stretch=1)
        path_layout.addWidget(browse_btn)
        path_layout.addWidget(self._scan_btn)
        root.addWidget(path_group)

        self._recursive_chk = QCheckBox("Incluir subpastas")
        self._recursive_chk.setChecked(self._container.config.gui.recursive_scan)
        self._recursive_chk.setToolTip(
            "Marcado: varre a pasta do corpus e todas as suas subpastas recursivamente.\n"
            "Desmarcado: considera apenas os arquivos na raiz da pasta selecionada."
        )
        self._recursive_chk.stateChanged.connect(self._on_recursive_changed)
        root.addWidget(self._recursive_chk)

        # ── Resumo + ações ───────────────────────────────────────────────────
        action_row = QHBoxLayout()
        self._ingest_btn = QPushButton("Ingerir mudancas")
        self._ingest_btn.setToolTip("Processa apenas arquivos novos ou modificados")
        self._ingest_btn.clicked.connect(self._ingest_incremental)
        self._recreate_btn = QPushButton("Reconstruir tudo")
        self._recreate_btn.setToolTip("Apaga o indice e re-ingere todos os arquivos do zero")
        self._recreate_btn.clicked.connect(self._ingest_full)
        self._summary_label = QLabel("—")
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        action_row.addWidget(self._ingest_btn)
        action_row.addWidget(self._recreate_btn)
        action_row.addStretch()
        action_row.addWidget(self._summary_label)
        root.addLayout(action_row)

        # ── Progresso ────────────────────────────────────────────────────────
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setToolTip("Progresso geral: arquivos processados")
        self._pause_btn = QPushButton("Pausar")
        self._pause_btn.setFixedWidth(90)
        self._pause_btn.setVisible(False)
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._stop_btn = QPushButton("Parar")
        self._stop_btn.setFixedWidth(70)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._request_stop)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self._progress_bar, stretch=1)
        progress_row.addWidget(self._pause_btn)
        progress_row.addWidget(self._stop_btn)
        root.addLayout(progress_row)
        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        root.addWidget(self._progress_label)

        self._file_progress_bar = QProgressBar()
        self._file_progress_bar.setVisible(False)
        self._file_progress_bar.setFixedHeight(10)
        self._file_progress_bar.setToolTip("Progresso por arquivo: chunks sendo embutidos")
        self._file_progress_bar.setTextVisible(False)
        root.addWidget(self._file_progress_bar)
        self._chunk_label = QLabel("")
        self._chunk_label.setVisible(False)
        root.addWidget(self._chunk_label)

        # ── Tabela de obras ──────────────────────────────────────────────────
        files_group = QGroupBox("Obras do corpus")
        files_layout = QVBoxLayout(files_group)

        # Filtros rapidos por status
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtrar:"))
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_btns: dict[str | None, QPushButton] = {}

        def _add_filter(label: str | None, display: str, color: str = "") -> None:
            btn = QPushButton(display)
            btn.setCheckable(True)
            btn.setChecked(label is None)
            if color:
                btn.setStyleSheet(
                    f"QPushButton:checked {{ background-color: {color}44; "
                    f"border: 1px solid {color}; border-radius: 3px; }}"
                )
            self._filter_group.addButton(btn)
            self._filter_btns[label] = btn
            btn.clicked.connect(lambda _c, lbl=label: self._set_filter(lbl))
            filter_row.addWidget(btn)

        _styles = _status_styles()
        _add_filter(None, "Todos")
        _add_filter(_STATUS_NEW,      _STATUS_NEW,      _styles[_STATUS_NEW][0])
        _add_filter(_STATUS_MODIFIED, _STATUS_MODIFIED, _styles[_STATUS_MODIFIED][0])
        _add_filter(_STATUS_INDEXED,  _STATUS_INDEXED,  _styles[_STATUS_INDEXED][0])
        _add_filter(_STATUS_REMOVED,  _STATUS_REMOVED,  _styles[_STATUS_REMOVED][0])
        filter_row.addStretch()
        files_layout.addLayout(filter_row)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filtrar por nome de arquivo...")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._apply_filters)
        files_layout.addWidget(self._search_edit)

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
        self._file_table.doubleClicked.connect(self._open_selected_file)
        self._file_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_table.customContextMenuRequested.connect(self._show_context_menu)
        files_layout.addWidget(self._file_table)

        remove_btn = QPushButton("Remover selecionado do indice")
        remove_btn.setToolTip("Remove do banco vetorial (nao apaga o arquivo original)")
        remove_btn.clicked.connect(self._remove_selected)
        files_layout.addWidget(remove_btn)

        root.addWidget(files_group, stretch=1)

        # ── Log ──────────────────────────────────────────────────────────────
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(110)
        self._log.setPlaceholderText("Aqui aparecem os detalhes das operacoes...")
        log_layout.addWidget(self._log)
        root.addWidget(log_group)

    # ── Navegacao ─────────────────────────────────────────────────────────────

    def _browse(self) -> None:
        current = self._path_edit.text().strip()
        start_dir = (
            current
            if current and Path(current).is_dir()
            else (
                QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
                or str(Path.home())
            )
        )
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta do corpus", start_dir)
        if folder:
            self._path_edit.setText(folder)
            set_config_value("paths.corpus_dir", folder)
            self._trigger_scan()

    def _on_folder_dropped(self, folder: str) -> None:
        set_config_value("paths.corpus_dir", folder)
        self._trigger_scan()

    def _corpus_dir(self) -> Path | None:
        text = self._path_edit.text().strip()
        return Path(text) if text else None

    # ── Checkbox de subpastas ─────────────────────────────────────────────────

    def _on_recursive_changed(self, _state: int) -> None:
        checked = self._recursive_chk.isChecked()
        set_config_value("gui.recursive_scan", str(checked).lower())
        self._trigger_scan()

    # ── Filtros da tabela ─────────────────────────────────────────────────────

    def _set_filter(self, label: str | None) -> None:
        self._active_status_filter = label
        self._apply_filters()

    def _apply_filters(self) -> None:
        search = self._search_edit.text().strip().lower()
        for row in range(self._file_table.rowCount()):
            name_item   = self._file_table.item(row, 0)
            status_item = self._file_table.item(row, 1)
            if name_item is None or status_item is None:
                self._file_table.setRowHidden(row, False)
                continue
            name_ok = not search or search in name_item.text().lower()
            status_ok = (
                self._active_status_filter is None
                or status_item.data(Qt.ItemDataRole.UserRole) == self._active_status_filter
            )
            self._file_table.setRowHidden(row, not (name_ok and status_ok))

    # ── Abrir arquivo / menu de contexto ─────────────────────────────────────

    def _open_selected_file(self) -> None:
        row = self._file_table.currentRow()
        if row < 0:
            return
        path_item = self._file_table.item(row, 3)
        if path_item:
            path = Path(path_item.text())
            if path.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _show_context_menu(self, pos: object) -> None:
        from PySide6.QtCore import QPoint

        if not isinstance(pos, QPoint):
            return
        row = self._file_table.rowAt(pos.y())
        if row < 0:
            return
        path_item = self._file_table.item(row, 3)
        if not path_item:
            return
        path = Path(path_item.text())

        menu = QMenu(self)
        act_open   = menu.addAction("Abrir arquivo")
        act_folder = menu.addAction("Abrir pasta")
        menu.addSeparator()
        act_remove = menu.addAction("Remover do indice")

        action = menu.exec(self._file_table.viewport().mapToGlobal(pos))
        if action == act_open and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        elif action == act_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
        elif action == act_remove:
            self._file_table.selectRow(row)
            self._remove_selected()

    # ── Scan (analise sem embedding) ──────────────────────────────────────────

    def _trigger_scan(self) -> None:
        corpus = self._corpus_dir()
        if corpus is None or not corpus.is_dir():
            return
        self._scan_btn.setEnabled(False)
        self._summary_label.setText("Analisando...")
        self._scan_worker = ScanWorker(
            self._container.ingest, corpus, recursive=self._recursive_chk.isChecked()
        )
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

        styles = _status_styles()
        parts = []
        if n_indexed:
            fg = styles[_STATUS_INDEXED][0]
            parts.append(f"<font color='{fg}'>{n_indexed} indexado{'s' if n_indexed != 1 else ''}</font>")
        if n_new:
            fg = styles[_STATUS_NEW][0]
            parts.append(f"<font color='{fg}'>{n_new} novo{'s' if n_new != 1 else ''}</font>")
        if n_modified:
            fg = styles[_STATUS_MODIFIED][0]
            parts.append(f"<font color='{fg}'>{n_modified} modificado{'s' if n_modified != 1 else ''}</font>")
        if n_removed:
            fg = styles[_STATUS_REMOVED][0]
            parts.append(f"<font color='{fg}'>{n_removed} removido{'s' if n_removed != 1 else ''}</font>")
        self._summary_label.setText(" · ".join(parts) if parts else f"{total} obras encontradas")

        self._file_table.setSortingEnabled(False)
        self._file_table.setRowCount(0)

        def _add_row(path_str: str, status: str) -> None:
            row_fg, row_bg = styles[status]
            p = Path(path_str)
            row = self._file_table.rowCount()
            self._file_table.insertRow(row)
            for col, text in enumerate([p.name, status, "", path_str]):
                item = QTableWidgetItem(text)
                item.setBackground(row_bg)
                self._file_table.setItem(row, col, item)
            status_item = self._file_table.item(row, 1)
            if status_item:
                status_item.setForeground(QColor(row_fg))
                status_item.setData(Qt.ItemDataRole.UserRole, status)
            chunks = sources.get(path_str, 0)
            chunk_item = self._file_table.item(row, 2)
            if chunk_item:
                chunk_item.setData(Qt.ItemDataRole.DisplayRole, chunks if chunks else None)

        for p in report.unchanged:
            _add_row(str(p), _STATUS_INDEXED)
        for p in report.new:
            _add_row(str(p), _STATUS_NEW)
        for p in report.modified:
            _add_row(str(p), _STATUS_MODIFIED)
        for s in report.removed:
            _add_row(s, _STATUS_REMOVED)

        self._file_table.setSortingEnabled(True)
        self._apply_filters()

        db_dir = self._container.config.paths.resolved_db_dir()
        if db_dir.exists():
            if sources:
                total_chunks = sum(sources.values())
                n_docs = len(sources)
                self._log_append(
                    f"Banco em: {db_dir}  "
                    f"({n_docs} doc{'s' if n_docs != 1 else ''}, "
                    f"{total_chunks} chunk{'s' if total_chunks != 1 else ''})"
                )
            else:
                self._log_append(
                    f"Pasta rag/ existe em {db_dir} mas sem dados indexados — "
                    "clique em 'Ingerir mudancas' para indexar."
                )
        else:
            self._log_append(f"Banco ainda nao existe em: {db_dir}")

        if n_new or n_modified:
            self._log_append(
                f"Scan concluido: {n_new} nova(s), {n_modified} modificada(s), "
                f"{n_indexed} ja indexada(s), {n_removed} removida(s)."
            )

    def _on_scan_error(self, msg: str) -> None:
        self._scan_btn.setEnabled(True)
        self._summary_label.setText("Erro no scan")
        self._log_append(f"Erro no scan: {msg}")

    # ── Remocao ───────────────────────────────────────────────────────────────

    def _remove_selected(self) -> None:
        selected = self._file_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Remover", "Selecione uma ou mais obras na lista primeiro.")
            return
        paths = [
            item.text()
            for index in selected
            if (item := self._file_table.item(index.row(), 3)) is not None
        ]
        if not paths:
            return
        if len(paths) == 1:
            msg = f"Remover '{Path(paths[0]).name}' do banco vetorial?\n\nO arquivo original nao sera apagado."
        else:
            names = "\n".join(f"  - {Path(p).name}" for p in paths)
            msg = f"Remover {len(paths)} obras do banco vetorial?\n\n{names}\n\nOs arquivos originais nao serao apagados."
        if QMessageBox.question(
            self, "Remover do indice", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        errors = []
        for path_str in paths:
            try:
                self._container.ingest.remove_file(path_str)
                self._log_append(f"Removido do indice: {Path(path_str).name}")
            except Exception as exc:
                errors.append(f"{Path(path_str).name}: {exc}")
        if errors:
            QMessageBox.critical(self, "Erro ao remover", "\n".join(errors))
        self._trigger_scan()

    # ── Ingestao ──────────────────────────────────────────────────────────────

    def _ingest_incremental(self) -> None:
        self._start_ingest(full=False)

    def _ingest_full(self) -> None:
        if QMessageBox.question(
            self, "Reconstruir indice",
            "Apagar todo o indice e re-ingerir do zero?\n\nIsso pode demorar bastante.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._start_ingest(full=True)

    def _start_ingest(self, full: bool) -> None:
        corpus = self._corpus_dir()
        if corpus is None:
            QMessageBox.warning(self, "Atencao", "Selecione a pasta do corpus primeiro.")
            return
        if not corpus.is_dir():
            QMessageBox.warning(self, "Atencao", f"Pasta nao encontrada:\n{corpus}")
            return
        self._set_busy(True)
        self._progress_bar.setValue(0)
        self._ingest_start_time = time.monotonic()
        self._log_append(f"{'Reconstruindo' if full else 'Ingerindo'} corpus: {corpus}")
        self._ingest_worker = IngestWorker(
            self._container, corpus, full=full, recursive=self._recursive_chk.isChecked()
        )
        self._ingest_worker.progress.connect(self._on_progress)
        self._ingest_worker.file_progress.connect(self._on_file_progress)
        self._ingest_worker.file_result.connect(self._on_file_result)
        self._ingest_worker.finished.connect(self._on_ingest_done)
        self._ingest_worker.stopped.connect(self._on_ingest_stopped)
        self._ingest_worker.paused.connect(self._on_paused)
        self._ingest_worker.resumed.connect(self._on_resumed)
        self._ingest_worker.error.connect(self._on_ingest_error)
        self._ingest_worker.start()

    def _on_progress(self, filename: str, current: int, total: int) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        elapsed = time.monotonic() - self._ingest_start_time
        if current > 0:
            eta = (elapsed / current) * (total - current)
            eta_str = f"  ETA: {eta:.0f}s" if eta > 1 else ""
        else:
            eta_str = ""
        self._progress_label.setText(f"[{current}/{total}] {filename}{eta_str}")

    def _on_file_progress(self, current: int, total: int) -> None:
        self._file_progress_bar.setMaximum(total)
        self._file_progress_bar.setValue(current)
        self._chunk_label.setText(f"chunk {current} de {total}")

    def _on_file_result(self, filename: str, ok: bool, msg: str) -> None:
        if ok:
            self._log_append(f"  ok  {filename}")
        else:
            self._log_append(f"  err {filename}: {msg}")

    def _on_paused(self) -> None:
        self._pause_btn.setText("Continuar")
        self._progress_label.setText("Em pausa...")

    def _on_resumed(self) -> None:
        self._pause_btn.setText("Pausar")

    def _on_ingest_done(self, report: IngestReport) -> None:
        self._set_busy(False)
        elapsed_s = report.elapsed_ms / 1000
        self._log_append(
            f"Concluido: +{report.added} adicionados  ~{report.updated} atualizados  "
            f"-{report.removed} removidos  {elapsed_s:.1f}s"
        )
        if elapsed_s >= _NOTIFY_THRESHOLD_S:
            self.notification_requested.emit(
                "Ingestao concluida",
                f"+{report.added} adicionados  ~{report.updated} atualizados  {elapsed_s:.0f}s",
            )
        self._trigger_scan()
        self.ingest_done.emit(report)

    def _on_ingest_stopped(self, report: IngestReport) -> None:
        self._set_busy(False)
        self._log_append(
            f"Interrompido: +{report.added} adicionados  ~{report.updated} atualizados  "
            f"-{report.removed} removidos  {report.elapsed_ms / 1000:.1f}s"
        )
        self._trigger_scan()

    def _on_ingest_error(self, msg: str) -> None:
        self._set_busy(False)
        self._log_append(f"Erro fatal: {msg}")
        QMessageBox.critical(self, "Erro na ingestao", msg)

    def _toggle_pause(self) -> None:
        if self._ingest_worker is None:
            return
        if self._pause_btn.text() == "Pausar":
            self._ingest_worker.pause()
        else:
            self._ingest_worker.resume()

    def _request_stop(self) -> None:
        if self._ingest_worker:
            self._ingest_worker.stop()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool) -> None:
        self._ingest_btn.setEnabled(not busy)
        self._recreate_btn.setEnabled(not busy)
        self._scan_btn.setEnabled(not busy)
        self._progress_bar.setVisible(busy)
        self._progress_label.setVisible(busy)
        self._file_progress_bar.setVisible(busy)
        self._chunk_label.setVisible(busy)
        self._pause_btn.setVisible(busy)
        self._stop_btn.setVisible(busy)
        if not busy:
            self._progress_label.setText("")
            self._pause_btn.setText("Pausar")
            self._file_progress_bar.setValue(0)
            self._chunk_label.setText("")

    def _log_append(self, msg: str) -> None:
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())
