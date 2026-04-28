from __future__ import annotations

import pytest

from rag_maker.adapters.driven.cross_encoder.reranker import (
    CrossEncoderReranker,
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
