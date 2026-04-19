from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag_maker.adapters.driven.config.toml_loader import load_toml, save_toml
from rag_maker.adapters.driven.cross_encoder.reranker import CrossEncoderReranker
from rag_maker.adapters.driven.lancedb.vector_store import LanceVectorStore
from rag_maker.adapters.driven.loaders import loader_for as _loader_for
from rag_maker.adapters.driven.ollama.embedder import OllamaEmbedder
from rag_maker.adapters.driven.ollama.manager import ensure_model, ensure_running, probe
from rag_maker.application.config import AppConfig, _xdg_config_file
from rag_maker.application.ingest_use_case import IngestUseCase
from rag_maker.application.query_use_case import QueryUseCase
from rag_maker.domain.ports.embedder import EmbedderPort
from rag_maker.domain.ports.reranker import RerankerPort
from rag_maker.domain.ports.vector_store import VectorStorePort


@dataclass
class Container:
    config: AppConfig
    embedder: EmbedderPort
    store: VectorStorePort
    reranker: RerankerPort
    ingest: IngestUseCase
    query: QueryUseCase


@dataclass
class StoreStats:
    initialized: bool
    chunk_count: int | None
    embedding_dim: int | None


# ── Meta (dim cache em disco) ─────────────────────────────────────────────────


def _meta_path(db_dir: Path) -> Path:
    return db_dir / "meta.json"


def _load_meta(db_dir: Path) -> dict[str, Any]:
    p = _meta_path(db_dir)
    if not p.exists():
        return {}
    with open(p) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _save_meta(db_dir: Path, data: dict[str, Any]) -> None:
    db_dir.mkdir(parents=True, exist_ok=True)
    tmp = _meta_path(db_dir).with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f)
    tmp.replace(_meta_path(db_dir))


# ── Funções auxiliares para a CLI ─────────────────────────────────────────────


def get_config_path(config_path: Path | None = None) -> Path:
    return config_path or _xdg_config_file()


def ensure_ollama_ready(config: AppConfig) -> None:
    """Garante que o daemon Ollama está no ar e o modelo está presente."""
    ensure_running(url=config.ollama.url)
    ensure_model(
        name=config.ollama.embedding_model,
        url=config.ollama.url,
        auto_pull=config.ollama.auto_pull,
    )


def get_store_stats(config: AppConfig) -> StoreStats:
    """Lê estatísticas do banco sem precisar do Ollama."""
    meta = _load_meta(config.paths.db_dir)
    dim: int | None = config.embedding_dim or meta.get("embedding_dim")
    if dim is None:
        return StoreStats(initialized=False, chunk_count=None, embedding_dim=None)
    try:
        store = LanceVectorStore(db_path=config.paths.db_dir, embedding_dim=dim)
        return StoreStats(initialized=True, chunk_count=store.count(), embedding_dim=dim)
    except Exception:
        return StoreStats(initialized=False, chunk_count=None, embedding_dim=dim)


def ollama_is_running(config: AppConfig) -> bool:
    return probe(url=config.ollama.url)


_OLLAMA_CANDIDATES = [
    "http://127.0.0.1:11434",
    "http://0.0.0.0:11434",
    "http://localhost:11434",
]


def detect_ollama_url() -> str:
    """Proba candidatos comuns + OLLAMA_HOST; retorna o primeiro que responde."""
    import os
    env_host = os.environ.get("OLLAMA_HOST", "").strip()
    candidates = ([env_host] if env_host else []) + _OLLAMA_CANDIDATES
    for url in candidates:
        if probe(url, timeout=1.5):
            return url
    return _OLLAMA_CANDIDATES[0]


def list_ollama_models(config: AppConfig) -> list[str]:
    from rag_maker.adapters.driven.ollama.manager import list_models as _list_models
    return _list_models(url=config.ollama.url)


def list_ignored_paths(config_path: Path | None = None) -> list[str]:
    data = load_toml(get_config_path(config_path))
    raw = data.get("ignored", {}).get("paths", [])
    return [str(p) for p in raw] if isinstance(raw, list) else []


def add_ignored_path(path: str, config_path: Path | None = None) -> None:
    toml_path = get_config_path(config_path)
    data = load_toml(toml_path)
    paths: list[str] = data.get("ignored", {}).get("paths", [])
    if path not in paths:
        paths.append(path)
    data.setdefault("ignored", {})["paths"] = paths
    save_toml(toml_path, data)


def remove_ignored_path(path: str, config_path: Path | None = None) -> bool:
    toml_path = get_config_path(config_path)
    data = load_toml(toml_path)
    paths: list[str] = data.get("ignored", {}).get("paths", [])
    if path not in paths:
        return False
    paths.remove(path)
    data.setdefault("ignored", {})["paths"] = paths
    save_toml(toml_path, data)
    return True


def get_config_value(key: str, config_path: Path | None = None) -> Any:
    data = load_toml(get_config_path(config_path))
    parts = key.split(".")
    node: Any = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def set_config_value(key: str, value: str, config_path: Path | None = None) -> None:
    path = get_config_path(config_path)
    data = load_toml(path)
    parts = key.split(".")
    node: dict[str, Any] = data
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    # coerce value to best type
    node[parts[-1]] = _coerce(value)
    save_toml(path, data)


def _coerce(value: str) -> int | float | bool | str:
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


# ── Factory principal ─────────────────────────────────────────────────────────


def build_container(
    config_path: Path | None = None,
    *,
    embedder: EmbedderPort | None = None,
    store: VectorStorePort | None = None,
    reranker: RerankerPort | None = None,
) -> Container:
    config = AppConfig.from_file(config_path)

    _embedder: EmbedderPort = embedder or OllamaEmbedder(
        model=config.ollama.embedding_model,
        url=config.ollama.url,
        timeout_seconds=config.ollama.timeout_seconds,
    )

    _store: VectorStorePort
    if store is not None:
        _store = store
    else:
        meta = _load_meta(config.paths.db_dir)
        dim: int = config.embedding_dim or meta.get("embedding_dim") or len(
            _embedder.embed("dim probe")
        )
        if meta.get("embedding_dim") != dim:
            _save_meta(config.paths.db_dir, {**meta, "embedding_dim": dim})
        config = config.model_copy(update={"embedding_dim": dim})
        _store = LanceVectorStore(db_path=config.paths.db_dir, embedding_dim=dim)

    _reranker: RerankerPort = reranker or CrossEncoderReranker(
        model_name=config.reranker.model,
        device=config.reranker.device,
    )

    return Container(
        config=config,
        embedder=_embedder,
        store=_store,
        reranker=_reranker,
        ingest=IngestUseCase(
            embedder=_embedder,
            store=_store,
            loader_for=_loader_for,
            config=config,
        ),
        query=QueryUseCase(
            embedder=_embedder,
            store=_store,
            reranker=_reranker,
            config=config,
        ),
    )
