"""Benchmark de latência do pipeline de recuperação por etapa.

Uso:
    uv run python scripts/benchmark_retrieval.py "filosofia da linguagem" --repeats 5

Requer corpus já ingerido e Ollama rodando.
"""

from __future__ import annotations

import argparse
import statistics
import time

from rich.console import Console
from rich.table import Table

from rag_maker.composition.container import build_container, get_config_path
from rag_maker.domain.models import RetrievedChunk

console = Console()


def _ms(elapsed: float) -> str:
    return f"{elapsed * 1000:.1f} ms"


def benchmark(query: str, repeats: int = 5, top_k: int = 8) -> None:
    config_path = get_config_path()
    container = build_container(config_path)
    embedder = container.embedder
    store = container.store
    reranker = container.reranker

    console.print(f"[bold]Query:[/bold] {query!r}  repeats={repeats}  top_k={top_k}\n")

    # ── Embed ─────────────────────────────────────────────────────────────────
    embed_times: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        vec = embedder.embed(query)
        embed_times.append(time.perf_counter() - t0)

    # ── Search (hybrid HNSW + FTS) ────────────────────────────────────────────
    search_times: list[float] = []
    coarse_top_n = container.config.retrieval.coarse_top_n
    retrieved: list[RetrievedChunk] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        retrieved = store.hybrid_search(vec, query, coarse_top_n)
        search_times.append(time.perf_counter() - t0)

    # ── Rerank ────────────────────────────────────────────────────────────────
    rerank_times: list[float] = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        reranker.rerank(query, retrieved, top_k)
        rerank_times.append(time.perf_counter() - t0)

    # ── Totals ────────────────────────────────────────────────────────────────
    total_times = [
        e + s + r for e, s, r in zip(embed_times, search_times, rerank_times, strict=True)
    ]

    def row(label: str, times: list[float]) -> tuple[str, str, str, str]:
        return (
            label,
            _ms(statistics.median(times)),
            _ms(sorted(times)[int(len(times) * 0.95)]),
            _ms(min(times)),
        )

    table = Table(title="Pipeline Latency Benchmark", show_lines=True)
    table.add_column("Etapa", style="bold")
    table.add_column("P50 (mediana)", justify="right")
    table.add_column("P95", justify="right")
    table.add_column("Min", justify="right")

    table.add_row(*row("embed", embed_times))
    table.add_row(*row("hybrid_search", search_times))
    table.add_row(*row("rerank", rerank_times))
    table.add_row(*row("TOTAL", total_times))

    console.print(table)
    console.print(f"\nChunks candidatos após search: {len(retrieved)} → reranked top-{top_k}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Texto da consulta")
    parser.add_argument("--repeats", type=int, default=5, help="Número de repetições")
    parser.add_argument("--top-k", type=int, default=8, dest="top_k")
    args = parser.parse_args()
    benchmark(args.query, repeats=args.repeats, top_k=args.top_k)


if __name__ == "__main__":
    main()
