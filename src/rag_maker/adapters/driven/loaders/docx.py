from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument

from rag_maker.adapters.driven.loaders._utils import sha256_file
from rag_maker.domain.models import Document, LoadError


class DocxLoader:
    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() == ".docx"

    def load(self, path: Path) -> Document:
        try:
            doc = DocxDocument(str(path))
        except Exception as e:
            raise LoadError(f"Erro ao abrir DOCX '{path}': {e}") from e

        parts = [para.text for para in doc.paragraphs if para.text.strip()]
        content = "\n".join(parts).strip()
        if not content:
            raise LoadError(f"'{path.name}' não contém texto extraível")

        return Document(
            path=path,
            content=content,
            content_hash=sha256_file(path),
            mtime=path.stat().st_mtime,
            metadata={"format": "docx"},
        )
