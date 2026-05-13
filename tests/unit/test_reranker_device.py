from __future__ import annotations

from typing import Any

import pytest

from rag_maker.adapters.driven.cross_encoder import reranker as reranker_mod
from rag_maker.adapters.driven.cross_encoder.reranker import (
    _MIN_CUDA_FREE_MIB,
    CrossEncoderReranker,
    _is_cuda_oom,
    _resolve_device,
)


def _mock_cuda(
    monkeypatch: pytest.MonkeyPatch,
    *,
    available: bool,
    free_mib: int = 8000,
) -> None:
    """Helper: simula `torch.cuda.is_available()` e `mem_get_info()` em conjunto."""
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: available)
    if available:
        free_bytes = free_mib * 1024 * 1024
        monkeypatch.setattr(
            torch.cuda, "mem_get_info", lambda *_a, **_k: (free_bytes, free_bytes * 2)
        )
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    if hasattr(torch.backends, "mps"):
        monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)


@pytest.mark.unit
class TestResolveDevice:
    def test_auto_resolves_to_cpu_when_no_accelerator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_cuda(monkeypatch, available=False)

        assert _resolve_device("auto") == "cpu"

    def test_auto_resolves_to_cuda_when_vram_sufficient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_cuda(monkeypatch, available=True, free_mib=_MIN_CUDA_FREE_MIB + 100)

        assert _resolve_device("auto") == "cuda"

    def test_auto_falls_back_to_cpu_when_vram_low(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_cuda(monkeypatch, available=True, free_mib=_MIN_CUDA_FREE_MIB - 100)

        assert _resolve_device("auto") == "cpu"

    def test_auto_falls_back_when_mem_get_info_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)

        def _raise(*_a: Any, **_kw: Any) -> tuple[int, int]:
            raise RuntimeError("driver mismatch")

        monkeypatch.setattr(torch.cuda, "mem_get_info", _raise)
        if hasattr(torch.backends, "mps"):
            monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)

        assert _resolve_device("auto") == "cpu"

    def test_auto_prefers_cuda_over_mps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import torch

        _mock_cuda(monkeypatch, available=True, free_mib=_MIN_CUDA_FREE_MIB + 100)
        if hasattr(torch.backends, "mps"):
            monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)

        assert _resolve_device("auto") == "cuda"

    def test_explicit_cpu_passes_through(self) -> None:
        assert _resolve_device("cpu") == "cpu"

    def test_explicit_cuda_passes_through(self) -> None:
        # Mesmo sem checar VRAM, usuário explícito é respeitado.
        assert _resolve_device("cuda") == "cuda"

    def test_explicit_unknown_passes_through_unchanged(self) -> None:
        # Não validamos device strings desconhecidas — torch é quem reclama.
        assert _resolve_device("xpu") == "xpu"


