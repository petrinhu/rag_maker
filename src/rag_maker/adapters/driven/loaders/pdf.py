# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import warnings
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfReadWarning

from rag_maker.adapters.driven.loaders._utils import (
    DEFAULT_MAX_EXTRACTED_CHARS,
    DEFAULT_MAX_FILE_MB,
    check_extracted_size,
    check_file_size,
    sha256_file,
)
from rag_maker.domain.models import Document, LoadError

_MIN_CHARS_PER_PAGE = 50


class PdfLoader:
    def __init__(
        self,
        *,
        max_file_mb: float = DEFAULT_MAX_FILE_MB,
        max_extracted_chars: int = DEFAULT_MAX_EXTRACTED_CHARS,
    ) -> None:
        self._max_file_mb = max_file_mb
        self._max_extracted_chars = max_extracted_chars

    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def load(self, path: Path) -> Document:
        check_file_size(path, self._max_file_mb)

        # AUD-INPUT-1: abertura E extração de páginas ficam no MESMO bloco
        # try — o pypdf pode lançar exceções durante extract_text() (não só
        # ao abrir), e todas devem virar LoadError (fail-clean), nunca
        # escapar cruas para o chamador (viola o contrato do LoaderPort).
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", PdfReadWarning)
                reader = PdfReader(str(path))
            # Checagem CORRENTE dentro do laço (fail-fast por página): um PDF
            # com milhares de páginas de texto não pode acumular o `content`
            # inteiro em memória antes de sabermos que vai estourar o teto.
            # `check_extracted_size` após o laço (abaixo) permanece como
            # defesa em profundidade, cobrindo o overhead dos separadores
            # "\n" inseridos pelo join.
            pages_text: list[str] = []
            running_chars = 0
            for page in reader.pages:
                text = page.extract_text() or ""
                running_chars += len(text)
                if running_chars > self._max_extracted_chars:
                    raise LoadError(
                        f"'{path.name}' produziu texto extraído acima do limite "
                        f"({running_chars} > {self._max_extracted_chars} caracteres, "
                        "abortado durante extração de páginas)"
                    )
                pages_text.append(text)
            content = "\n".join(pages_text).strip()
            page_count = len(reader.pages)
        except PdfReadError as e:
            raise LoadError(f"Erro ao abrir PDF '{path}': {e}") from e
        except LoadError:
            raise
        except Exception as e:
            raise LoadError(f"Erro ao extrair texto do PDF '{path}': {e}") from e

        if not content or _is_image_pdf(pages_text):
            raise LoadError(f"'{path.name}' parece ser PDF de imagem sem texto extraível")

        check_extracted_size(content, path, self._max_extracted_chars)

        return Document(
            path=path,
            content=content,
            content_hash=sha256_file(path),
            mtime=path.stat().st_mtime,
            metadata={"page_count": str(page_count), "format": "pdf"},
        )


def _is_image_pdf(pages_text: list[str]) -> bool:
    if not pages_text:
        return False
    avg = sum(len(t) for t in pages_text) / len(pages_text)
    return avg < _MIN_CHARS_PER_PAGE
