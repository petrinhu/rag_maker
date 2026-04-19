from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Document:
    path: Path
    content: str
    content_hash: str  # sha256 hex do conteúdo
    mtime: float
    metadata: dict[str, str] = field(default_factory=dict, hash=False, compare=False)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str  # sha256 de (source_path + char_offset)
    document_path: Path
    content: str
    char_offset: int
    mtime: float
    page: int | None = None
    section: str | None = None


@dataclass(frozen=True)
class IndexedChunk:
    chunk: Chunk
    vector: tuple[float, ...]  # dim validada contra AppConfig.embedding_dim


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    dense_score: float
    lexical_score: float
    rrf_score: float


@dataclass(frozen=True)
class RankedChunk:
    chunk: Chunk
    rerank_score: float
    rrf_score: float


@dataclass(frozen=True)
class QueryResult:
    query: str
    ranked_chunks: tuple[RankedChunk, ...]
    latency_ms: float


# ── Exceções do domínio ───────────────────────────────────────────────────────


class EmbeddingError(Exception):
    """Falha ao gerar embedding; nunca use vetor zero como fallback."""


class DimensionMismatchError(EmbeddingError):
    """Vetor retornado tem dimensão diferente da esperada."""


class OllamaUnavailableError(Exception):
    """Daemon Ollama não respondeu dentro do timeout."""


class ModelNotFoundError(Exception):
    """Modelo requerido não está disponível localmente."""


class LoadError(Exception):
    """Falha ao carregar ou decodificar um arquivo do corpus."""
