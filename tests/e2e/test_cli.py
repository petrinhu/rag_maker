from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Invoca o módulo diretamente via Python com force_terminal=False para captura
_RAG = [sys.executable, "-m", "rag_maker.adapters.driving.cli.main"]
_ENV_BASE = {**os.environ, "FORCE_COLOR": "0", "NO_COLOR": "1"}


def _run(*args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**_ENV_BASE, **(extra_env or {})}
    return subprocess.run([*_RAG, *args], capture_output=True, text=True, env=env)


# ── --version ─────────────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_version_flag() -> None:
    r = _run("--version")
    assert r.returncode == 0
    assert "." in r.stdout  # semver


@pytest.mark.e2e()
def test_help_flag() -> None:
    r = _run("--help")
    assert r.returncode == 0
    assert "rag" in r.stdout.lower() or "rag" in r.stderr.lower()


# ── status ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_status_json(tmp_path: Path) -> None:
    db = str(tmp_path / "db")
    r = _run("status", "--json", extra_env={"RAG_MAKER_PATHS__DB_DIR": db})
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "version" in data
    assert "store" in data
    assert "ollama" in data


# ── config ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_config_path(tmp_path: Path) -> None:
    r = _run("config", "path", extra_env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert r.returncode == 0, r.stderr
    assert "rag_maker" in r.stdout


@pytest.mark.e2e()
def test_config_set_and_get(tmp_path: Path) -> None:
    xdg = {"XDG_CONFIG_HOME": str(tmp_path)}
    r_set = _run("config", "set", "ollama.timeout_seconds", "120", extra_env=xdg)
    assert r_set.returncode == 0, r_set.stderr

    r_get = _run("config", "get", "ollama.timeout_seconds", extra_env=xdg)
    assert r_get.returncode == 0, r_get.stderr
    assert "120" in r_get.stdout


# ── ignore ────────────────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_ignore_add_list_rm(tmp_path: Path) -> None:
    xdg = {"XDG_CONFIG_HOME": str(tmp_path)}
    target = str(tmp_path / "pasta_ignorada")

    r_add = _run("ignore", "add", target, extra_env=xdg)
    assert r_add.returncode == 0, r_add.stderr

    r_list = _run("ignore", "list", extra_env=xdg)
    assert r_list.returncode == 0, r_list.stderr
    assert target in r_list.stdout

    r_rm = _run("ignore", "rm", target, extra_env=xdg)
    assert r_rm.returncode == 0, r_rm.stderr


# ── exit codes ────────────────────────────────────────────────────────────────


@pytest.mark.e2e()
def test_query_empty_store_returns_exit_6(tmp_path: Path) -> None:
    db = str(tmp_path / "db")
    r = _run("query", "teste", "--json", extra_env={"RAG_MAKER_PATHS__DB_DIR": db})
    assert r.returncode == 6


@pytest.mark.e2e()
def test_unknown_command_exits_nonzero() -> None:
    r = _run("naoexiste")
    assert r.returncode != 0
