from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from rag_maker.domain.chunker import RecursiveCharacterChunker
from rag_maker.domain.models import Document


def _make_doc(content: str) -> Document:
    return Document(path=Path("test.txt"), content=content, content_hash="x", mtime=0.0)


@pytest.mark.unit
class TestRecursiveCharacterChunker:
    def test_invalid_overlap_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            RecursiveCharacterChunker(size=100, overlap=100)

    def test_empty_content_returns_empty(self) -> None:
        chunker = RecursiveCharacterChunker(size=200, overlap=50)
        chunks = chunker.chunk(_make_doc(""))
        assert chunks == []

    def test_short_content_single_chunk(self) -> None:
        chunker = RecursiveCharacterChunker(size=500, overlap=50)
        chunks = chunker.chunk(_make_doc("hello world"))
        assert len(chunks) == 1
        assert chunks[0].content == "hello world"

    def test_chunk_ids_are_unique(self) -> None:
        chunker = RecursiveCharacterChunker(size=100, overlap=20)
        content = "word " * 200
        chunks = chunker.chunk(_make_doc(content))
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_offsets_non_decreasing(self) -> None:
        chunker = RecursiveCharacterChunker(size=100, overlap=20)
        content = "a" * 1000
        chunks = chunker.chunk(_make_doc(content))
        offsets = [c.char_offset for c in chunks]
        assert offsets == sorted(offsets)

    def test_document_path_preserved(self) -> None:
        chunker = RecursiveCharacterChunker(size=200, overlap=50)
        path = Path("my/doc.txt")
        doc = Document(path=path, content="x" * 300, content_hash="h", mtime=1.0)
        chunks = chunker.chunk(doc)
        assert all(c.document_path == path for c in chunks)

    def test_mtime_preserved(self) -> None:
        chunker = RecursiveCharacterChunker(size=200, overlap=50)
        doc = Document(path=Path("a.txt"), content="x" * 300, content_hash="h", mtime=9999.0)
        chunks = chunker.chunk(doc)
        assert all(c.mtime == 9999.0 for c in chunks)


@pytest.mark.unit
@settings(max_examples=50)
@given(
    content=st.text(min_size=0, max_size=3000),
    size=st.integers(min_value=50, max_value=500),
    overlap_pct=st.integers(min_value=0, max_value=40),
)
def test_chunker_offsets_ordered_hypothesis(content: str, size: int, overlap_pct: int) -> None:
    overlap = int(size * overlap_pct / 100)
    assume(overlap < size)
    chunker = RecursiveCharacterChunker(size=size, overlap=overlap)
    chunks = chunker.chunk(_make_doc(content))
    offsets = [c.char_offset for c in chunks]
    assert offsets == sorted(offsets), "char_offset deve ser crescente"


@pytest.mark.unit
@settings(max_examples=30)
@given(
    content=st.text(min_size=1, max_size=3000),
    size=st.integers(min_value=50, max_value=500),
)
def test_chunker_chunks_not_empty_hypothesis(content: str, size: int) -> None:
    chunker = RecursiveCharacterChunker(size=size, overlap=0)
    chunks = chunker.chunk(_make_doc(content))
    assert all(c.content for c in chunks), "nenhum chunk deve ter conteúdo vazio"
