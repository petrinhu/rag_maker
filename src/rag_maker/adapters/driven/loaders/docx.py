# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import zipfile
from pathlib import Path

from docx import Document as DocxDocument

from rag_maker.adapters.driven.loaders._utils import (
    DEFAULT_MAX_COMPRESSION_RATIO,
    DEFAULT_MAX_EXTRACTED_CHARS,
    DEFAULT_MAX_FILE_MB,
    DEFAULT_MAX_UNCOMPRESSED_MB,
    check_extracted_size,
    check_file_size,
    check_zip_bomb,
    check_zip_bomb_streaming,
    sha256_file,
)
from rag_maker.domain.models import Document, LoadError


class DocxLoader:
    def __init__(
        self,
        *,
        max_file_mb: float = DEFAULT_MAX_FILE_MB,
        max_uncompressed_mb: float = DEFAULT_MAX_UNCOMPRESSED_MB,
        max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
        max_extracted_chars: int = DEFAULT_MAX_EXTRACTED_CHARS,
    ) -> None:
        self._max_file_mb = max_file_mb
        self._max_uncompressed_mb = max_uncompressed_mb
        self._max_compression_ratio = max_compression_ratio
        self._max_extracted_chars = max_extracted_chars

    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() == ".docx"

    def load(self, path: Path) -> Document:
        check_file_size(path, self._max_file_mb)

        # DOCX é um ZIP (Office Open XML). AUD-INPUT-2/AUD-TEST-3: checar a
        # razão de descompressão ANTES de deixar python-docx expandir o
        # conteúdo — python-docx não tem guard próprio contra zip bomb.
        # `check_zip_bomb` (metadado) é defesa em profundidade barata;
        # `check_zip_bomb_streaming` é a barreira AUTORITATIVA (mede bytes
        # REAIS via streaming, não confia em ZipInfo.file_size forjável).
        try:
            with zipfile.ZipFile(path) as zf:
                check_zip_bomb(
                    zf,
                    path,
                    max_uncompressed_mb=self._max_uncompressed_mb,
                    max_compression_ratio=self._max_compression_ratio,
                )
                check_zip_bomb_streaming(
                    zf,
                    path,
                    max_uncompressed_mb=self._max_uncompressed_mb,
                )
            doc = DocxDocument(str(path))
        except LoadError:
            raise
        except zipfile.BadZipFile as e:
            raise LoadError(f"'{path.name}' não é um DOCX válido (zip corrompido): {e}") from e
        except Exception as e:
            raise LoadError(f"Erro ao abrir DOCX '{path}': {e}") from e

        parts = [para.text for para in doc.paragraphs if para.text.strip()]
        content = "\n".join(parts).strip()
        if not content:
            raise LoadError(f"'{path.name}' não contém texto extraível")

        check_extracted_size(content, path, self._max_extracted_chars)

        return Document(
            path=path,
            content=content,
            content_hash=sha256_file(path),
            mtime=path.stat().st_mtime,
            metadata={"format": "docx"},
        )
