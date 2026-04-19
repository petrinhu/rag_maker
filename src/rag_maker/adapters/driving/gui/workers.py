from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from rag_maker.application.ingest_use_case import ChangeReport, IngestReport, IngestUseCase
from rag_maker.application.query_use_case import QueryUseCase
from rag_maker.composition.container import Container
from rag_maker.domain.models import QueryResult


class IngestWorker(QThread):
    finished = Signal(object)       # IngestReport
    error = Signal(str)
    progress = Signal(str, int, int)  # filename, current, total

    def __init__(self, container: Container, corpus_dir: Path, full: bool = False) -> None:
        super().__init__()
        self._container = container
        self._corpus_dir = corpus_dir
        self._full = full

    def run(self) -> None:
        def _on_progress(filename: str, current: int, total: int) -> None:
            self.progress.emit(filename, current, total)

        try:
            if self._full:
                report: IngestReport = self._container.ingest.recreate_all(
                    self._corpus_dir, on_progress=_on_progress
                )
            else:
                report = self._container.ingest.ingest_incremental(
                    self._corpus_dir, on_progress=_on_progress
                )
            self.finished.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))


class ScanWorker(QThread):
    finished = Signal(object)  # ChangeReport
    error = Signal(str)

    def __init__(self, ingest_uc: IngestUseCase, corpus_dir: Path) -> None:
        super().__init__()
        self._ingest_uc = ingest_uc
        self._corpus_dir = corpus_dir

    def run(self) -> None:
        try:
            report: ChangeReport = self._ingest_uc.scan_changes(self._corpus_dir)
            self.finished.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))


class QueryWorker(QThread):
    finished = Signal(object)   # QueryResult
    error = Signal(str)

    def __init__(self, query_uc: QueryUseCase, query: str, top_k: int) -> None:
        super().__init__()
        self._query_uc = query_uc
        self._query = query
        self._top_k = top_k

    def run(self) -> None:
        try:
            result: QueryResult = self._query_uc.answer(self._query, top_k=self._top_k)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
