# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from rag_maker.application.config import AppConfig
from rag_maker.domain.chunker import RecursiveCharacterChunker
from rag_maker.domain.models import IndexedChunk
from rag_maker.domain.ports.embedder import EmbedderPort
from rag_maker.domain.ports.loader import LoaderPort
from rag_maker.domain.ports.vector_store import VectorStorePort

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, int, int], None]  # (filename, current, total)
FileDoneFn = Callable[[str, bool, str], None]  # (filename, success, error_msg)
ShouldContinueFn = Callable[[], bool]
ChunkProgressFn = Callable[[int, int], None]  # (current_chunk, total_chunks)


@runtime_checkable
class _FtsIndexMaintainable(Protocol):
    """Capacidade opcional de manutenção de índice FTS.

    NÃO faz parte de `VectorStorePort` (domain/ports) porque esta unidade de
    trabalho está restrita a `ingest_use_case.py` + `vector_store.py`. O
    adapter LanceDB implementa este método; detectamos via isinstance
    (Protocol runtime_checkable) para não quebrar outros adapters/fakes que
    ainda não o implementam. TODO de arquitetura: promover `ensure_fts_index`
    para `VectorStorePort` oficialmente (requer editar domain/ports/vector_store.py,
    fora do escopo desta unidade) — ver AUD-TEST-2 em AUDIT_FIND.md.
    """

    def ensure_fts_index(self) -> None: ...


class _IngestionStopped(Exception):
    """Lançada quando should_continue() retorna False dentro de _ingest_file."""


@dataclass
class _ManifestEntry:
    mtime: float
    content_hash: str


@dataclass
class ChangeReport:
    new: list[Path] = field(default_factory=list)
    modified: list[Path] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[Path] = field(default_factory=list)


@dataclass
class IngestReport:
    added: int = 0
    updated: int = 0
    removed: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    elapsed_ms: float = 0.0


