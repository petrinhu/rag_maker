from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from rag_maker.adapters.driven.loaders._utils import sha256_file
from rag_maker.domain.models import Document, LoadError

_MIN_CHARS_PER_PAGE = 50


class PdfLoader:
    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def load(self, path: Path) -> Document:
        try:
            reader = PdfReader(str(path))
        except PdfReadError as e:
            raise LoadError(f"Erro ao abrir PDF '{path}': {e}") from e

        pages_text = [page.extract_text() or "" for page in reader.pages]
        content = "\n".join(pages_text).strip()

        if not content or _is_image_pdf(pages_text):
            raise LoadError(f"'{path.name}' parece ser PDF de imagem sem texto extraível")

        return Document(
            path=path,
            content=content,
            content_hash=sha256_file(path),
            mtime=path.stat().st_mtime,
            metadata={"page_count": str(len(reader.pages)), "format": "pdf"},
        )


def _is_image_pdf(pages_text: list[str]) -> bool:
    if not pages_text:
        return False
    avg = sum(len(t) for t in pages_text) / len(pages_text)
    return avg < _MIN_CHARS_PER_PAGE
