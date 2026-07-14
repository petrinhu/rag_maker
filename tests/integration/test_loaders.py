from __future__ import annotations

import os
import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from rag_maker.adapters.driven.loaders import loader_for
from rag_maker.adapters.driven.loaders.docx import DocxLoader
from rag_maker.adapters.driven.loaders.epub import EpubLoader
from rag_maker.adapters.driven.loaders.pdf import PdfLoader
from rag_maker.adapters.driven.loaders.text import TextLoader
from rag_maker.domain.models import Document, LoadError

CORPUS = Path(__file__).parent.parent / "fixtures" / "corpus_mini"


def _make_zip_bomb(path: Path, *, inner_size: int, entry_name: str = "word/document.xml") -> None:
    """Zip pequeno em disco cujo conteúdo descomprime MUITO (bytes repetidos
    comprimem com razão altíssima via DEFLATE) — não precisa ser um DOCX/EPUB
    estruturalmente válido: o guard de zip bomb roda ANTES do parser real
    (python-docx/ebooklib) tentar interpretar o conteúdo."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr(entry_name, "0" * inner_size)


def _make_forged_zip_bomb(
    path: Path,
    *,
    real_size: int,
    declared_size: int,
    entry_name: str = "word/document.xml",
) -> None:
    """Monta um ZIP byte-a-byte (SEM usar `zipfile.ZipFile.writestr`, que
    sempre recalcula `file_size` honestamente a partir do conteúdo real —
    não dá pra forjar por ali) onde o CENTRAL DIRECTORY declara um
    `file_size` (uncompressed size) pequeno e forjado, mas o payload deflate
    REAL descomprime para `real_size` bytes. `compress_size` fica HONESTO
    (reflete o payload real) — precisa estar correto para o arquivo ser um
    ZIP fisicamente válido e legível por `zipfile`.

    Simula um atacante que forja o metadado do ZIP especificamente para
    escapar de um guard que confia em `ZipInfo.file_size`/`compress_size`
    (a vulnerabilidade que `check_zip_bomb_streaming` fecha)."""
    payload = b"0" * real_size
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
    compressed = compressor.compress(payload) + compressor.flush()
    name_bytes = entry_name.encode("utf-8")
    crc = zlib.crc32(payload) & 0xFFFFFFFF

    local_header = struct.pack(
        "<4s5H3I2H",
        b"PK\x03\x04",
        20,
        0,
        8,
        0,
        0,
        crc,
        len(compressed),
        real_size,
        len(name_bytes),
        0,
    )
    local_record = local_header + name_bytes + compressed

    central_header = struct.pack(
        "<4s6H3I5H2I",
        b"PK\x01\x02",
        20,
        20,
        0,
        8,
        0,
        0,
        crc,
        len(compressed),
        declared_size,  # <- FORJADO: uncompressed size mentiroso
        len(name_bytes),
        0,
        0,
        0,
        0,
        0o600 << 16,
        0,
    )
    central_record = central_header + name_bytes

    eocd = struct.pack(
        "<4s4H2IH",
        b"PK\x05\x06",
        0,
        0,
        1,
        1,
        len(central_record),
        len(local_record),
        0,
    )

    path.write_bytes(local_record + central_record + eocd)


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


@pytest.mark.integration
class TestFileSizeGuard:
    """AUD-INPUT-2: teto de tamanho em disco, verificado ANTES de qualquer parsing."""

    def test_pdf_oversized_raises_before_parsing(self) -> None:
        # sample.pdf tem ~810 bytes; um teto absurdamente baixo garante que o
        # guard dispara mesmo sem escrever um arquivo grande no disco.
        with pytest.raises(LoadError, match="excede o tamanho máximo"):
            PdfLoader(max_file_mb=1e-6).load(CORPUS / "sample.pdf")

    def test_docx_oversized_raises(self) -> None:
        with pytest.raises(LoadError, match="excede o tamanho máximo"):
            DocxLoader(max_file_mb=1e-6).load(CORPUS / "sample.docx")

    def test_epub_oversized_raises(self) -> None:
        with pytest.raises(LoadError, match="excede o tamanho máximo"):
            EpubLoader(max_file_mb=1e-6).load(CORPUS / "sample.epub")

    def test_text_oversized_raises(self) -> None:
        with pytest.raises(LoadError, match="excede o tamanho máximo"):
            TextLoader(max_file_mb=1e-6).load(CORPUS / "sample.txt")

    def test_within_limit_still_loads(self) -> None:
        # Confirma que o guard não é falso-positivo com o teto default.
        doc = PdfLoader().load(CORPUS / "sample.pdf")
        assert isinstance(doc, Document)


@pytest.mark.integration
class TestZipBombGuard:
    """AUD-INPUT-2/AUD-TEST-3/AUD-TEST-3b: guard de descompressão em ZIP-based
    loaders (DOCX/EPUB), com fixtures pequenas e controladas."""

    def test_docx_bomb_raises_before_oom(self, tmp_path: Path) -> None:
        # 10 MB de bytes repetidos comprime para poucos KB (razão >100x
        # default) — dispara o guard SEM jamais materializar o conteúdo
        # descomprimido em memória.
        bomb = tmp_path / "bomb.docx"
        _make_zip_bomb(bomb, inner_size=10_000_000)
        with pytest.raises(LoadError, match="zip bomb"):
            DocxLoader().load(bomb)

    def test_epub_bomb_raises_before_oom(self, tmp_path: Path) -> None:
        bomb = tmp_path / "bomb.epub"
        _make_zip_bomb(bomb, inner_size=10_000_000, entry_name="OEBPS/content.xhtml")
        with pytest.raises(LoadError, match="zip bomb"):
            EpubLoader().load(bomb)

    def test_docx_total_uncompressed_cap_triggers_without_extreme_ratio(
        self, tmp_path: Path
    ) -> None:
        # Conteúdo com razão de compressão BAIXA (texto quase incompressível),
        # mas volume total acima de um teto customizado baixo: cobre o
        # branch "OR" do guard (soma total), não só a razão por entrada.
        low_ratio_bytes = os.urandom(2_000_000)  # ~1:1, não achata via DEFLATE
        target = tmp_path / "big_low_ratio.docx"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("word/document.xml", low_ratio_bytes)
        with pytest.raises(LoadError, match="zip bomb"):
            DocxLoader(max_uncompressed_mb=1.0, max_compression_ratio=1000.0).load(target)

    def test_docx_corrupted_zip_raises_load_error(self, tmp_path: Path) -> None:
        corrupted = tmp_path / "corrupted.docx"
        corrupted.write_bytes(b"not a real zip file at all")
        with pytest.raises(LoadError, match="não é um DOCX válido"):
            DocxLoader().load(corrupted)

    def test_epub_corrupted_zip_raises_load_error(self, tmp_path: Path) -> None:
        corrupted = tmp_path / "corrupted.epub"
        corrupted.write_bytes(b"not a real zip file at all")
        with pytest.raises(LoadError, match="não é um EPUB válido"):
            EpubLoader().load(corrupted)

    def test_legit_docx_still_loads(self) -> None:
        doc = DocxLoader().load(CORPUS / "sample.docx")
        assert isinstance(doc, Document)

    def test_legit_epub_still_loads(self) -> None:
        doc = EpubLoader().load(CORPUS / "sample.epub")
        assert isinstance(doc, Document)


@pytest.mark.integration
class TestZipBombForgedMetadataGuard:
    """FURO fechado (revisão adversarial): `ZipInfo.file_size`/`compress_size`
    são metadados do central directory FORJÁVEIS por quem monta o ZIP.
    `check_zip_bomb` (baseada nesses campos) sozinha NÃO detecta um ataque
    que declara `file_size` pequeno mas mantém um payload deflate REAL
    gigante — só `check_zip_bomb_streaming` (mede bytes REAIS via streaming
    com teto por bloco) fecha esse furo. Estes testes provam que (1) o
    metadado forjado passaria pelo guard antigo isolado, e (2) o loader
    completo (com o novo guard em série) recusa e não estoura memória."""

    def test_docx_forged_small_declared_size_raises_before_oom(self, tmp_path: Path) -> None:
        bomb = tmp_path / "forged.docx"
        # 5 MB de zeros reais comprimem para ~5 KB (ratio ~1000x), mas o
        # central directory declara file_size=100 — a razão calculada sobre
        # o metadado (100 / ~5000) fica bem abaixo de qualquer teto
        # plausível, então SÓ a medição real via streaming detecta.
        _make_forged_zip_bomb(bomb, real_size=5_000_000, declared_size=100)
        with pytest.raises(LoadError, match="descomprime"):
            DocxLoader(max_uncompressed_mb=1.0).load(bomb)

    def test_epub_forged_small_declared_size_raises_before_oom(self, tmp_path: Path) -> None:
        bomb = tmp_path / "forged.epub"
        _make_forged_zip_bomb(
            bomb, real_size=5_000_000, declared_size=100, entry_name="OEBPS/content.xhtml"
        )
        with pytest.raises(LoadError, match="descomprime"):
            EpubLoader(max_uncompressed_mb=1.0).load(bomb)

    def test_forged_declared_size_would_bypass_metadata_only_check(self, tmp_path: Path) -> None:
        # Prova isolada de QUE o guard antigo (baseado só em metadado)
        # sozinho não pegaria este arquivo: soma de file_size declarado
        # (100 bytes) e razão declarada (100 / compress_size real) ficam
        # ambas sob qualquer teto plausível.
        from rag_maker.adapters.driven.loaders._utils import check_zip_bomb

        bomb = tmp_path / "forged_metadata_only.docx"
        _make_forged_zip_bomb(bomb, real_size=5_000_000, declared_size=100)
        with zipfile.ZipFile(bomb) as zf:
            check_zip_bomb(
                zf, bomb, max_uncompressed_mb=1.0, max_compression_ratio=100.0
            )  # não levanta — confirma o furo do guard baseado em metadado


@pytest.mark.integration
class TestPdfCorruptedRaisesCleanly:
    """AUD-INPUT-1: laço de extração de páginas também precisa virar LoadError."""

    def test_truncated_pdf_raises_load_error(self, tmp_path: Path) -> None:
        truncated = tmp_path / "truncated.pdf"
        truncated.write_bytes(b"%PDF-1.4\ngarbage, not a real pdf structure")
        with pytest.raises(LoadError):
            PdfLoader().load(truncated)


@pytest.mark.integration
class TestPdfFailFastMidLoop:
    """F12.30: prova que `running_chars` aborta DURANTE o laço de páginas
    (fail-fast por página) e não apenas na checagem pós-join
    (`check_extracted_size`). Sem este teste, um regressor poderia mover a
    checagem de volta para depois do `"\\n".join(pages_text)` — todos os
    outros testes de PDF continuariam verdes (a exceção ainda seria
    levantada, só que tarde demais, depois de extrair TODAS as páginas)."""

    def test_running_chars_aborts_before_extracting_all_pages(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        call_count = [0]
        page_text = "x" * 100  # cada página soma 100 chars ao acumulador
        n_pages = 10
        expected_calls_before_abort = 3  # 100+100+100=300 > max_extracted_chars

        class _FakePage:
            def extract_text(self) -> str:
                call_count[0] += 1
                return page_text

        class _FakeReader:
            def __init__(self, *_args: object, **_kwargs: object) -> None:
                self.pages = [_FakePage() for _ in range(n_pages)]

        monkeypatch.setattr("rag_maker.adapters.driven.loaders.pdf.PdfReader", _FakeReader)

        dummy = tmp_path / "fake_multi_page.pdf"
        dummy.write_bytes(b"%PDF-1.4\n%fake bytes, reader is mocked\n")

        # limite estoura na 3ª página (100 -> 200 -> 300 > 250), bem antes
        # das 10 páginas do PDF sintético.
        max_chars = 250
        with pytest.raises(LoadError, match="acima do limite"):
            PdfLoader(max_extracted_chars=max_chars).load(dummy)

        # (a) exceção correta do domínio já verificada por pytest.raises
        # acima. (b) prova de fail-fast: extract_text foi chamado
        # EXATAMENTE até a página que estourou o teto, nunca as 10 páginas
        # inteiras — se o loader extraísse tudo antes de checar (checagem
        # só pós-join), call_count seria 10.
        assert call_count[0] == expected_calls_before_abort
        assert call_count[0] < n_pages


@pytest.mark.integration
class TestTextBinaryGuard:
    """AUD-INPUT-3: binário disfarçado de .txt/.md deve ser recusado, não
    silenciosamente decodificado via fallback latin-1/cp1252 cego."""

    def test_null_byte_binary_raises(self, tmp_path: Path) -> None:
        fake_txt = tmp_path / "fake.txt"
        fake_txt.write_bytes(b"\x00\x01\x02PNG-like-binary-garbage\x00\x00\x00")
        with pytest.raises(LoadError, match="binário"):
            TextLoader().load(fake_txt)

    def test_high_control_byte_ratio_raises(self, tmp_path: Path) -> None:
        fake_txt = tmp_path / "fake2.txt"
        # Sem byte nulo, mas maioria dos bytes são de controle não-textual.
        fake_txt.write_bytes(bytes(range(1, 9)) * 200)
        with pytest.raises(LoadError, match="binário"):
            TextLoader().load(fake_txt)

    def test_legit_utf8_still_loads(self) -> None:
        doc = TextLoader().load(CORPUS / "sample.txt")
        assert isinstance(doc, Document)

    def test_legit_latin1_text_still_loads(self, tmp_path: Path) -> None:
        latin1_txt = tmp_path / "latin1.txt"
        # 'ção' em latin-1 (não é utf-8 válido), mas é texto plausível de
        # verdade — deve continuar caindo no fallback controlado, não ser
        # rejeitado como binário.
        latin1_txt.write_bytes("Sessão de estudo, informação relevante.".encode("latin-1"))
        doc = TextLoader().load(latin1_txt)
        assert "Sess" in doc.content


@pytest.mark.integration
class TestExtractedTextSizeGuard:
    """Teto no total de texto extraído (defesa em profundidade)."""

    def test_text_loader_rejects_over_extracted_cap(self, tmp_path: Path) -> None:
        big = tmp_path / "big.txt"
        big.write_text("word " * 100, encoding="utf-8")
        with pytest.raises(LoadError, match="texto extraído"):
            TextLoader(max_extracted_chars=10).load(big)
