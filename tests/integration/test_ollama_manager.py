from __future__ import annotations

import shutil
import subprocess
import time

import httpx
import pytest
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
        respx.get(_TAGS).respond(
            200,
            json={
                "models": [
                    {"name": "bge-m3:latest"},
                    {"name": "llama2:7b"},
                ]
            },
        )
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

    @respx.mock
    def test_model_missing_with_auto_pull_delegates_to_pull(self) -> None:
        """F12.20/AUD-TEST-4: cobre a call-site de _pull() (manager.py:66)."""
        respx.get(_TAGS).respond(200, json={"models": []})
        pull_route = respx.post(f"{_URL}/api/pull").respond(200, content=b'{"status":"success"}\n')

        manager.ensure_model("bge-m3:latest", _URL, auto_pull=True)

        assert pull_route.called


@pytest.mark.integration
class TestEnsureRunning:
    """F12.20/AUD-TEST-4: cobre ensure_running sem custar tempo real de wall-clock."""

    def test_returns_immediately_when_already_running(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(manager, "probe", lambda url, timeout=2.0: True)

        def _fail_spawn() -> None:
            raise AssertionError("spawn_daemon não deveria ser chamado se já está rodando")

        monkeypatch.setattr(manager, "spawn_daemon", _fail_spawn)
        manager.ensure_running(_URL, max_wait_s=30.0)

    def test_succeeds_after_n_probes_post_spawn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 1ª chamada (fora do loop): False -> aciona spawn_daemon.
        # Dentro do loop: False, depois True (recupera após 2 probes).
        probe_results = iter([False, False, True])
        monkeypatch.setattr(manager, "probe", lambda url, timeout=2.0: next(probe_results))
        spawn_calls: list[None] = []
        monkeypatch.setattr(manager, "spawn_daemon", lambda: spawn_calls.append(None))
        sleep_calls: list[float] = []
        monkeypatch.setattr(time, "sleep", lambda s: sleep_calls.append(s))

        manager.ensure_running(_URL, max_wait_s=30.0)

        assert len(spawn_calls) == 1
        assert sleep_calls == [0.5]

    def test_raises_on_timeout_without_real_wait(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(manager, "probe", lambda url, timeout=2.0: False)
        monkeypatch.setattr(manager, "spawn_daemon", lambda: None)

        clock = [0.0]

        def fake_monotonic() -> float:
            return clock[0]

        def fake_sleep(seconds: float) -> None:
            clock[0] += seconds

        monkeypatch.setattr(time, "monotonic", fake_monotonic)
        monkeypatch.setattr(time, "sleep", fake_sleep)

        with pytest.raises(OllamaUnavailableError, match="30s"):
            manager.ensure_running(_URL, max_wait_s=30.0)


@pytest.mark.integration
class TestSpawnDaemon:
    """F12.20/AUD-TEST-4: caminho 'ollama' ausente do PATH e args do Popen."""

    def test_ollama_not_in_path_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: None)
        with pytest.raises(OllamaUnavailableError, match="ollama"):
            manager.spawn_daemon()

    def test_spawns_with_expected_args_and_new_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ollama")
        captured_args: list[list[str]] = []
        captured_kwargs: list[dict[str, object]] = []

        def fake_popen(args: list[str], **kwargs: object) -> object:
            captured_args.append(args)
            captured_kwargs.append(kwargs)
            return object()

        monkeypatch.setattr(subprocess, "Popen", fake_popen)

        manager.spawn_daemon()

        assert captured_args == [["ollama", "serve"]]
        kwargs = captured_kwargs[0]
        assert kwargs["start_new_session"] is True
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL


@pytest.mark.integration
class TestPull:
    """F12.20/AUD-TEST-4: streaming de POST /api/pull (sucesso e erro)."""

    @respx.mock
    def test_success_consumes_full_stream_without_error(self) -> None:
        route = respx.post(f"{_URL}/api/pull").respond(
            200,
            content=b'{"status":"pulling manifest"}\n{"status":"success"}\n',
        )

        manager._pull("bge-m3:latest", _URL)

        sent_body = route.calls.last.request.content
        assert b'"name": "bge-m3:latest"' in sent_body or b'"name":"bge-m3:latest"' in sent_body

    @respx.mock
    def test_http_error_in_stream_raises(self) -> None:
        respx.post(f"{_URL}/api/pull").respond(404, json={"error": "model not found"})

        with pytest.raises(httpx.HTTPStatusError):
            manager._pull("nonexistent:latest", _URL)