class IngestUseCase:
    def __init__(
        self,
        embedder: EmbedderPort,
        store: VectorStorePort,
        loader_for: Callable[[Path], LoaderPort],
        config: AppConfig,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._loader_for = loader_for
        self._config = config
        self._chunker = RecursiveCharacterChunker(
            size=config.chunking.size,
            overlap=config.chunking.overlap,
        )
        self._manifest_path = config.paths.resolved_db_dir() / "manifest.json"
        self._db_dir = config.paths.resolved_db_dir()

    # ── Manifest ──────────────────────────────────────────────────────────────

    def _load_manifest(self) -> dict[str, _ManifestEntry]:
        if not self._manifest_path.exists():
            return {}
        with open(self._manifest_path) as f:
            raw: dict[str, Any] = json.load(f)
        return {
            k: _ManifestEntry(mtime=float(v["mtime"]), content_hash=str(v["content_hash"]))
            for k, v in raw.items()
        }

    def _save_manifest(self, manifest: dict[str, _ManifestEntry]) -> None:
        self._manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._manifest_path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(
                {
                    k: {"mtime": v.mtime, "content_hash": v.content_hash}
                    for k, v in manifest.items()
                },
                f,
                indent=2,
            )
        tmp.replace(self._manifest_path)

    # ── Change detection ──────────────────────────────────────────────────────

    def _is_loadable(self, path: Path) -> bool:
        try:
            self._loader_for(path)
            return True
        except Exception:
            return False

    def _repair_manifest_from_store(
        self, manifest: dict[str, _ManifestEntry]
    ) -> dict[str, _ManifestEntry]:
        """Se o manifest estiver vazio mas o store tiver dados, reconstrói a partir do LanceDB."""
        if manifest:
            return manifest
        sources = self._store.list_sources()
        if not sources:
            return manifest
        repaired: dict[str, _ManifestEntry] = {}
        for source_path_str in sources:
            path = Path(source_path_str)
            if path.exists():
                with contextlib.suppress(Exception):
                    repaired[source_path_str] = _ManifestEntry(
                        mtime=path.stat().st_mtime,
                        content_hash=_sha256_file(path),
                    )
        if repaired:
            self._save_manifest(repaired)
        return repaired

    def scan_changes(self, corpus_dir: Path, recursive: bool = True) -> ChangeReport:
        manifest = self._load_manifest()
        manifest = self._repair_manifest_from_store(manifest)
        # F12.19/AUD-SEC-6: `ignored` precisa ser um conjunto de `Path` RESOLVIDOS
        # (não `str`) e a checagem precisa ser `Path.is_relative_to`, não
        # `str.startswith`. Comparação por prefixo de string casa diretórios
        # IRMÃOS por acidente: a string "corpus/secret2/notas.txt" começa com
        # "corpus/secret", então ignorar "corpus/secret" excluía silenciosamente
        # "corpus/secret2/" inteiro. `resolve()` normaliza `..`/symlinks/relativos
        # para que a comparação de componentes de caminho seja exata.
        ignored = {p.resolve() for p in self._config.ignored.paths} | {self._db_dir.resolve()}
        report = ChangeReport()
        seen: set[str] = set()

        glob_fn = corpus_dir.rglob if recursive else corpus_dir.glob
        for path in sorted(glob_fn("*")):
            if not path.is_file():
                continue
            resolved_path = path.resolve()
            if any(resolved_path.is_relative_to(ig) for ig in ignored):
                continue
            if not self._is_loadable(path):
                continue
            key = str(path)
            seen.add(key)
            entry = manifest.get(key)
            if entry is None:
                report.new.append(path)
            elif path.stat().st_mtime != entry.mtime or _sha256_file(path) != entry.content_hash:
                report.modified.append(path)
            else:
                report.unchanged.append(path)

        for key in manifest:
            if key not in seen:
                report.removed.append(key)

        return report

    # ── File ingestion ────────────────────────────────────────────────────────

    def _ingest_file(
        self,
        path: Path,
        on_chunk_progress: ChunkProgressFn | None = None,
        should_continue: ShouldContinueFn | None = None,
    ) -> list[IndexedChunk]:
        loader = self._loader_for(path)
        doc = loader.load(path)
        chunks = self._chunker.chunk(doc)
        total = len(chunks)
        vectors: list[tuple[float, ...]] = []
        for i, chunk in enumerate(chunks):
            if should_continue and not should_continue():
                raise _IngestionStopped()
            if on_chunk_progress:
                on_chunk_progress(i, total)
            vectors.append(self._embedder.embed(chunk.content))
        if on_chunk_progress:
            on_chunk_progress(total, total)
        return [IndexedChunk(chunk=c, vector=v) for c, v in zip(chunks, vectors, strict=True)]

    # ── Public API ────────────────────────────────────────────────────────────

    def ingest_incremental(
        self,
        corpus_dir: Path,
        on_progress: ProgressFn | None = None,
        on_file_done: FileDoneFn | None = None,
        on_chunk_progress: ChunkProgressFn | None = None,
        should_continue: ShouldContinueFn | None = None,
        recursive: bool = True,
    ) -> IngestReport:
        t0 = time.monotonic()
        changes = self.scan_changes(corpus_dir, recursive=recursive)
        manifest = self._load_manifest()
        report = IngestReport()
        new_set = {str(p) for p in changes.new}

        for source_path in changes.removed:
            if should_continue and not should_continue():
                break
            self._store.delete_by_source(source_path)
            manifest.pop(source_path, None)
            report.removed += 1

        to_process = changes.new + changes.modified
        for i, path in enumerate(to_process):
            if should_continue and not should_continue():
                break
            if on_progress:
                on_progress(path.name, i + 1, len(to_process))
            try:
                indexed = self._ingest_file(
                    path,
                    on_chunk_progress=on_chunk_progress,
                    should_continue=should_continue,
                )
                # AUD-CORRECT-1: chunk_id é sha256(path:offset) — NUNCA sensível a
                # conteúdo. upsert() faz merge_insert("chunk_id") (update/insert,
                # nunca delete). Se um arquivo MODIFICADO encolhe ou desloca
                # offsets, chunks antigos ficam órfãos para sempre e continuam
                # sendo retornados por hybrid_search como se fossem atuais.
                # Invariante: para reprocessamento de arquivo já indexado, a
                # substituição precisa ser delete-then-insert (nunca upsert puro).
                # Arquivos NOVOS não têm nada para apagar; deletar depois de
                # _ingest_file ter sucesso (não antes) preserva os dados antigos
                # caso o parse/embedding falhe e a exceção seja capturada abaixo.
                if str(path) not in new_set:
                    self._store.delete_by_source(str(path))
                self._store.upsert(indexed)
                manifest[str(path)] = _ManifestEntry(
                    mtime=path.stat().st_mtime,
                    content_hash=_sha256_file(path),
                )
                if str(path) in new_set:
                    report.added += 1
                else:
                    report.updated += 1
                if on_file_done:
                    on_file_done(path.name, True, "")
                self._save_manifest(manifest)
            except _IngestionStopped:
                break  # não adiciona ao manifest; será re-processado na próxima vez
            except Exception as exc:
                report.errors.append((str(path), str(exc)))
                if on_file_done:
                    on_file_done(path.name, False, str(exc))

        # AUD-TEST-2: ensure_fts_index() precisa ser chamado após qualquer
        # mutação de linhas (upsert ou delete) para que hybrid_search(query_type=
        # "fts") não opere sobre um índice invertido inexistente/desatualizado —
        # sem isso a metade lexical da RRF degrada silenciosamente para
        # dense-only. Reconstruir uma vez ao fim do lote (não por arquivo) é
        # suficiente e evita custo de rebuild repetido por item.
        if report.added or report.updated or report.removed:
            self._ensure_fts_index_if_supported()

        report.elapsed_ms = (time.monotonic() - t0) * 1000
        return report

    def _ensure_fts_index_if_supported(self) -> None:
        if isinstance(self._store, _FtsIndexMaintainable):
            self._store.ensure_fts_index()
        else:
            logger.warning(
                "vector_store_no_fts_maintenance",
                extra={"store_type": type(self._store).__name__},
            )

    def recreate_all(
        self,
        corpus_dir: Path,
        on_progress: ProgressFn | None = None,
        on_file_done: FileDoneFn | None = None,
        on_chunk_progress: ChunkProgressFn | None = None,
        should_continue: ShouldContinueFn | None = None,
        recursive: bool = True,
    ) -> IngestReport:
        t0 = time.monotonic()
        manifest = self._load_manifest()
        for source_path in list(manifest.keys()):
            self._store.delete_by_source(source_path)
        manifest.clear()
        self._save_manifest(manifest)
        report = self.ingest_incremental(
            corpus_dir,
            on_progress=on_progress,
            on_file_done=on_file_done,
            on_chunk_progress=on_chunk_progress,
            should_continue=should_continue,
            recursive=recursive,
        )
        report.elapsed_ms = (time.monotonic() - t0) * 1000
        return report

    def remove_file(self, source_path: str) -> None:
        self._store.delete_by_source(source_path)
        manifest = self._load_manifest()
        manifest.pop(source_path, None)
        self._save_manifest(manifest)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
