from __future__ import annotations

import json
import shutil
import sys
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from rag_maker.application.config import AppConfig
from rag_maker.composition.container import (
    add_ignored_path,
    build_container,
    ensure_ollama_ready,
    get_config_path,
    get_config_value,
    get_store_stats,
    list_ignored_paths,
    list_ollama_models,
    ollama_is_running,
    remove_ignored_path,
    set_config_value,
)
from rag_maker.domain.models import (
    EmbeddingError,
    ModelNotFoundError,
    OllamaUnavailableError,
)

# ── Exit codes ────────────────────────────────────────────────────────────────

EXIT_OK = 0
EXIT_USER = 1
EXIT_CONFIG = 2
EXIT_OLLAMA = 3
EXIT_MODEL = 4
EXIT_DB = 5
EXIT_CORPUS = 6
EXIT_INTERNAL = 70

# F12.8 / AUD-CIDOCS-2: mensagem bilíngue — o consumidor (IA externa) segue
# AGENTS.md/README, que documentam exit 5 = "banco corrompido, requer
# intervenção humana, não retentar" e sugerem `rag ingest --full`.
_DB_CORRUPTED_MSG = (
    "Banco corrompido. Execute `rag ingest --full` para reconstruir. / "
    "Corrupted vector store. Run `rag ingest --full` to rebuild."
)

# ── Apps ──────────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="rag",
    help="Ferramenta de recuperação offline (retrieval-only) para IAs externas.",
    add_completion=True,
    no_args_is_help=True,
)
config_app = typer.Typer(name="config", help="Gerenciar configuração.", no_args_is_help=True)
ignore_app = typer.Typer(name="ignore", help="Gerenciar caminhos ignorados.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(ignore_app, name="ignore")

console = Console()
err = Console(stderr=True)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_config() -> AppConfig:
    try:
        return AppConfig.from_file()
    except Exception as exc:
        err.print(f"[red]Configuração inválida:[/red] {exc}")
        raise typer.Exit(EXIT_CONFIG) from exc


def _abort(msg: str, code: int) -> None:
    err.print(f"[red]{msg}[/red]")
    raise typer.Exit(code)


def _print_json(data: object) -> None:
    sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    sys.stdout.flush()


# ── Version ───────────────────────────────────────────────────────────────────


def _version_cb(value: bool) -> None:
    if value:
        console.print(_pkg_version("rag-maker"))
        raise typer.Exit()


@app.callback()
def _root(
    _version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_cb, is_eager=True, help="Exibir versão."),
    ] = None,
) -> None:
    pass


# ── status ────────────────────────────────────────────────────────────────────


@app.command()
def status(
    as_json: Annotated[bool, typer.Option("--json", help="Saída em JSON.")] = False,
) -> None:
    """Mostrar estado do sistema (Ollama, banco, config)."""
    config = _load_config()
    running = ollama_is_running(config)
    stats = get_store_stats(config)

    data = {
        "version": _pkg_version("rag-maker"),
        "config_path": str(get_config_path()),
        "corpus_dir": str(config.paths.corpus_dir) if config.paths.corpus_dir else None,
        "db_dir": str(config.paths.resolved_db_dir()),
        "ollama": {
            "url": config.ollama.url,
            "model": config.ollama.embedding_model,
            "running": running,
        },
        "store": {
            "initialized": stats.initialized,
            "chunk_count": stats.chunk_count,
            "embedding_dim": stats.embedding_dim,
            "corrupted": stats.corrupted,
        },
    }

    if as_json:
        _print_json(data)
    else:
        t = Table(show_header=False, box=None)
        t.add_row("Versão", _pkg_version("rag-maker"))
        t.add_row("Config", str(get_config_path()))
        t.add_row("Corpus dir", str(config.paths.corpus_dir or "[dim]não configurado[/dim]"))
        t.add_row("DB dir", str(config.paths.resolved_db_dir()))
        t.add_row("Ollama", "[green]online[/green]" if running else "[red]offline[/red]")
        t.add_row("Modelo", config.ollama.embedding_model)
        t.add_row(
            "Chunks",
            str(stats.chunk_count) if stats.chunk_count is not None else "[dim]—[/dim]",
        )
        if stats.corrupted:
            t.add_row("Banco", "[red]corrompido[/red]")
        console.print(t)

    # F12.8 / AUD-CIDOCS-2: `status` também deve emitir EXIT_DB=5 quando o
    # banco existe em disco mas está ilegível — sinal diferenciado de "nunca
    # inicializado" (que não é erro em `status`, só ausência de dado).
    if stats.corrupted:
        _abort(_DB_CORRUPTED_MSG, EXIT_DB)


# ── ingest ────────────────────────────────────────────────────────────────────


