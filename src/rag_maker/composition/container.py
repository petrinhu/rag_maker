from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag_maker.adapters.driven.config.toml_loader import load_toml, save_toml
from rag_maker.adapters.driven.cross_encoder.reranker import CrossEncoderReranker
from rag_maker.adapters.driven.lancedb.vector_store import LanceVectorStore, table_path
from rag_maker.adapters.driven.loaders import loader_for as _loader_for
from rag_maker.adapters.driven.ollama.embedder import OllamaEmbedder
from rag_maker.adapters.driven.ollama.manager import ensure_model, ensure_running, probe
from rag_maker.application.config import AppConfig, _xdg_config_file
from rag_maker.application.ingest_use_case import IngestUseCase
from rag_maker.application.query_use_case import QueryUseCase
from rag_maker.domain.ports.embedder import EmbedderPort
from rag_maker.domain.ports.reranker import RerankerPort
from rag_maker.domain.ports.vector_store import VectorStorePort

logger = logging.getLogger(__name__)


@dataclass
class Container:
    config: AppConfig
    embedder: EmbedderPort
    store: VectorStorePort
    reranker: RerankerPort
    ingest: IngestUseCase
    query: QueryUseCase

    def rebind_to_corpus(self, new_corpus_dir: Path) -> bool:
        """Aponta o container para um novo corpus.

        Cria ``{new_corpus_dir}/rag`` se não existir, reaproveita o banco
        existente se compatível, persiste os novos paths no TOML e substitui
        store + use cases. Embedder e reranker permanecem.

        Returns:
            True  se a troca foi efetivada.
            False se ``new_corpus_dir`` é igual ao corpus atual (no-op).

        Raises:
            ValueError: pasta não existe ou dim do banco existente é
                incompatível com a dim atual.
            PermissionError / OSError: falha ao criar ``rag/``.
        """
        new_corpus_dir = new_corpus_dir.expanduser().resolve()
        if not new_corpus_dir.is_dir():
            raise ValueError(f"Pasta do corpus nao encontrada: {new_corpus_dir}")

        current = self.config.paths.corpus_dir
        if current is not None and current.expanduser().resolve() == new_corpus_dir:
            return False

        new_db_dir = new_corpus_dir / "rag"
        new_db_dir.mkdir(parents=True, exist_ok=True)

        current_dim = self.config.embedding_dim
        meta = _load_meta(new_db_dir)
        meta_dim = meta.get("embedding_dim")
        if meta_dim is not None and current_dim is not None and meta_dim != current_dim:
            raise ValueError(
                f"Banco em {new_db_dir} usa embedding dim={meta_dim}; "
                f"atual e {current_dim}. Escolha outra pasta ou reconstrua manualmente."
            )

        dim_for_store = current_dim or meta_dim
        if dim_for_store is None:
            raise ValueError(
                "Nenhuma embedding_dim conhecida; ingestao precisa ocorrer pelo menos uma vez."
            )

        new_store = LanceVectorStore(db_path=new_db_dir, embedding_dim=dim_for_store)

        new_paths = self.config.paths.model_copy(
            update={"corpus_dir": new_corpus_dir, "db_dir": new_db_dir}
        )
        new_config = self.config.model_copy(
            update={"paths": new_paths, "embedding_dim": dim_for_store}
        )

        new_ingest = IngestUseCase(
            embedder=self.embedder,
            store=new_store,
            loader_for=_loader_for,
            config=new_config,
        )
        new_query = QueryUseCase(
            embedder=self.embedder,
            store=new_store,
            reranker=self.reranker,
            config=new_config,
        )

        set_config_value("paths.corpus_dir", str(new_corpus_dir))
        set_config_value("paths.db_dir", str(new_db_dir))

        self.config = new_config
        self.store = new_store
        self.ingest = new_ingest
        self.query = new_query
        return True


@dataclass
class StoreStats:
    initialized: bool
    chunk_count: int | None
    embedding_dim: int | None
    # F12.8 / AUD-CIDOCS-2: True quando a tabela existe em disco mas
    # abrir/ler falhou (dados ilegíveis) — distinto de `initialized=False`
    # "puro" (nunca ingerido). Ver `get_store_stats`.
    corrupted: bool = False


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
    """Lê estatísticas do banco sem precisar do Ollama.

    F12.8 / AUD-CIDOCS-2: distingue "banco nunca inicializado" (sem
    `meta.json` com dim conhecida, ou tabela LanceDB nunca criada em disco
    -> `initialized=False`, `corrupted=False`, CLI emite EXIT_CORPUS=6) de
    "banco existe mas está ilegível/corrompido" (a tabela existe em disco,
    mas abrir ou ler falha -> `corrupted=True`, CLI emite EXIT_DB=5). Sem
    essa distinção, um agente reage à corrupção com o remédio errado
    (`rag ingest` incremental, que não reconstrói) em vez de
    `rag ingest --full`.
    """
    db_dir = config.paths.resolved_db_dir()
    meta = _load_meta(db_dir)
    dim: int | None = config.embedding_dim or meta.get("embedding_dim")
    if dim is None:
        return StoreStats(initialized=False, chunk_count=None, embedding_dim=None)

    table_existed_before_open = table_path(db_dir).exists()
    try:
        store = LanceVectorStore(db_path=db_dir, embedding_dim=dim)
        count = store.count()
        store.check_integrity()
        return StoreStats(initialized=True, chunk_count=count, embedding_dim=dim)
    except Exception:
        if table_existed_before_open:
            logger.warning(
                "store_corrupted db_dir=%s: tabela LanceDB existe em disco mas "
                "abrir/ler falhou — sinalizando corrupção (EXIT_DB=5).",
                db_dir,
                exc_info=True,
            )
            return StoreStats(
                initialized=False, chunk_count=None, embedding_dim=dim, corrupted=True
            )
        # Tabela nunca foi criada: nada para ler, não é corrupção.
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
        meta = _load_meta(config.paths.resolved_db_dir())
        dim: int = (
            config.embedding_dim or meta.get("embedding_dim") or len(_embedder.embed("dim probe"))
        )
        if meta.get("embedding_dim") != dim:
            _save_meta(config.paths.resolved_db_dir(), {**meta, "embedding_dim": dim})
        config = config.model_copy(update={"embedding_dim": dim})
        _store = LanceVectorStore(db_path=config.paths.resolved_db_dir(), embedding_dim=dim)

    _reranker: RerankerPort = reranker or CrossEncoderReranker(
        model_name=config.reranker.model,
        device=config.reranker.device,
        revision=config.reranker.revision,
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
