from __future__ import annotations

from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from rag_maker.adapters.driven.loaders._utils import sha256_file
from rag_maker.domain.models import Document, LoadError


class EpubLoader:
    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() == ".epub"

    def load(self, path: Path) -> Document:
        try:
            book = epub.read_epub(str(path), options={"ignore_ncx": True})
        except Exception as e:
            raise LoadError(f"Erro ao abrir EPUB '{path}': {e}") from e

        parts: list[str] = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_content(), "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if text:
                parts.append(text)

        content = "\n\n".join(parts).strip()
        if not content:
            raise LoadError(f"'{path.name}' EPUB não contém texto extraível")

        return Document(
            path=path,
            content=content,
            content_hash=sha256_file(path),
            mtime=path.stat().st_mtime,
            metadata={"format": "epub"},
        )
