# SPDX-License-Identifier: AGPL-3.0-or-later
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

    def list_sources(self) -> dict[str, int]: ...

    def ensure_fts_index(self) -> None:
        """Garante que o índice invertido (full-text search) está vivo e atualizado.

        AUD-TEST-2/F12.29: precisa ser chamado após QUALQUER mutação de linhas
        (`upsert`/`delete_by_source`). Sem isso, a metade lexical (FTS) de
        `hybrid_search` opera sobre um índice inexistente ou desatualizado e o
        RRF degrada silenciosamente para dense-only — sem erro visível, só
        recall pior. Idempotente: chamar quando já está atualizado é barato/no-op.
        """
        ...

    def ensure_vector_index(self) -> None:
        """Garante que o índice vetorial (ANN, ex. HNSW/IVF) está vivo e atualizado.

        Mesmo invariante de `ensure_fts_index`: chamar após mutação de linhas.
        Sem índice vetorial vivo, a busca densa cai para varredura exaustiva
        (correta, porém lenta) até o índice ser reconstruído. Idempotente.
        """
        ...
