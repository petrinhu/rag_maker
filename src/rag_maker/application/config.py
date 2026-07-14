# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _xdg_config_file() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "rag_maker" / "config.toml"


class PathsConfig(BaseModel):
    corpus_dir: Path | None = None
    db_dir: Path | None = None  # None → corpus_dir/rag ou ~/.local/share/rag_maker/db

    def resolved_db_dir(self) -> Path:
        if self.db_dir is not None:
            return self.db_dir.expanduser()
        if self.corpus_dir is not None:
            return self.corpus_dir.expanduser() / "rag"
        return Path.home() / ".local" / "share" / "rag_maker" / "db"


class OllamaConfig(BaseModel):
    url: str = "http://127.0.0.1:11434"
    embedding_model: str = "bge-m3:latest"
    timeout_seconds: int = 180
    auto_start: bool = True
    auto_pull: bool = False


class ChunkingConfig(BaseModel):
    size: int = 1000
    overlap: int = 200


class RetrievalConfig(BaseModel):
    coarse_top_n: int = 100
    rerank_top_k: int = 8
    alpha: float = 0.5


class RerankerConfig(BaseModel):
    model: str = "BAAI/bge-reranker-v2-m3"
    device: str = "auto"
    # AUD-SEC-5 / F12.18: sem revision, `CrossEncoder` resolve a branch mutável
    # `main` do repo HF a cada load — pin explícito de commit SHA evita que uma
    # republicação upstream (conta comprometida ou mantenedor) troque os pesos
    # silenciosamente. `None` preserva o comportamento atual (resolve `main`).
    revision: str | None = None


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "console"


class IgnoredConfig(BaseModel):
    paths: list[Path] = Field(default_factory=list)


class GuiConfig(BaseModel):
    recursive_scan: bool = True


class LoadersConfig(BaseModel):
    """Tetos anti-DoS aplicados pelos loaders (AUD-INPUT-2/AUD-TEST-3/3b).

    Os valores aqui espelham (duplicados intencionalmente, não importados)
    os defaults efetivos em `adapters/driven/loaders/_utils.py` — a regra
    hexagonal proíbe `application/` de importar `adapters/`. Esta classe é a
    superfície de configuração documentada para wiring futuro via
    `composition/container`; os loaders já protegem contra zip bomb, arquivo
    gigante e texto extraído sem limite mesmo sem essa injeção, usando os
    mesmos defaults por construtor.
    """

    max_file_mb: float = 100.0
    max_uncompressed_mb: float = 500.0
    max_compression_ratio: float = 100.0
    max_extracted_chars: int = 20_000_000


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_MAKER_",
        env_nested_delimiter="__",
    )

    paths: PathsConfig = Field(default_factory=PathsConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    ignored: IgnoredConfig = Field(default_factory=IgnoredConfig)
    gui: GuiConfig = Field(default_factory=GuiConfig)
    loaders: LoadersConfig = Field(default_factory=LoadersConfig)
    embedding_dim: int | None = None  # preenchido em runtime após primeiro embed

    @classmethod
    def from_file(cls, path: Path | None = None) -> AppConfig:
        config_path = path or _xdg_config_file()
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            # Mescla TOML (base) com env vars (override). Sem isso, `model_validate`
            # ignora env e RAG_MAKER_* não funciona quando TOML existe.
            env_overrides = cls().model_dump(exclude_unset=True)
            merged = _deep_merge(data, env_overrides)
            return cls.model_validate(merged)
        return cls()


def _deep_merge(base: dict[str, object], override: dict[str, object]) -> dict[str, object]:
    """Merge recursivo: override prevalece sobre base em chaves coincidentes."""
    out = dict(base)
    for key, value in override.items():
        base_value = out.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            out[key] = _deep_merge(base_value, value)
        else:
            out[key] = value
    return out
