from __future__ import annotations

from typing import Any

import pytest

from rag_maker.adapters.driven.cross_encoder import reranker as reranker_mod
from rag_maker.adapters.driven.cross_encoder.reranker import (
    CrossEncoderReranker,
    _is_cuda_oom,
    _resolve_device,
)


@pytest.mark.unit
class TestResolveDevice:
    def test_auto_resolves_to_cpu_when_no_accelerator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        if hasattr(torch.backends, "mps"):
            monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)

        assert _resolve_device("auto") == "cpu"

    def test_auto_resolves_to_cuda_when_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)

        assert _resolve_device("auto") == "cuda"

    def test_auto_prefers_cuda_over_mps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        if hasattr(torch.backends, "mps"):
            monkeypatch.setattr(torch.backends.mps, "is_available", lambda: True)

        assert _resolve_device("auto") == "cuda"

    def test_explicit_cpu_passes_through(self) -> None:
        assert _resolve_device("cpu") == "cpu"

    def test_explicit_cuda_passes_through(self) -> None:
        assert _resolve_device("cuda") == "cuda"

    def test_explicit_unknown_passes_through_unchanged(self) -> None:
        # Não validamos device strings desconhecidas — torch é quem reclama.
        assert _resolve_device("xpu") == "xpu"


@pytest.mark.unit
class TestRerankerInitResolvesDevice:
    def test_init_with_auto_stores_resolved_device(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
        if hasattr(torch.backends, "mps"):
            monkeypatch.setattr(torch.backends.mps, "is_available", lambda: False)

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
    def test_falls_back_to_cpu_on_cuda_oom(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
        monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)

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
        import torch

        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)

        class _FakeModel:
            def __init__(self, model_name: str, device: str) -> None:
                raise RuntimeError("network unreachable")

        monkeypatch.setattr(reranker_mod, "CrossEncoder", _FakeModel)

        reranker = CrossEncoderReranker(device="auto")
        with pytest.raises(RuntimeError, match="network unreachable"):
            reranker._get_model()
        assert reranker._device == "cuda"  # não degradou

    def test_no_fallback_when_device_is_already_cpu(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _FakeModel:
            def __init__(self, model_name: str, device: str) -> None:
                raise RuntimeError("out of memory on cpu")

        monkeypatch.setattr(reranker_mod, "CrossEncoder", _FakeModel)

        reranker = CrossEncoderReranker(device="cpu")
        with pytest.raises(RuntimeError, match="out of memory"):
            reranker._get_model()
