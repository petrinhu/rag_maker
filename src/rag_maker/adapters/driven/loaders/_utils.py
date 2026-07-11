from __future__ import annotations

import copy
import hashlib
import zipfile
from pathlib import Path

from rag_maker.domain.models import LoadError

# Defaults efetivos deste adapter. Duplicados intencionalmente (não importados
# de application/config.py): domain/application não pode ser acoplado a
# valores de adapters/driven, e application/ não pode ser importado por
# adapters/ (regra hexagonal). `AppConfig.loaders` documenta a mesma
# superfície para wiring futuro via composition/container; até lá, estes
# defaults protegem o adapter mesmo sem injeção externa.
DEFAULT_MAX_FILE_MB = 100.0
DEFAULT_MAX_UNCOMPRESSED_MB = 500.0
DEFAULT_MAX_COMPRESSION_RATIO = 100.0
DEFAULT_MAX_EXTRACTED_CHARS = 20_000_000

_BYTES_PER_MB = 1024 * 1024

# Tamanho do bloco de streaming em `check_zip_bomb_streaming`. É o teto de
# memória do pré-scan por chamada de decompressão (ver docstring da função).
_STREAM_BLOCK_BYTES = 65536

# Sentinel usado para SUBSTITUIR o `file_size` declarado (forjável) de cada
# entrada antes de abri-la para streaming. Precisa ser maior que qualquer
# `max_uncompressed_mb` configurável em prática, para que `ZipExtFile` nunca
# trunque a leitura por esse campo — o EOF do streaming deve vir do fim
# GENUÍNO do stream comprimido, nunca do metadado.
_UNBOUNDED_FILE_SIZE_SENTINEL = 2**62


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_file_size(path: Path, max_file_mb: float) -> None:
    """Recusa arquivos maiores que o teto ANTES de qualquer parsing (fail-fast).

    Invariante protegido: nenhum loader abre/parseia um arquivo cujo tamanho
    em disco já é conhecido como excessivo — evita alocação de memória
    proporcional a um arquivo gigante antes mesmo de checar seu conteúdo.
    """
    size_mb = path.stat().st_size / _BYTES_PER_MB
    if size_mb > max_file_mb:
        raise LoadError(
            f"'{path.name}' excede o tamanho máximo de arquivo permitido "
            f"({size_mb:.1f} MB > {max_file_mb:.1f} MB)"
        )


def check_zip_bomb(
    zf: zipfile.ZipFile,
    path: Path,
    *,
    max_uncompressed_mb: float,
    max_compression_ratio: float,
) -> None:
    """Guard contra decompression bomb em containers ZIP (DOCX/EPUB).

    Invariante protegido: nenhuma extração de ZIP por este loader pode expandir
    para uma quantidade de memória sem limite superior conhecido. NÃO confia no
    tamanho comprimido em disco (já validado por `check_file_size`); soma o
    tamanho DESCOMPRIMIDO declarado (`ZipInfo.file_size`) de cada entrada e
    recusa assim que o acumulado excede o teto absoluto, OU assim que uma
    única entrada exibe razão de compressão implausível (assinatura clássica
    de zip bomb: poucos KB comprimidos expandindo para GBs).
    """
    max_uncompressed_bytes = max_uncompressed_mb * _BYTES_PER_MB
    total_uncompressed = 0
    for info in zf.infolist():
        total_uncompressed += info.file_size
        if total_uncompressed > max_uncompressed_bytes:
            raise LoadError(
                f"'{path.name}' recusado: conteúdo descomprimido do ZIP excede "
                f"{max_uncompressed_mb:.0f} MB (possível zip bomb)"
            )
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > max_compression_ratio:
                raise LoadError(
                    f"'{path.name}' recusado: entrada '{info.filename}' do ZIP tem "
                    f"razão de compressão {ratio:.0f}x (teto {max_compression_ratio:.0f}x, "
                    "possível zip bomb)"
                )


