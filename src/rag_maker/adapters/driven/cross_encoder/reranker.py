from __future__ import annotations

import logging
from typing import Any

import torch
from sentence_transformers import CrossEncoder

from rag_maker.domain.models import RankedChunk, RetrievedChunk

_logger = logging.getLogger(__name__)

# bge-reranker-v2-m3 fp32 ~= 2.3GB de pesos + ativações para batch top_n=100.
# Margem de segurança em VRAM livre antes de tentar CUDA.
_MIN_CUDA_FREE_MIB = 3500


def _cuda_free_mib() -> int | None:
    """Retorna VRAM livre em MiB, ou None se não conseguir consultar."""
    try:
        free_bytes, _ = torch.cuda.mem_get_info()
        return int(free_bytes // (1024 * 1024))
    except Exception:
        return None


def _resolve_device(device: str, min_cuda_free_mib: int = _MIN_CUDA_FREE_MIB) -> str:
    """Resolve `"auto"` para `cuda`/`mps`/`cpu` conforme disponibilidade.

    PyTorch não aceita `"auto"` como device string; precisa ser resolvido antes.
    Para `cuda`, exige VRAM livre suficiente — caso contrário cai para CPU
    preventivamente (evita OOM durante inferência).
    """
    if device != "auto":
        return device
    if torch.cuda.is_available():
        free = _cuda_free_mib()
        if free is not None and free >= min_cuda_free_mib:
            return "cuda"
        _logger.warning(
            "CUDA disponível mas VRAM livre (%s MiB) abaixo do mínimo (%d MiB). "
            "Usando CPU para o reranker.",
            free if free is not None else "?",
            min_cuda_free_mib,
        )
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _is_cuda_oom(exc: BaseException) -> bool:
    """Detecta OOM de CUDA — torch nem sempre lança `OutOfMemoryError` direto."""
    if isinstance(exc, torch.cuda.OutOfMemoryError):
        return True
    msg = str(exc).lower()
    return "out of memory" in msg or "cuda error: out of memory" in msg


class CrossEncoderReranker:
    """Implementa RerankerPort com BAAI/bge-reranker-v2-m3 (singleton lazy).

    O modelo é carregado na primeira chamada a rerank() — pode demorar ~30s.
    Se o device resolvido for `cuda` mas faltar VRAM (no load ou na inferência),
    faz fallback para `cpu` automaticamente.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "auto",
    ) -> None:
        self._model_name = model_name
        self._device = _resolve_device(device)
        self._model: CrossEncoder | None = None

    def _get_model(self) -> CrossEncoder:
        if self._model is not None:
            return self._model
        try:
            self._model = CrossEncoder(self._model_name, device=self._device)
        except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:
            if self._device != "cuda" or not _is_cuda_oom(exc):
                raise
            _logger.warning(
                "VRAM insuficiente em CUDA para carregar %s — degradando para CPU. Detalhe: %s",
                self._model_name,
                exc,
            )
            self._fallback_to_cpu()
            self._model = CrossEncoder(self._model_name, device="cpu")
        return self._model

    def _fallback_to_cpu(self) -> None:
        """Libera modelo e cache CUDA e fixa device em CPU."""
        self._model = None
        torch.cuda.empty_cache()
        self._device = "cpu"

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RankedChunk]:
        if not chunks:
            return []
        pairs: Any = [(query, c.chunk.content) for c in chunks]
        try:
            raw_scores: list[float] = self._get_model().predict(pairs).tolist()
        except (torch.cuda.OutOfMemoryError, RuntimeError) as exc:
            if self._device != "cuda" or not _is_cuda_oom(exc):
                raise
            _logger.warning(
                "OOM em CUDA durante predict() — recarregando %s em CPU e refazendo. Detalhe: %s",
                self._model_name,
                exc,
            )
            self._fallback_to_cpu()
            self._model = CrossEncoder(self._model_name, device="cpu")
            raw_scores = self._model.predict(pairs).tolist()
        ranked = sorted(zip(chunks, raw_scores, strict=True), key=lambda x: x[1], reverse=True)
        return [
            RankedChunk(chunk=rc.chunk, rerank_score=float(s), rrf_score=rc.rrf_score)
            for rc, s in ranked[:top_k]
        ]
