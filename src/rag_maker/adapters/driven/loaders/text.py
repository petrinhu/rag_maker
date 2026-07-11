from __future__ import annotations

from pathlib import Path

from rag_maker.adapters.driven.loaders._utils import (
    DEFAULT_MAX_EXTRACTED_CHARS,
    DEFAULT_MAX_FILE_MB,
    check_extracted_size,
    check_file_size,
    sha256_file,
)
from rag_maker.domain.models import Document, LoadError

_SUPPORTED = {".txt", ".md", ".markdown"}
_FALLBACK_ENCODINGS = ("utf-8-sig", "latin-1", "cp1252")

_BINARY_SNIFF_BYTES = 8192
_MAX_CONTROL_BYTE_RATIO = 0.30
# Bytes de controle aceitos em texto plausível: tab, LF, CR. Qualquer outro
# byte < 0x20 conta para o heurístico de "parece binário".
_ALLOWED_CONTROL_BYTES = frozenset({0x09, 0x0A, 0x0D})


class TextLoader:
    def __init__(
        self,
        *,
        max_file_mb: float = DEFAULT_MAX_FILE_MB,
        max_extracted_chars: int = DEFAULT_MAX_EXTRACTED_CHARS,
    ) -> None:
        self._max_file_mb = max_file_mb
        self._max_extracted_chars = max_extracted_chars

    def can_load(self, path: Path) -> bool:
        return path.suffix.lower() in _SUPPORTED

    def load(self, path: Path) -> Document:
        check_file_size(path, self._max_file_mb)

        raw = path.read_bytes()
        _reject_if_binary(raw, path)
        content = _decode(raw, path)

        if not content.strip():
            raise LoadError(f"'{path.name}' está vazio")

        check_extracted_size(content, path, self._max_extracted_chars)

        return Document(
            path=path,
            content=content,
            content_hash=sha256_file(path),
            mtime=path.stat().st_mtime,
            metadata={"format": path.suffix.lstrip(".")},
        )


def _reject_if_binary(raw: bytes, path: Path) -> None:
    """AUD-INPUT-3: detecta binário disfarçado de .txt/.md ANTES de decodificar.

    Sem isso, o fallback latin-1/cp1252 nunca falha (mapeia qualquer byte),
    tornando o branch de erro morto e deixando lixo binário ser indexado
    silenciosamente. Heurística: byte nulo (assinatura clássica de binário
    como PNG/ELF/ZIP) OU proporção alta de bytes de controle não-textuais
    numa amostra do arquivo.
    """
    sample = raw[:_BINARY_SNIFF_BYTES]
    if not sample:
        return

    if b"\x00" in sample:
        raise LoadError(f"'{path.name}' parece ser binário (byte nulo detectado), recusado")

    control_bytes = sum(1 for b in sample if b < 0x20 and b not in _ALLOWED_CONTROL_BYTES)
    ratio = control_bytes / len(sample)
    if ratio > _MAX_CONTROL_BYTE_RATIO:
        raise LoadError(
            f"'{path.name}' parece ser binário "
            f"({ratio:.0%} de bytes de controle não-textuais na amostra), recusado"
        )


def _decode(raw: bytes, path: Path) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in _FALLBACK_ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise LoadError(
        f"'{path.name}' não pôde ser decodificado (tentadas: utf-8, {_FALLBACK_ENCODINGS})"
    )
