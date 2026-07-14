# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import time

import httpx

from rag_maker.domain.models import DimensionMismatchError, EmbeddingError


class OllamaEmbedder:
    """Implementa EmbedderPort via HTTP contra o daemon Ollama.

    Nunca retorna vetor zero — levanta EmbeddingError em falha persistente.
    Descobre a dimensão na primeira chamada e valida nas subsequentes.
    """

    def __init__(
        self,
        model: str,
        url: str,
        timeout_seconds: int = 180,
        max_retries: int = 3,
    ) -> None:
        self._model = model
        self._embed_url = f"{url}/api/embed"
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._dim: int | None = None

    @property
    def dim(self) -> int:
        if self._dim is None:
            raise EmbeddingError("Dimensão desconhecida: chame embed() ao menos uma vez")
        return self._dim

    def embed(self, text: str) -> tuple[float, ...]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self._embed_with_retry(t) for t in texts]

    def _embed_with_retry(self, text: str) -> tuple[float, ...]:
        last: Exception = EmbeddingError("sem tentativas realizadas")
        for attempt in range(self._max_retries):
            try:
                vec = self._call(text)
                self._cache_dim(vec)
                return vec
            except (DimensionMismatchError, EmbeddingError):
                raise
            except Exception as exc:
                last = EmbeddingError(str(exc))
                if attempt < self._max_retries - 1:
                    time.sleep(2**attempt)
        raise last

    def _call(self, text: str) -> tuple[float, ...]:
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(
                self._embed_url,
                json={"model": self._model, "input": text},
            )
            r.raise_for_status()
            data: dict[str, object] = r.json()

        embeddings = data.get("embeddings")
        if not embeddings or not isinstance(embeddings, list) or not embeddings[0]:
            raise EmbeddingError("Ollama retornou embedding vazio")

        raw: list[float] = embeddings[0]
        if all(v == 0.0 for v in raw):
            raise EmbeddingError("Ollama retornou vetor todo-zero — embedding inválido")
        return tuple(float(v) for v in raw)

    def _cache_dim(self, vec: tuple[float, ...]) -> None:
        dim = len(vec)
        if self._dim is None:
            self._dim = dim
        elif dim != self._dim:
            raise DimensionMismatchError(f"dim esperado={self._dim}, recebido={dim}")
