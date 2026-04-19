from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbedderPort(Protocol):
    @property
    def dim(self) -> int: ...

    def embed(self, text: str) -> tuple[float, ...]: ...

    def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]: ...
