# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from rag_maker.adapters.driven.loaders.docx import DocxLoader
from rag_maker.adapters.driven.loaders.epub import EpubLoader
from rag_maker.adapters.driven.loaders.pdf import PdfLoader
from rag_maker.adapters.driven.loaders.text import TextLoader
from rag_maker.domain.models import LoadError
from rag_maker.domain.ports.loader import LoaderPort

_LOADERS: list[LoaderPort] = [
    PdfLoader(),
    DocxLoader(),
    EpubLoader(),
    TextLoader(),
]


def loader_for(path: Path) -> LoaderPort:
    """Retorna o loader adequado para o arquivo dado ou levanta LoadError."""
    for loader in _LOADERS:
        if loader.can_load(path):
            return loader
    raise LoadError(
        f"Formato não suportado: '{path.suffix}'. "
        "Suportados: .pdf, .docx, .epub, .txt, .md, .markdown"
    )
