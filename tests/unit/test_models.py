from __future__ import annotations

from pathlib import Path

import pytest

from rag_maker.domain.models import (
    Chunk,
    DimensionMismatchError,
    Document,
    EmbeddingError,
    IndexedChunk,
    LoadError,
    ModelNotFoundError,
    OllamaUnavailableError,
    QueryResult,
)


@pytest.mark.unit
class TestDocument:
    def test_frozen(self) -> None:
        doc = Document(path=Path("a.txt"), content="x", content_hash="abc", mtime=0.0)
        with pytest.raises((AttributeError, TypeError)):
            doc.path = Path("b.txt")  # type: ignore[misc]

    def test_equality(self) -> None:
        doc1 = Document(path=Path("a.txt"), content="x", content_hash="abc", mtime=1.0)
        doc2 = Document(path=Path("a.txt"), content="x", content_hash="abc", mtime=1.0)
        assert doc1 == doc2

    def test_metadata_excluded_from_equality(self) -> None:
        doc1 = Document(
            path=Path("a.txt"), content="x", content_hash="abc", mtime=1.0, metadata={"k": "1"}
        )
        doc2 = Document(
            path=Path("a.txt"), content="x", content_hash="abc", mtime=1.0, metadata={"k": "2"}
        )
        assert doc1 == doc2

    def test_default_metadata_empty(self) -> None:
        doc = Document(path=Path("a.txt"), content="x", content_hash="abc", mtime=0.0)
        assert doc.metadata == {}


@pytest.mark.unit
class TestChunk:
    def _make(self) -> Chunk:
        return Chunk(
            chunk_id="id1",
            document_path=Path("a.txt"),
            content="hello",
            char_offset=0,
            mtime=1.0,
        )

    def test_frozen(self) -> None:
        c = self._make()
        with pytest.raises((AttributeError, TypeError)):
            c.content = "x"  # type: ignore[misc]

    def test_optional_fields_default_none(self) -> None:
        c = self._make()
        assert c.page is None
        assert c.section is None

    def test_hashable(self) -> None:
        c = self._make()
        assert hash(c) is not None
        s = {c}  # deve ser usavel como key de set
        assert c in s


@pytest.mark.unit
class TestIndexedChunk:
    def test_vector_is_tuple(self) -> None:
        chunk = Chunk(chunk_id="x", document_path=Path("a"), content="hi", char_offset=0, mtime=0.0)
        ic = IndexedChunk(chunk=chunk, vector=(0.1, 0.2, 0.3))
        assert isinstance(ic.vector, tuple)

    def test_frozen(self) -> None:
        chunk = Chunk(chunk_id="x", document_path=Path("a"), content="hi", char_offset=0, mtime=0.0)
        ic = IndexedChunk(chunk=chunk, vector=(0.1,))
        with pytest.raises((AttributeError, TypeError)):
            ic.vector = (0.2,)  # type: ignore[misc]


@pytest.mark.unit
class TestQueryResult:
    def test_empty_chunks(self) -> None:
        qr = QueryResult(query="test", ranked_chunks=(), latency_ms=10.0)
        assert len(qr.ranked_chunks) == 0
        assert qr.latency_ms == 10.0


@pytest.mark.unit
class TestExceptions:
    def test_dimension_mismatch_is_embedding_error(self) -> None:
        err = DimensionMismatchError("expected 1024, got 512")
        assert isinstance(err, EmbeddingError)

    def test_hierarchy(self) -> None:
        assert issubclass(DimensionMismatchError, EmbeddingError)
        assert issubclass(EmbeddingError, Exception)
        assert issubclass(OllamaUnavailableError, Exception)
        assert issubclass(ModelNotFoundError, Exception)
        assert issubclass(LoadError, Exception)

    def test_can_raise_and_catch(self) -> None:
        with pytest.raises(EmbeddingError):
            raise DimensionMismatchError("dim mismatch")

        with pytest.raises(LoadError):
            raise LoadError("bad file")
