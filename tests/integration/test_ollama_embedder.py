from __future__ import annotations

import pytest
import respx
import httpx

from rag_maker.adapters.driven.ollama.embedder import OllamaEmbedder
from rag_maker.domain.models import DimensionMismatchError, EmbeddingError

_URL = "http://127.0.0.1:11434"
_EMBED = f"{_URL}/api/embed"
_DIM = 8  # dimensão reduzida para testes


def _vec(dim: int = _DIM, val: float = 0.1) -> list[float]:
    return [val] * dim


@pytest.mark.integration
class TestOllamaEmbedder:
    @respx.mock
    def test_embed_returns_tuple(self) -> None:
        respx.post(_EMBED).respond(200, json={"embeddings": [_vec()]})
        emb = OllamaEmbedder("bge-m3:latest", _URL)
        result = emb.embed("hello")
        assert isinstance(result, tuple)
        assert len(result) == _DIM

    @respx.mock
    def test_dim_cached_after_first_embed(self) -> None:
        respx.post(_EMBED).respond(200, json={"embeddings": [_vec()]})
        emb = OllamaEmbedder("bge-m3:latest", _URL)
        emb.embed("test")
        assert emb.dim == _DIM

    @respx.mock
    def test_zero_vector_raises_embedding_error(self) -> None:
        respx.post(_EMBED).respond(200, json={"embeddings": [_vec(val=0.0)]})
        emb = OllamaEmbedder("bge-m3:latest", _URL)
        with pytest.raises(EmbeddingError):
            emb.embed("test")

    @respx.mock
    def test_empty_embedding_raises(self) -> None:
        respx.post(_EMBED).respond(200, json={"embeddings": [[]]})
        emb = OllamaEmbedder("bge-m3:latest", _URL)
        with pytest.raises(EmbeddingError):
            emb.embed("test")

    @respx.mock
    def test_dim_mismatch_raises(self) -> None:
        route = respx.post(_EMBED)
        route.side_effect = [
            httpx.Response(200, json={"embeddings": [_vec(_DIM)]}),
            httpx.Response(200, json={"embeddings": [_vec(_DIM // 2)]}),
        ]
        emb = OllamaEmbedder("bge-m3:latest", _URL)
        emb.embed("first")
        with pytest.raises(DimensionMismatchError):
            emb.embed("second")

    @respx.mock
    def test_embed_batch_returns_list(self) -> None:
        respx.post(_EMBED).respond(200, json={"embeddings": [_vec()]})
        emb = OllamaEmbedder("bge-m3:latest", _URL)
        results = emb.embed_batch(["a", "b"])
        assert len(results) == 2
        assert all(isinstance(r, tuple) for r in results)

    def test_dim_before_embed_raises(self) -> None:
        emb = OllamaEmbedder("bge-m3:latest", _URL)
        with pytest.raises(EmbeddingError, match="Dimensão desconhecida"):
            _ = emb.dim
