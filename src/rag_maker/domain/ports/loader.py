from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from rag_maker.domain.models import Document


@runtime_checkable
class LoaderPort(Protocol):
    def can_load(self, path: Path) -> bool: ...

    def load(self, path: Path) -> Document: ...
