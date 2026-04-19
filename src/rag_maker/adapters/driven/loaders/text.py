from __future__ import annotations

from pathlib import Path

from rag_maker.adapters.driven.loaders._utils import sha256_file
from rag_maker.domain.models import Document, LoadError

_SUPPORTED = {".txt", ".md", ".markdown"}
_ENCODINGS = ("utf-8", "utf-8-sig", "latin-1", "cp1252")


class TextLoader:
    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() in _SUPPORTED

    def load(self, path: Path) -> Document:
        content = _read(path)
        if not content.strip():
            raise LoadError(f"'{path.name}' está vazio")
        return Document(
            path=path,
            content=content,
            content_hash=sha256_file(path),
            mtime=path.stat().st_mtime,
            metadata={"format": path.suffix.lstrip(".")},
        )


def _read(path: Path) -> str:
    for enc in _ENCODINGS:
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise LoadError(f"'{path.name}' não pôde ser decodificado (tentadas: {_ENCODINGS})")
