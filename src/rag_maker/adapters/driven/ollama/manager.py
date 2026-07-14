# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import shutil
import subprocess  # nosec B404 # usado só em Popen abaixo com lista fixa de argumentos, sem shell nem input do usuário
import time

import httpx

from rag_maker.domain.models import ModelNotFoundError, OllamaUnavailableError


def probe(url: str, timeout: float = 2.0) -> bool:
    """Retorna True se o daemon Ollama está respondendo."""
    try:
        with httpx.Client() as client:
            r = client.get(f"{url}/api/tags", timeout=timeout)
            return r.status_code == 200
    except Exception:
        return False


def ensure_running(url: str, max_wait_s: float = 30.0) -> None:
    """Garante que o daemon está rodando; spawna se necessário."""
    if probe(url):
        return
    spawn_daemon()
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        if probe(url, timeout=1.0):
            return
        time.sleep(0.5)
    raise OllamaUnavailableError(f"Ollama não respondeu em {max_wait_s:.0f}s após spawn")


def spawn_daemon() -> None:
    """Inicia 'ollama serve' em background (não bloqueia)."""
    if not shutil.which("ollama"):
        raise OllamaUnavailableError("comando 'ollama' não encontrado no PATH")
    subprocess.Popen(  # nosec B603 B607 # comando fixo ["ollama","serve"] resolvido via PATH (shutil.which já validou acima); sem shell=True e sem input do usuário
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def list_models(url: str) -> list[str]:
    """Retorna lista de nomes de modelos disponíveis localmente."""
    try:
        with httpx.Client() as client:
            r = client.get(f"{url}/api/tags", timeout=5.0)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except httpx.HTTPError as e:
        raise OllamaUnavailableError(f"Falha ao listar modelos: {e}") from e


def ensure_model(name: str, url: str, auto_pull: bool = False) -> None:
    """Garante que o modelo está disponível; faz pull se auto_pull=True."""
    models = list_models(url)
    base = name.split(":")[0]
    if any(m == name or m.split(":")[0] == base for m in models):
        return
    if not auto_pull:
        raise ModelNotFoundError(f"Modelo '{name}' não encontrado. Execute: ollama pull {name}")
    _pull(name, url)


def _pull(name: str, url: str) -> None:
    with (
        httpx.Client(timeout=600.0) as client,
        client.stream("POST", f"{url}/api/pull", json={"name": name, "stream": True}) as r,
    ):
        r.raise_for_status()
        for _ in r.iter_lines():
            pass