def check_zip_bomb_streaming(
    zf: zipfile.ZipFile,
    path: Path,
    *,
    max_uncompressed_mb: float,
) -> None:
    """Guard AUTORITATIVO contra zip bomb: mede a descompressão REAL de cada
    entrada via streaming, com teto de memória por bloco. Complementa (não
    substitui) `check_zip_bomb`.

    Por que `check_zip_bomb` (baseada em `ZipInfo.file_size`/`compress_size`)
    NÃO basta como única barreira: esses campos vêm do central directory do
    ZIP e são metadados FORJÁVEIS por quem monta o arquivo — nada nos exige
    que reflitam o tamanho real do stream deflate. Pior: quando uma lib como
    python-docx/ebooklib chama `zf.read(name)` (leitura SEM tamanho
    explícito), `zipfile.ZipExtFile._read1` propaga um `max_length`
    efetivamente ilimitado (`self.MAX_N`) para `decompressor.decompress(...)`
    — o payload REAL inteiro é decomprimido em memória ANTES de
    `data[:self._left]` truncar pelo `file_size` declarado. Um `file_size`
    pequeno forjado não evita o pico de memória; só engana quem confia no
    metadado (como a versão anterior deste guard).

    Mitigação, em duas partes:
    1. Abrimos a entrada via `zf.open()` passando uma CÓPIA do `ZipInfo` cujo
       `file_size` foi elevado a um sentinel bem acima de qualquer teto
       configurável. Isso impede que `ZipExtFile` sinalize EOF prematuro por
       causa do metadado forjado — o EOF real só vem do fim genuíno do
       stream comprimido (fim do deflate ou exaustão de `compress_size`,
       este sim usado para limitar quantos bytes crus são lidos do disco).
    2. Lemos em blocos de tamanho FIXO e EXPLÍCITO (`entry.read(n)`, nunca
       `entry.read()`/`entry.read(-1)`), o que limita o `max_length`
       repassado à chamada interna de `zlib.decompressobj.decompress()` a
       esse bloco — cada chamada produz no máximo `_STREAM_BLOCK_BYTES` de
       saída, e descartamos o bloco imediatamente após somar seu tamanho a
       um contador corrente. Assim que o contador (acumulado por TODAS as
       entradas, mesma semântica de `check_zip_bomb`) ultrapassa o teto,
       abortamos com `LoadError` sem jamais reter o conteúdo descomprimido.

    Invariante protegido: o pico de memória deste pré-scan é ~O(tamanho do
    bloco), independente do que o metadado do ZIP declara e independente do
    tamanho real da bomba — a decisão de aceitar/recusar é feita sobre bytes
    REALMENTE produzidos pelo decompressor, nunca sobre um valor que o
    atacante controla.
    """
    max_uncompressed_bytes = int(max_uncompressed_mb * _BYTES_PER_MB)
    total_uncompressed = 0
    for info in zf.infolist():
        probe = copy.copy(info)
        probe.file_size = _UNBOUNDED_FILE_SIZE_SENTINEL
        with zf.open(probe) as entry:
            while True:
                block = entry.read(_STREAM_BLOCK_BYTES)
                if not block:
                    break
                total_uncompressed += len(block)
                if total_uncompressed > max_uncompressed_bytes:
                    raise LoadError(
                        f"'{path.name}' recusado: entrada '{info.filename}' do ZIP "
                        f"descomprime (medição real via streaming) acima de "
                        f"{max_uncompressed_mb:.0f} MB — possível zip bomb com "
                        "metadado de tamanho forjado"
                    )


def check_extracted_size(content: str, path: Path, max_extracted_chars: int) -> None:
    """Teto no total de texto extraído, independente da origem (defesa em
    profundidade complementar a `check_zip_bomb`/`check_file_size`)."""
    if len(content) > max_extracted_chars:
        raise LoadError(
            f"'{path.name}' produziu texto extraído acima do limite "
            f"({len(content)} > {max_extracted_chars} caracteres)"
        )
