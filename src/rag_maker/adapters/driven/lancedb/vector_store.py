from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import lancedb  # type: ignore[import-untyped]
import pyarrow as pa

from rag_maker.domain.models import Chunk, IndexedChunk, RetrievedChunk
from rag_maker.domain.scoring import rrf_fuse

_DEFAULT_TABLE = "chunks"


class LanceVectorStore:
    """Implementa VectorStorePort usando LanceDB (HNSW + FTS via tantivy).

    A dimensão do embedding deve ser conhecida na construção — ela define o
    schema da tabela e não pode mudar depois.
    """

    def __init__(
        self,
        db_path: Path,
        embedding_dim: int,
        table_name: str = _DEFAULT_TABLE,
    ) -> None:
        self._dim = embedding_dim
        self._table_name = table_name
        self._db: Any = lancedb.connect(str(db_path))
        self._table: Any = self._open_or_create()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _schema(self) -> pa.Schema:
        return pa.schema(
            [
                pa.field("chunk_id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self._dim)),
                pa.field("text", pa.string()),
                pa.field("source_path", pa.string()),
                pa.field("char_offset", pa.int64()),
                pa.field("page", pa.int64(), nullable=True),
                pa.field("section", pa.string(), nullable=True),
                pa.field("content_hash", pa.string()),
                pa.field("mtime", pa.float64()),
            ]
        )

    def _open_or_create(self) -> Any:
        response = self._db.list_tables()
        # list_tables() retorna ListTablesResponse em lancedb>=0.10, não uma lista
        names: list[str] = response.tables if hasattr(response, "tables") else list(response)
        if self._table_name in names:
            return self._db.open_table(self._table_name)
        try:
            return self._db.create_table(self._table_name, schema=self._schema())
        except ValueError:
            return self._db.open_table(self._table_name)

    # ── VectorStorePort ───────────────────────────────────────────────────────

    def upsert(self, chunks: list[IndexedChunk]) -> None:
        if not chunks:
            return
        rows = [_to_row(ic) for ic in chunks]
        (
            self._table.merge_insert("chunk_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(rows)
        )

    def delete_by_source(self, source_path: str) -> None:
        safe = source_path.replace("'", "''")
        self._table.delete(f"source_path = '{safe}'")

    def count(self) -> int:
        return int(self._table.count_rows())

    def stats(self) -> dict[str, Any]:
        return {
            "count": self.count(),
            "table_name": self._table_name,
            "embedding_dim": self._dim,
        }

    def list_sources(self) -> dict[str, int]:
        try:
            n = self._table.count_rows()
            if n == 0:
                return {}
            rows = self._table.search().select(["source_path"]).limit(n).to_list()
            counts: dict[str, int] = {}
            for row in rows:
                key = str(row["source_path"])
                counts[key] = counts.get(key, 0) + 1
            return counts
        except Exception:
            return {}

    def hybrid_search(
        self,
        vector: tuple[float, ...],
        text: str,
        top_n: int,
    ) -> list[RetrievedChunk]:
        # Dense (HNSW cosine)
        dense_rows: list[dict[str, Any]] = (
            self._table.search(list(vector)).metric("cosine").limit(top_n).to_list()
        )
        dense_ids = [str(r["chunk_id"]) for r in dense_rows]

        # Lexical (FTS)
        lexical_rows: list[dict[str, Any]] = []
        lexical_ids: list[str] = []
        try:
            lexical_rows = self._table.search(text, query_type="fts").limit(top_n).to_list()
            lexical_ids = [str(r["chunk_id"]) for r in lexical_rows]
        except Exception:
            pass

        # RRF fusion
        rrf_scores = rrf_fuse(dense_ids, lexical_ids)

        # Row lookup
        all_rows: dict[str, dict[str, Any]] = {}
        for r in dense_rows + lexical_rows:
            all_rows[str(r["chunk_id"])] = r

        dense_score_map = {
            str(r["chunk_id"]): max(0.0, 1.0 - float(r.get("_distance", 1.0))) for r in dense_rows
        }
        lexical_set = set(lexical_ids)

        results: list[RetrievedChunk] = []
        for cid, rrf_score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True):
            row = all_rows.get(cid)
            if row is None:
                continue
            results.append(
                RetrievedChunk(
                    chunk=_row_to_chunk(row),
                    dense_score=dense_score_map.get(cid, 0.0),
                    lexical_score=1.0 if cid in lexical_set else 0.0,
                    rrf_score=rrf_score,
                )
            )

        return results[:top_n]

    # ── Manutenção de índices ─────────────────────────────────────────────────

    def ensure_fts_index(self) -> None:
        with contextlib.suppress(Exception):
            self._table.create_fts_index("text", replace=True)

    def ensure_vector_index(self) -> None:
        with contextlib.suppress(Exception):
            self._table.create_index(metric="cosine", replace=True)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_row(ic: IndexedChunk) -> dict[str, Any]:
    return {
        "chunk_id": ic.chunk.chunk_id,
        "vector": [float(v) for v in ic.vector],
        "text": ic.chunk.content,
        "source_path": str(ic.chunk.document_path),
        "char_offset": ic.chunk.char_offset,
        "page": ic.chunk.page,
        "section": ic.chunk.section,
        "content_hash": "",
        "mtime": ic.chunk.mtime,
    }


def _row_to_chunk(row: dict[str, Any]) -> Chunk:
    page_raw = row.get("page")
    page = int(page_raw) if page_raw is not None else None
    section_raw = row.get("section")
    section = str(section_raw) if section_raw else None
    return Chunk(
        chunk_id=str(row["chunk_id"]),
        document_path=Path(str(row["source_path"])),
        content=str(row["text"]),
        char_offset=int(row["char_offset"]),
        mtime=float(row["mtime"]),
        page=page,
        section=section,
    )