@app.command()
def ingest(
    corpus: Annotated[Path | None, typer.Option("--corpus", help="Pasta do corpus.")] = None,
    full: Annotated[bool, typer.Option("--full", help="Recriar índice do zero.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirmar sem prompt.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Saída em JSON.")] = False,
) -> None:
    """Ingerir documentos do corpus no índice vetorial."""
    config = _load_config()
    _raw_corpus = corpus or config.paths.corpus_dir
    if _raw_corpus is None:
        _abort(
            "corpus_dir não configurado. Use --corpus DIR ou `rag config set paths.corpus_dir PATH`.",
            EXIT_CONFIG,
        )
        return  # mypy: unreachable after _abort
    corpus_dir = _raw_corpus.expanduser().resolve()
    if not corpus_dir.exists():
        _abort(f"Pasta não encontrada: {corpus_dir}", EXIT_USER)

    if full and not yes:
        confirmed = typer.confirm(f"Reconstruir índice completo de '{corpus_dir}'?", default=False)
        if not confirmed:
            raise typer.Abort()

    try:
        ensure_ollama_ready(config)
    except OllamaUnavailableError:
        _abort("Ollama indisponível. Execute `rag doctor` para diagnóstico.", EXIT_OLLAMA)
    except ModelNotFoundError as exc:
        _abort(f"Modelo não encontrado: {exc}", EXIT_MODEL)

    try:
        container = build_container()
    except Exception as exc:
        _abort(f"Erro ao inicializar componentes: {exc}", EXIT_INTERNAL)

    try:
        if full:
            report = container.ingest.recreate_all(corpus_dir)
        else:
            report = container.ingest.ingest_incremental(corpus_dir)
    except Exception as exc:
        _abort(f"Erro na ingestão: {exc}", EXIT_INTERNAL)

    data = {
        "added": report.added,
        "updated": report.updated,
        "removed": report.removed,
        "errors": [{"path": p, "error": e} for p, e in report.errors],
        "elapsed_ms": round(report.elapsed_ms, 1),
    }

    if as_json:
        _print_json(data)
        return

    if report.errors:
        for path, msg in report.errors:
            err.print(f"[yellow]Erro em {path}:[/yellow] {msg}")

    console.print(
        f"[green]✓[/green] +{report.added} adicionados, "
        f"~{report.updated} atualizados, "
        f"-{report.removed} removidos "
        f"({report.elapsed_ms:.0f} ms)"
    )
    if report.errors:
        console.print(f"[yellow]{len(report.errors)} erros — veja acima.[/yellow]")


# ── query ─────────────────────────────────────────────────────────────────────


@app.command()
def query(
    text: Annotated[str, typer.Argument(help="Consulta em linguagem natural.")],
    top_k: Annotated[
        int | None, typer.Option("--top-k", min=1, help="Número de chunks (>= 1).")
    ] = None,
    alpha: Annotated[float | None, typer.Option("--alpha", help="Peso dense vs lexical.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Saída em JSON.")] = False,
) -> None:
    """Consultar o índice e retornar trechos ranqueados."""
    config = _load_config()
    stats = get_store_stats(config)
    if stats.corrupted:
        _abort(_DB_CORRUPTED_MSG, EXIT_DB)
    if not stats.initialized or not stats.chunk_count:
        _abort("Banco vazio ou não inicializado. Execute `rag ingest` primeiro.", EXIT_CORPUS)

    try:
        ensure_ollama_ready(config)
    except OllamaUnavailableError:
        _abort("Ollama indisponível.", EXIT_OLLAMA)
    except ModelNotFoundError as exc:
        _abort(f"Modelo não encontrado: {exc}", EXIT_MODEL)

    try:
        container = build_container()
        result = container.query.answer(text, top_k=top_k, alpha=alpha)
    except EmbeddingError as exc:
        _abort(f"Erro de embedding: {exc}", EXIT_INTERNAL)
    except Exception as exc:
        _abort(f"Erro na consulta: {exc}", EXIT_INTERNAL)

    chunks_data = [
        {
            "chunk_id": rc.chunk.chunk_id,
            "text": rc.chunk.content,
            "source_path": str(rc.chunk.document_path),
            "source_file": rc.chunk.document_path.name,
            "page": rc.chunk.page,
            "section": rc.chunk.section,
            "rerank_score": round(rc.rerank_score, 6),
            "rrf_score": round(rc.rrf_score, 6),
        }
        for rc in result.ranked_chunks
    ]
    data = {
        "schema_version": 1,
        "query": result.query,
        "chunks": chunks_data,
        "latency_ms": round(result.latency_ms, 1),
    }

    if as_json:
        _print_json(data)
        return

    if not result.ranked_chunks:
        console.print("[dim]Nenhum resultado encontrado.[/dim]")
        return

    t = Table("Score", "Arquivo", "Página", "Trecho", show_lines=True)
    for rc in result.ranked_chunks:
        t.add_row(
            f"{rc.rerank_score:.3f}",
            rc.chunk.document_path.name,
            str(rc.chunk.page) if rc.chunk.page else "—",
            rc.chunk.content[:200].replace("\n", " "),
        )
    console.print(t)
    console.print(f"[dim]Latência: {result.latency_ms:.0f} ms[/dim]")


