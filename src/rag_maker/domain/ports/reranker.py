# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_maker.domain.models import RankedChunk, RetrievedChunk


@runtime_checkable
class RerankerPort(Protocol):
    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RankedChunk]: ...
