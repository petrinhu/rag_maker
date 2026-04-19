from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from rag_maker.application.ingest_use_case import ChangeReport, IngestReport, IngestUseCase
from rag_maker.application.query_use_case import QueryUseCase
from rag_maker.composition.container import Container
from rag_maker.domain.models import QueryResult


class IngestWorker(QThread):
    finished       = Signal(object)        # IngestReport
    stopped        = Signal(object)        # IngestReport parcial
    error          = Signal(str)
    progress       = Signal(str, int, int) # filename, current, total
    file_progress  = Signal(int, int)      # chunk_current, chunk_total (dentro do arquivo)
    file_result    = Signal(str, bool, str)# filename, success, error_msg
    paused         = Signal()
    resumed        = Signal()

    def __init__(
        self,
        container: Container,
        corpus_dir: Path,
        full: bool = False,
        recursive: bool = True,
    ) -> None:
        super().__init__()
        self._container  = container
        self._corpus_dir = corpus_dir
        self._full       = full
        self._recursive  = recursive
        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # não pausado inicialmente

    def pause(self) -> None:
        self._pause_event.clear()
        self.paused.emit()

    def resume(self) -> None:
        self._pause_event.set()
        self.resumed.emit()

    def stop(self) -> None:
        self._stop_event.set()
        self._pause_event.set()  # desbloqueia se estiver pausado

    def _should_continue(self) -> bool:
        self._pause_event.wait()  # bloqueia enquanto pausado
        return not self._stop_event.is_set()

    def run(self) -> None:
        def _on_progress(filename: str, current: int, total: int) -> None:
            self.progress.emit(filename, current, total)

        def _on_chunk_progress(current: int, total: int) -> None:
            self.file_progress.emit(current, total)

        def _on_file_done(filename: str, ok: bool, msg: str) -> None:
            self.file_result.emit(filename, ok, msg)

        try:
            if self._full:
                report: IngestReport = self._container.ingest.recreate_all(
                    self._corpus_dir,
                    on_progress=_on_progress,
                    on_file_done=_on_file_done,
                    on_chunk_progress=_on_chunk_progress,
                    should_continue=self._should_continue,
                    recursive=self._recursive,
                )
            else:
                report = self._container.ingest.ingest_incremental(
                    self._corpus_dir,
                    on_progress=_on_progress,
                    on_file_done=_on_file_done,
                    on_chunk_progress=_on_chunk_progress,
                    should_continue=self._should_continue,
                    recursive=self._recursive,
                )
            if self._stop_event.is_set():
                self.stopped.emit(report)
            else:
                self.finished.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))


class ScanWorker(QThread):
    finished = Signal(object)  # ChangeReport
    error    = Signal(str)

    def __init__(self, ingest_uc: IngestUseCase, corpus_dir: Path, recursive: bool = True) -> None:
        super().__init__()
        self._ingest_uc  = ingest_uc
        self._corpus_dir = corpus_dir
        self._recursive  = recursive

    def run(self) -> None:
        try:
            report: ChangeReport = self._ingest_uc.scan_changes(self._corpus_dir, recursive=self._recursive)
            self.finished.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))


class QueryWorker(QThread):
    finished = Signal(object)  # QueryResult
    error    = Signal(str)

    def __init__(self, query_uc: QueryUseCase, query: str, top_k: int) -> None:
        super().__init__()
        self._query_uc = query_uc
        self._query    = query
        self._top_k    = top_k

    def run(self) -> None:
        try:
            result: QueryResult = self._query_uc.answer(self._query, top_k=self._top_k)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
