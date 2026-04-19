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
    db_dir: Path | None = None  # None → ~/.local/share/rag_maker/db

    def resolved_db_dir(self) -> Path:
        if self.db_dir is not None:
            return self.db_dir.expanduser()
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


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "console"


class IgnoredConfig(BaseModel):
    paths: list[Path] = Field(default_factory=list)


class GuiConfig(BaseModel):
    recursive_scan: bool = True


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
    embedding_dim: int | None = None  # preenchido em runtime após primeiro embed

    @classmethod
    def from_file(cls, path: Path | None = None) -> AppConfig:
        config_path = path or _xdg_config_file()
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            return cls.model_validate(data)
        return cls()
