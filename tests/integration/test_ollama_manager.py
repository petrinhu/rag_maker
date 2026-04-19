from __future__ import annotations

import pytest
import httpx
import respx

from rag_maker.adapters.driven.ollama import manager
from rag_maker.domain.models import ModelNotFoundError, OllamaUnavailableError

_URL = "http://127.0.0.1:11434"
_TAGS = f"{_URL}/api/tags"


@pytest.mark.integration
class TestProbe:
    @respx.mock
    def test_probe_success(self) -> None:
        respx.get(_TAGS).respond(200, json={"models": []})
        assert manager.probe(_URL) is True

    @respx.mock
    def test_probe_connection_error(self) -> None:
        respx.get(_TAGS).mock(side_effect=httpx.ConnectError("refused"))
        assert manager.probe(_URL) is False

    @respx.mock
    def test_probe_non_200(self) -> None:
        respx.get(_TAGS).respond(500)
        assert manager.probe(_URL) is False


@pytest.mark.integration
class TestListModels:
    @respx.mock
    def test_returns_model_names(self) -> None:
        respx.get(_TAGS).respond(200, json={"models": [
            {"name": "bge-m3:latest"},
            {"name": "llama2:7b"},
        ]})
        models = manager.list_models(_URL)
        assert "bge-m3:latest" in models
        assert "llama2:7b" in models

    @respx.mock
    def test_empty_models_list(self) -> None:
        respx.get(_TAGS).respond(200, json={"models": []})
        assert manager.list_models(_URL) == []

    @respx.mock
    def test_http_error_raises(self) -> None:
        respx.get(_TAGS).respond(503)
        with pytest.raises(OllamaUnavailableError):
            manager.list_models(_URL)


@pytest.mark.integration
class TestEnsureModel:
    @respx.mock
    def test_model_found_no_exception(self) -> None:
        respx.get(_TAGS).respond(200, json={"models": [{"name": "bge-m3:latest"}]})
        manager.ensure_model("bge-m3:latest", _URL, auto_pull=False)

    @respx.mock
    def test_model_missing_raises(self) -> None:
        respx.get(_TAGS).respond(200, json={"models": []})
        with pytest.raises(ModelNotFoundError):
            manager.ensure_model("bge-m3:latest", _URL, auto_pull=False)

    @respx.mock
    def test_base_name_match(self) -> None:
        respx.get(_TAGS).respond(200, json={"models": [{"name": "bge-m3:latest"}]})
        manager.ensure_model("bge-m3", _URL, auto_pull=False)
