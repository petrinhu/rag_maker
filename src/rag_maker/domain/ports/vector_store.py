from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rag_maker.domain.models import IndexedChunk, RetrievedChunk


@runtime_checkable
class VectorStorePort(Protocol):
    def upsert(self, chunks: list[IndexedChunk]) -> None: ...

    def delete_by_source(self, source_path: str) -> None: ...

    def hybrid_search(
        self,
        vector: tuple[float, ...],
        text: str,
        top_n: int,
    ) -> list[RetrievedChunk]: ...

    def count(self) -> int: ...

    def stats(self) -> dict[str, Any]: ...