# ── config ────────────────────────────────────────────────────────────────────


@config_app.command("get")
def config_get(
    key: Annotated[str | None, typer.Argument(help="Chave (ex: ollama.url).")] = None,
) -> None:
    """Exibir configuração atual."""
    if key is None:
        import tomllib

        cfg_path = get_config_path()
        if cfg_path.exists():
            with open(cfg_path, "rb") as f:
                data = tomllib.load(f)
            _print_json(data)
        else:
            console.print("[dim]Nenhum config.toml encontrado. Usando padrões.[/dim]")
        return

    value = get_config_value(key)
    if value is None:
        err.print(f"[yellow]Chave '{key}' não encontrada.[/yellow]")
        raise typer.Exit(EXIT_USER)
    console.print(value)


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Chave (ex: ollama.url).")],
    value: Annotated[str, typer.Argument(help="Valor.")],
) -> None:
    """Definir um valor de configuração (escrita atômica no TOML)."""
    try:
        set_config_value(key, value)
        console.print(f"[green]✓[/green] {key} = {value!r}")
    except Exception as exc:
        _abort(f"Erro ao salvar configuração: {exc}", EXIT_CONFIG)


@config_app.command("path")
def config_path_cmd() -> None:
    """Imprimir caminho do arquivo config.toml."""
    console.print(str(get_config_path()))


# ── ignore ────────────────────────────────────────────────────────────────────


@ignore_app.command("add")
def ignore_add(
    path: Annotated[Path, typer.Argument(help="Caminho a ignorar.")],
) -> None:
    """Adicionar caminho à lista de ignorados."""
    resolved = str(path.expanduser().resolve())
    add_ignored_path(resolved)
    console.print(f"[green]✓[/green] Adicionado: {resolved}")


@ignore_app.command("rm")
def ignore_rm(
    path: Annotated[Path, typer.Argument(help="Caminho a remover da lista.")],
) -> None:
    """Remover caminho da lista de ignorados."""
    resolved = str(path.expanduser().resolve())
    if not remove_ignored_path(resolved):
        err.print(f"[yellow]Não encontrado na lista: {resolved}[/yellow]")
        raise typer.Exit(EXIT_USER)
    console.print(f"[green]✓[/green] Removido: {resolved}")


@ignore_app.command("list")
def ignore_list() -> None:
    """Listar caminhos ignorados."""
    paths = list_ignored_paths()
    if not paths:
        console.print("[dim]Nenhum caminho ignorado.[/dim]")
        return
    for p in paths:
        sys.stdout.write(p + "\n")
    sys.stdout.flush()


# ── doctor ────────────────────────────────────────────────────────────────────


@app.command()
def doctor() -> None:
    """Diagnóstico completo do ambiente."""
    config = _load_config()

    checks: list[tuple[str, bool, str]] = []

    # Ollama daemon
    running = ollama_is_running(config)
    checks.append(("Ollama daemon", running, config.ollama.url))

    # Embedding model
    model_ok = False
    if running:
        models = list_ollama_models(config)
        base = config.ollama.embedding_model.split(":")[0]
        model_ok = any(base in m for m in models)
    checks.append(("Modelo de embedding", model_ok, config.ollama.embedding_model))

    # Reranker cache
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    model_slug = config.reranker.model.replace("/", "--")
    reranker_ok = (hf_cache / f"models--{model_slug}").exists()
    checks.append(("Reranker (HF cache)", reranker_ok, config.reranker.model))

    # corpus_dir
    corpus_ok = config.paths.corpus_dir is not None and config.paths.corpus_dir.exists()
    checks.append(("corpus_dir", corpus_ok, str(config.paths.corpus_dir or "não configurado")))

    # db_dir writable
    db_dir = config.paths.resolved_db_dir()
    try:
        db_dir.mkdir(parents=True, exist_ok=True)
        db_ok = db_dir.is_dir()
    except Exception:
        db_ok = False
    checks.append(("db_dir (escrita)", db_ok, str(db_dir)))

    # Disk space
    try:
        usage = shutil.disk_usage(db_dir.parent if db_dir.parent.exists() else Path.home())
        free_gb = usage.free / 1024**3
        disk_ok = free_gb > 1.0
        checks.append(("Espaço em disco", disk_ok, f"{free_gb:.1f} GB livres"))
    except Exception:
        checks.append(("Espaço em disco", False, "erro ao checar"))

    t = Table("Verificação", "Status", "Detalhe", show_header=True)
    all_ok = True
    for name, ok, detail in checks:
        status_str = "[green]✓[/green]" if ok else "[red]✗[/red]"
        t.add_row(name, status_str, detail)
        if not ok:
            all_ok = False

    console.print(t)
    if not all_ok:
        console.print("[yellow]Alguns itens precisam de atenção. Consulte o README.[/yellow]")
        raise typer.Exit(EXIT_USER)


if __name__ == "__main__":
    app()
