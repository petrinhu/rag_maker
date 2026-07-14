# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import hashlib
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag_maker.domain.models import Chunk, Document


class RecursiveCharacterChunker:
    def __init__(self, size: int = 1000, overlap: int = 200) -> None:
        if overlap >= size:
            raise ValueError(f"overlap ({overlap}) must be less than size ({size})")
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=size,
            chunk_overlap=overlap,
            add_start_index=True,
        )

    def chunk(self, doc: Document) -> list[Chunk]:
        lc_docs = self._splitter.create_documents([doc.content])
        chunks: list[Chunk] = []
        for lc_doc in lc_docs:
            offset: int = lc_doc.metadata.get("start_index", 0)
            chunk_id = _make_chunk_id(doc.path, offset)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_path=doc.path,
                    content=lc_doc.page_content,
                    char_offset=offset,
                    mtime=doc.mtime,
                    page=None,
                    section=None,
                )
            )
        return chunks


def _make_chunk_id(path: Path, offset: int) -> str:
    raw = f"{path}:{offset}".encode()
    return hashlib.sha256(raw).hexdigest()[:24]
