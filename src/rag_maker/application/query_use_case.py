# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import time

from rag_maker.application.config import AppConfig
from rag_maker.domain.models import QueryResult
from rag_maker.domain.ports.embedder import EmbedderPort
from rag_maker.domain.ports.reranker import RerankerPort
from rag_maker.domain.ports.vector_store import VectorStorePort


class QueryUseCase:
    def __init__(
        self,
        embedder: EmbedderPort,
        store: VectorStorePort,
        reranker: RerankerPort,
        config: AppConfig,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._reranker = reranker
        self._config = config

    def answer(
        self,
        query: str,
        top_k: int | None = None,
        alpha: float | None = None,  # reservado para uso futuro na store
    ) -> QueryResult:
        # AUD-INPUT-4 / F12.15: guard defensivo — a borda (CLI, `typer.Option
        # min=1`) já rejeita top_k <= 0, mas QueryUseCase é chamável por
        # qualquer driving adapter futuro (GUI, outra CLI, uso direto em
        # teste/script); sem este guard, `ranked[:top_k]` com valor negativo
        # usa a semântica de slice do Python ("todos menos os últimos N") e
        # silenciosamente devolve um subconjunto errado em vez de falhar.
        if top_k is not None and top_k <= 0:
            raise ValueError(f"top_k deve ser positivo (recebido: {top_k}).")

        t0 = time.monotonic()
        k = top_k if top_k is not None else self._config.retrieval.rerank_top_k
        coarse_n = self._config.retrieval.coarse_top_n

        query_vector = self._embedder.embed(query)
        retrieved = self._store.hybrid_search(query_vector, query, coarse_n)
        ranked = self._reranker.rerank(query, retrieved, k)

        return QueryResult(
            query=query,
            ranked_chunks=tuple(ranked),
            latency_ms=(time.monotonic() - t0) * 1000,
        )
