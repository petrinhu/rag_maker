from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from rag_maker.application.ingest_use_case import IngestReport
from rag_maker.application.query_use_case import QueryUseCase
from rag_maker.composition.container import Container
from rag_maker.domain.models import QueryResult


class IngestWorker(QThread):
    finished = Signal(object)   # IngestReport
    error = Signal(str)

    def __init__(self, container: Container, corpus_dir: Path, full: bool = False) -> None:
        super().__init__()
        self._container = container
        self._corpus_dir = corpus_dir
        self._full = full

    def run(self) -> None:
        try:
            if self._full:
                report: IngestReport = self._container.ingest.recreate_all(self._corpus_dir)
            else:
                report = self._container.ingest.ingest_incremental(self._corpus_dir)
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