@pytest.mark.unit
class TestRerankerInitResolvesDevice:
    def test_init_with_auto_stores_resolved_device(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_cuda(monkeypatch, available=False)

        reranker = CrossEncoderReranker(device="auto")

        # nunca expor "auto" para torch
        assert reranker._device != "auto"
        assert reranker._device == "cpu"

    def test_init_with_explicit_cpu(self) -> None:
        reranker = CrossEncoderReranker(device="cpu")

        assert reranker._device == "cpu"


@pytest.mark.unit
class TestIsCudaOom:
    def test_detects_torch_oom_class(self) -> None:
        import torch

        exc = torch.cuda.OutOfMemoryError("CUDA out of memory")
        assert _is_cuda_oom(exc) is True

    def test_detects_runtime_with_oom_message(self) -> None:
        exc = RuntimeError("CUDA out of memory. Tried to allocate 2.27 GiB")
        assert _is_cuda_oom(exc) is True

    def test_detects_oom_case_insensitive(self) -> None:
        exc = RuntimeError("OUT OF MEMORY")
        assert _is_cuda_oom(exc) is True

    def test_other_runtime_error_is_not_oom(self) -> None:
        exc = RuntimeError("some other failure")
        assert _is_cuda_oom(exc) is False


@pytest.mark.unit
class TestRerankerOomFallback:
    def test_falls_back_to_cpu_on_cuda_oom_at_load(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_cuda(monkeypatch, available=True, free_mib=_MIN_CUDA_FREE_MIB + 1000)

        calls: list[dict[str, Any]] = []

        class _FakeModel:
            def __init__(self, model_name: str, device: str) -> None:
                calls.append({"model_name": model_name, "device": device})
                if device == "cuda":
                    raise RuntimeError("CUDA out of memory. Tried to allocate 2.27 GiB")

        monkeypatch.setattr(reranker_mod, "CrossEncoder", _FakeModel)

        reranker = CrossEncoderReranker(device="auto")
        assert reranker._device == "cuda"  # antes do load

        model = reranker._get_model()
        assert isinstance(model, _FakeModel)
        # primeira tentativa em cuda, segunda em cpu
        assert [c["device"] for c in calls] == ["cuda", "cpu"]
        assert reranker._device == "cpu"  # fallback persistido

    def test_does_not_fallback_on_unrelated_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _mock_cuda(monkeypatch, available=True, free_mib=_MIN_CUDA_FREE_MIB + 1000)

        class _FakeModel:
            def __init__(self, model_name: str, device: str) -> None:
                raise RuntimeError("network unreachable")

        monkeypatch.setattr(reranker_mod, "CrossEncoder", _FakeModel)

        reranker = CrossEncoderReranker(device="auto")
        with pytest.raises(RuntimeError, match="network unreachable"):
            reranker._get_model()
        assert reranker._device == "cuda"  # não degradou

    def test_no_fallback_when_device_is_already_cpu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _FakeModel:
            def __init__(self, model_name: str, device: str) -> None:
                raise RuntimeError("out of memory on cpu")

        monkeypatch.setattr(reranker_mod, "CrossEncoder", _FakeModel)

        reranker = CrossEncoderReranker(device="cpu")
        with pytest.raises(RuntimeError, match="out of memory"):
            reranker._get_model()


@pytest.mark.unit
class TestRerankPredictOomFallback:
    def test_predict_oom_triggers_cpu_reload_and_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pathlib import Path

        from rag_maker.domain.models import Chunk, RetrievedChunk

        _mock_cuda(monkeypatch, available=True, free_mib=_MIN_CUDA_FREE_MIB + 1000)

        instances: list[Any] = []

        class _FakeArray:
            def __init__(self, values: list[float]) -> None:
                self._values = values

            def tolist(self) -> list[float]:
                return self._values

        class _FakeModel:
            def __init__(self, model_name: str, device: str) -> None:
                self.device = device
                self.predict_calls = 0
                instances.append(self)

            def predict(self, pairs: list[tuple[str, str]]) -> _FakeArray:
                self.predict_calls += 1
                if self.device == "cuda":
                    raise RuntimeError("CUDA out of memory. Tried to allocate 150.00 MiB")
                return _FakeArray([0.9 - 0.1 * i for i in range(len(pairs))])

        monkeypatch.setattr(reranker_mod, "CrossEncoder", _FakeModel)

        chunks = [
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id=f"c{i}",
                    document_path=Path("doc.txt"),
                    content=f"texto {i}",
                    char_offset=0,
                    mtime=0.0,
                ),
                dense_score=0.5,
                lexical_score=0.5,
                rrf_score=0.5,
            )
            for i in range(3)
        ]

        reranker = CrossEncoderReranker(device="auto")
        results = reranker.rerank("query", chunks, top_k=3)

        # 2 modelos foram instanciados: cuda (que estourou no predict) + cpu
        assert [m.device for m in instances] == ["cuda", "cpu"]
        # cuda predict() chamado 1x (e falhou); cpu predict() chamado 1x (e venceu)
        assert instances[0].predict_calls == 1
        assert instances[1].predict_calls == 1
        # device foi atualizado para cpu após o fallback
        assert reranker._device == "cpu"
        # resultado válido — ordem decrescente por score
        assert len(results) == 3
        assert [r.chunk.chunk_id for r in results] == ["c0", "c1", "c2"]

    def test_predict_non_oom_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pathlib import Path

        from rag_maker.domain.models import Chunk, RetrievedChunk

        _mock_cuda(monkeypatch, available=True, free_mib=_MIN_CUDA_FREE_MIB + 1000)

        class _FakeModel:
            def __init__(self, model_name: str, device: str) -> None:
                pass

            def predict(self, pairs: list[tuple[str, str]]) -> Any:
                raise RuntimeError("kernel panic")

        monkeypatch.setattr(reranker_mod, "CrossEncoder", _FakeModel)

        chunks = [
            RetrievedChunk(
                chunk=Chunk(
                    chunk_id="c0",
                    document_path=Path("d.txt"),
                    content="x",
                    char_offset=0,
                    mtime=0.0,
                ),
                dense_score=0.5,
                lexical_score=0.5,
                rrf_score=0.5,
            )
        ]

        reranker = CrossEncoderReranker(device="auto")
        with pytest.raises(RuntimeError, match="kernel panic"):
            reranker.rerank("q", chunks, top_k=1)
