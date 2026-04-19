from __future__ import annotations

from pathlib import Path

import pytest

from rag_maker.adapters.driven.loaders import loader_for
from rag_maker.adapters.driven.loaders.docx import DocxLoader
from rag_maker.adapters.driven.loaders.epub import EpubLoader
from rag_maker.adapters.driven.loaders.pdf import PdfLoader
from rag_maker.adapters.driven.loaders.text import TextLoader
from rag_maker.domain.models import Document, LoadError

CORPUS = Path(__file__).parent.parent / "fixtures" / "corpus_mini"


@pytest.mark.integration
class TestTextLoader:
    def test_loads_txt(self) -> None:
        doc = TextLoader().load(CORPUS / "sample.txt")
        assert isinstance(doc, Document)
        assert "maçonaria" in doc.content.lower()
        assert doc.metadata["format"] == "txt"

    def test_loads_md(self) -> None:
        doc = TextLoader().load(CORPUS / "sample.md")
        assert "Hermes" in doc.content
        assert doc.metadata["format"] == "md"

    def test_can_load_txt(self) -> None:
        assert TextLoader().can_load(Path("x.txt")) is True

    def test_cannot_load_pdf(self) -> None:
        assert TextLoader().can_load(Path("x.pdf")) is False

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.txt"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(LoadError):
            TextLoader().load(empty)


@pytest.mark.integration
class TestDocxLoader:
    def test_loads_docx(self) -> None:
        doc = DocxLoader().load(CORPUS / "sample.docx")
        assert isinstance(doc, Document)
        assert len(doc.content) > 10
        assert doc.metadata["format"] == "docx"

    def test_can_load_docx(self) -> None:
        assert DocxLoader().can_load(Path("x.docx")) is True

    def test_cannot_load_txt(self) -> None:
        assert DocxLoader().can_load(Path("x.txt")) is False


@pytest.mark.integration
class TestEpubLoader:
    def test_loads_epub(self) -> None:
        doc = EpubLoader().load(CORPUS / "sample.epub")
        assert isinstance(doc, Document)
        assert "Rosacruz" in doc.content
        assert doc.metadata["format"] == "epub"

    def test_can_load_epub(self) -> None:
        assert EpubLoader().can_load(Path("x.epub")) is True


@pytest.mark.integration
class TestPdfLoader:
    def test_loads_pdf(self) -> None:
        doc = PdfLoader().load(CORPUS / "sample.pdf")
        assert isinstance(doc, Document)
        assert len(doc.content) > 0

    def test_can_load_pdf(self) -> None:
        assert PdfLoader().can_load(Path("x.pdf")) is True


@pytest.mark.integration
class TestRegistry:
    def test_loader_for_txt(self) -> None:
        loader = loader_for(CORPUS / "sample.txt")
        assert isinstance(loader, TextLoader)

    def test_loader_for_md(self) -> None:
        loader = loader_for(CORPUS / "sample.md")
        assert isinstance(loader, TextLoader)

    def test_loader_for_docx(self) -> None:
        loader = loader_for(CORPUS / "sample.docx")
        assert isinstance(loader, DocxLoader)

    def test_loader_for_epub(self) -> None:
        loader = loader_for(CORPUS / "sample.epub")
        assert isinstance(loader, EpubLoader)

    def test_loader_for_pdf(self) -> None:
        loader = loader_for(CORPUS / "sample.pdf")
        assert isinstance(loader, PdfLoader)

    def test_unsupported_raises(self) -> None:
        with pytest.raises(LoadError):
            loader_for(Path("file.xyz"))
