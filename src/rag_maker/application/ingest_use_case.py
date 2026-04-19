from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag_maker.application.config import AppConfig
from rag_maker.domain.chunker import RecursiveCharacterChunker
from rag_maker.domain.models import IndexedChunk
from rag_maker.domain.ports.embedder import EmbedderPort
from rag_maker.domain.ports.loader import LoaderPort
from rag_maker.domain.ports.vector_store import VectorStorePort

ProgressFn = Callable[[str, int, int], None]  # (filename, current, total)


@dataclass
class _ManifestEntry:
    mtime: float
    content_hash: str


@dataclass
class ChangeReport:
    new: list[Path] = field(default_factory=list)
    modified: list[Path] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0


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
        self._manifest_path = config.paths.db_dir / "manifest.json"

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
                {k: {"mtime": v.mtime, "content_hash": v.content_hash} for k, v in manifest.items()},
                f,
                indent=2,
            )
        tmp.replace(self._manifest_path)

    # ── Change detection ──────────────────────────────────────────────────────

    def scan_changes(self, corpus_dir: Path) -> ChangeReport:
        manifest = self._load_manifest()
        ignored = {str(p) for p in self._config.ignored.paths}
        report = ChangeReport()
        seen: set[str] = set()

        for path in sorted(corpus_dir.rglob("*")):
            if not path.is_file():
                continue
            if any(str(path).startswith(ig) for ig in ignored):
                continue
            key = str(path)
            seen.add(key)
            entry = manifest.get(key)
            if entry is None:
                report.new.append(path)
            elif path.stat().st_mtime != entry.mtime or _sha256_file(path) != entry.content_hash:
                report.modified.append(path)
            else:
                report.unchanged += 1

        for key in manifest:
            if key not in seen:
                report.removed.append(key)

        return report

    # ── File ingestion ────────────────────────────────────────────────────────

    def _ingest_file(self, path: Path) -> list[IndexedChunk]:
        loader = self._loader_for(path)
        doc = loader.load(path)
        chunks = self._chunker.chunk(doc)
        texts = [c.content for c in chunks]
        vectors = self._embedder.embed_batch(texts)
        return [IndexedChunk(chunk=c, vector=v) for c, v in zip(chunks, vectors, strict=True)]

    # ── Public API ────────────────────────────────────────────────────────────

    def ingest_incremental(
        self,
        corpus_dir: Path,
        on_progress: ProgressFn | None = None,
    ) -> IngestReport:
        t0 = time.monotonic()
        changes = self.scan_changes(corpus_dir)
        manifest = self._load_manifest()
        report = IngestReport()
        new_set = {str(p) for p in changes.new}

        for source_path in changes.removed:
            self._store.delete_by_source(source_path)
            manifest.pop(source_path, None)
            report.removed += 1

        to_process = changes.new + changes.modified
        for i, path in enumerate(to_process):
            if on_progress:
                on_progress(path.name, i + 1, len(to_process))
            try:
                indexed = self._ingest_file(path)
                self._store.upsert(indexed)
                manifest[str(path)] = _ManifestEntry(
                    mtime=path.stat().st_mtime,
                    content_hash=_sha256_file(path),
                )
                if str(path) in new_set:
                    report.added += 1
                else:
                    report.updated += 1
            except Exception as exc:
                report.errors.append((str(path), str(exc)))

        self._save_manifest(manifest)
        report.elapsed_ms = (time.monotonic() - t0) * 1000
        return report

    def recreate_all(
        self,
        corpus_dir: Path,
        on_progress: ProgressFn | None = None,
    ) -> IngestReport:
        t0 = time.monotonic()
        manifest = self._load_manifest()
        for source_path in list(manifest.keys()):
            self._store.delete_by_source(source_path)
        manifest.clear()
        self._save_manifest(manifest)
        report = self.ingest_incremental(corpus_dir, on_progress=on_progress)
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
