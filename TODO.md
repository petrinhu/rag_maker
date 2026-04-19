# rag_maker — Planejamento

Tabela de pendências do projeto. Todas as ações passam por aqui antes de qualquer escrita de código.

**Arquitetura:** hexagonal (Ports & Adapters). `domain/` é puro; `application/` orquestra via ports; `adapters/driven/` implementam I/O; `adapters/driving/` (CLI, GUI) invocam os use cases; `composition/container.py` faz o wiring.

**Regra crítica:** `domain/` nunca importa de `adapters/` nem de libs externas. Adapters importam de `domain/ports/` e implementam os Protocols. Ver `CONTRACT.md` para regras completas e `TESTES.md` para quality gates.

**Mapeamento front/mid/back (hexagonal):**

| Camada | Módulos | Papel |
|:---|:---|:---|
| **Front** (driving) | `adapters/driving/cli`, `adapters/driving/gui` | Entrada humana/agente → use case |
| **Mid** (core + wiring) | `domain/`, `application/`, `composition/` | Regras puras + orquestração + DI |
| **Back** (driven) | `adapters/driven/{ollama,lancedb,cross_encoder,loaders,config}` | I/O, serviços externos |

Referências:
- Plano de arquitetura completo: `/home/petrus/.claude/plans/vou-refazer-o-projeto-serene-robin.md`
- Contrato técnico do projeto: `CONTRACT.md`
- Padrões de teste e gates de qualidade: `TESTES.md`

## Resumo por fase

| Fase | Grupo | Camada | Tarefas | Prioridade geral |
|:---:|:---|:---:|:---:|:---:|
| F0 | Pré-execução | — | 2 | Alta |
| F1 | Fundação (infra de projeto + quality gates) | neutro | 16 | Alta |
| F2 | Domínio + Ports + Application/config | Mid | 14 | Alta |
| F3 | Adapters driven (I/O) | Back | 19 | Alta |
| F4 | Application (use cases) + Composition | Mid | 7 | Alta |
| F5 | Adapter driving: CLI + AGENTS.md | Front | 11 | Alta |
| F6 | Adapter driving: GUI Qt6 | Front | 10 | Média |
| F7 | Polimento + Distribuição | neutro | 7 | Média |
| **Total** | | | **86** | |

---

## Pendências

| ID | Grupo | Descrição Técnica | Prioridade | Pré-requisito | Dificuldade | Status | Estado Auditado |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| F0.1 | Pré-execução | Popular esta tabela oficial via `tab_pendencias --create` | Alta | — | Baixa | ✅ Concluído | — |
| F0.2 | Pré-execução | Usuário revisa tabela e autoriza início da Fase 1 | Alta | F0.1 | Baixa | ✅ Concluído | ✓ |
| F1.1 | Fundação | `git init` na raiz; primeiro commit vazio (Conventional Commits habilitado) | Alta | F0.2 | Baixa | ✅ Concluído | ✓ |
| F1.2 | Fundação | `.gitignore` (`legacy/`, `.venv/`, `__pycache__/`, `*.lance/`, `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`, `dist/`, `build/`, `*.egg-info`, `htmlcov/`) | Alta | F1.1 | Baixa | ✅ Concluído | ✓ |
| F1.3 | Fundação | `.python-version` = `3.11` | Alta | F1.1 | Baixa | ✅ Concluído | ✓ |
| F1.4 | Fundação | `pyproject.toml`: metadata, deps principais, extras `gui`+`dev`, placeholder de entry points `rag`/`rag-gui`, configs de ruff/mypy/pytest/coverage embutidas | Alta | F1.1 | Média | ✅ Concluído | ✓ |
| F1.5 | Fundação | `uv sync` → gerar `uv.lock` determinístico | Alta | F1.4 | Baixa | ✅ Concluído | ✓ |
| F1.6 | Fundação | `ruff.toml` (regras + line-length 100 + isort + pyupgrade) | Alta | F1.5 | Baixa | ✅ Concluído | ✓ |
| F1.7 | Fundação | `mypy.ini` em modo strict (ou `[tool.mypy]` no pyproject) | Alta | F1.5 | Baixa | ✅ Concluído | ✓ |
| F1.8 | Fundação | Scaffold hexagonal: criar árvore `src/rag_maker/{domain/ports,application,adapters/driving/{cli,gui/widgets},adapters/driven/{ollama,lancedb,cross_encoder,loaders,config},composition}` + `tests/{unit,integration,e2e,fixtures/corpus_mini}` + todos os `__init__.py` vazios | Alta | F1.5 | Baixa | ✅ Concluído | ✓ |
| F1.9 | Fundação | `src/rag_maker/py.typed` (marker PEP 561) | Alta | F1.8 | Baixa | ✅ Concluído | ✓ |
| F1.10 | Fundação | `rag_maker.toml.example` na raiz (config comentado; TOML é single source of truth) | Alta | F1.4 | Baixa | ✅ Concluído | ✓ |
| F1.11 | Fundação | `AGENTS.md` stub (cabeçalho + aviso "conteúdo preenchido em F5.10") | Alta | F1.8 | Baixa | ✅ Concluído | ✓ |
| F1.12 | Fundação | `tests/conftest.py` mínimo (marcadores `unit`/`integration`/`e2e`, fixture `tmp_config_dir`) | Alta | F1.8 | Baixa | ✅ Concluído | ✓ |
| F1.13 | Fundação | `.importlinter` com contratos hexagonais: `domain` não importa de `adapters\|application\|composition`; `application` não importa de `adapters`; `adapters/driving` não importa de `adapters/driven` | Alta | F1.8 | Média | ✅ Concluído | ✓ |
| F1.14 | Fundação | Config de `bandit` (pyproject `[tool.bandit]` ou `bandit.yaml`) + script `uv run pip-audit` no dev workflow | Alta | F1.5 | Baixa | ✅ Concluído | ✓ |
| F1.15 | Fundação | Config de `coverage.py` no pyproject (`fail_under=70`, `source=["src/rag_maker"]`, exclude `adapters/driving/gui`) | Alta | F1.5 | Baixa | ✅ Concluído | ✓ |
| F1.16 | Fundação | Validar estrutura vazia: `uv run ruff check` + `uv run mypy src/` + `uv run pytest --collect-only` + `uv run lint-imports` + `uv run bandit -r src/` todos verdes | Alta | F1.6, F1.7, F1.8, F1.13, F1.14 | Baixa | ✅ Concluído | ✓ |
| F2.1 | Domínio | `domain/models.py`: frozen dataclasses `Document`, `Chunk`, `IndexedChunk`, `RetrievedChunk`, `RankedChunk`, `QueryResult` (PEP 604 unions, `from __future__ import annotations`) | Alta | F1.16 | Média | ✅ Concluído | ✓ |
| F2.2 | Domínio | `domain/models.py`: exceções `EmbeddingError`, `DimensionMismatchError`, `OllamaUnavailableError`, `ModelNotFoundError`, `LoadError` | Alta | F2.1 | Baixa | ✅ Concluído | ✓ |
| F2.3 | Domínio | `domain/chunker.py`: `RecursiveCharacterChunker` (lógica pura, params por construtor; zero I/O) | Alta | F2.1 | Média | ✅ Concluído | ✓ |
| F2.4 | Domínio | `domain/scoring.py`: `rrf_fuse(dense_ranks, lexical_ranks, k)` (função pura) | Alta | F2.1 | Baixa | ✅ Concluído | ✓ |
| F2.5 | Domínio/Ports | `domain/ports/embedder.py`: `@runtime_checkable` Protocol `EmbedderPort` (`embed`, `embed_batch`, `dim`) | Alta | F2.1, F2.2 | Baixa | ✅ Concluído | ✓ |
| F2.6 | Domínio/Ports | `domain/ports/vector_store.py`: Protocol `VectorStorePort` (`upsert`, `delete_by_source`, `hybrid_search`, `count`, `stats`) | Alta | F2.1 | Baixa | ✅ Concluído | ✓ |
| F2.7 | Domínio/Ports | `domain/ports/reranker.py`: Protocol `RerankerPort` (`rerank(query, chunks, top_k)`) | Alta | F2.1 | Baixa | ✅ Concluído | ✓ |
| F2.8 | Domínio/Ports | `domain/ports/loader.py`: Protocol `LoaderPort` (`can_load`, `load`) | Alta | F2.1 | Baixa | ✅ Concluído | ✓ |
| F2.9 | Application/Config | `application/config.py`: `AppConfig` via pydantic-settings lendo TOML + env overrides; campos: `paths`, `ollama`, `chunking`, `retrieval`, `reranker`, `logging`, `ignored` | Alta | F1.16 | Média | ✅ Concluído | ✓ |
| F2.10 | Tests/Unit | `tests/unit/test_models.py` (frozen, hash, igualdade, PEP 604 unions) | Alta | F2.1, F2.2 | Baixa | ✅ Concluído | ✓ |
| F2.11 | Tests/Unit | `tests/unit/test_chunker.py` via hypothesis (invariantes: tamanho, overlap, ordem, preserva conteúdo) | Alta | F2.3 | Média | ✅ Concluído | ✓ |
| F2.12 | Tests/Unit | `tests/unit/test_scoring.py` via hypothesis (propriedades RRF: idempotência, simetria, monotonicidade) | Alta | F2.4 | Média | ✅ Concluído | ✓ |
| F2.13 | Tests/Unit | `tests/unit/test_config.py` (TOML, defaults, override por env, paths XDG) | Alta | F2.9 | Média | ✅ Concluído | ✓ |
| F2.14 | Validação | `uv run mypy src/` strict + `uv run pytest tests/unit/ --cov` (≥70%) + `uv run lint-imports` verde | Alta | F2.10, F2.11, F2.12, F2.13 | Baixa | ✅ Concluído | ✓ |
| F3.1 | Adapters/Driven | `adapters/driven/config/toml_loader.py`: load/save atômico em `~/.config/rag_maker/config.toml` (XDG; usa `tomllib` + `tomli-w`) | Alta | F2.9 | Baixa | ✅ Concluído | ✓ |
| F3.2 | Adapters/Driven | `adapters/driven/ollama/manager.py`: `probe()`, `ensure_running()`, `spawn_daemon()` (subprocess + start_new_session), `list_models()`, `ensure_model(name, auto_pull)` | Alta | F1.16 | Média | ✅ Concluído | ✓ |
| F3.3 | Adapters/Driven | `adapters/driven/ollama/embedder.py`: `OllamaEmbedder` implementa `EmbedderPort` (batch + retry com backoff + dim validada; **nunca injeta vetor zero → levanta `EmbeddingError`**) | Alta | F2.5, F3.2 | Média | ✅ Concluído | ✓ |
| F3.4 | Adapters/Driven | `adapters/driven/loaders/pdf.py`: `PdfLoader` implementa `LoaderPort` (pypdf; marca página/seção; detecta PDF-imagem) | Alta | F2.8 | Média | ✅ Concluído | ✓ |
| F3.5 | Adapters/Driven | `adapters/driven/loaders/docx.py`: `DocxLoader` implementa `LoaderPort` (python-docx; headings → section) | Alta | F2.8 | Média | ✅ Concluído | ✓ |
| F3.6 | Adapters/Driven | `adapters/driven/loaders/epub.py`: `EpubLoader` implementa `LoaderPort` (ebooklib + beautifulsoup4) | Alta | F2.8 | Média | ✅ Concluído | ✓ |
| F3.7 | Adapters/Driven | `adapters/driven/loaders/text.py`: `TextLoader` implementa `LoaderPort` (.txt/.md/.markdown) | Alta | F2.8 | Baixa | ✅ Concluído | ✓ |
| F3.8 | Adapters/Driven | `adapters/driven/loaders/__init__.py`: registry plugável + `loader_for(path) -> LoaderPort` (factory) | Alta | F3.4, F3.5, F3.6, F3.7 | Média | ✅ Concluído | ✓ |
| F3.9 | Adapters/Driven | `adapters/driven/lancedb/vector_store.py`: `open_or_create`, schema (`id`, `vector`, `text`, `source_path`, `page`, `section`, `content_hash`, `mtime`), índice HNSW, índice FTS via tantivy | Alta | F2.6 | Alta | ✅ Concluído | ✓ |
| F3.10 | Adapters/Driven | `adapters/driven/lancedb/vector_store.py`: `upsert`, `delete_by_source`, `count`, `stats` (implementa `VectorStorePort`) | Alta | F3.9 | Média | ✅ Concluído | ✓ |
| F3.11 | Adapters/Driven | `adapters/driven/lancedb/vector_store.py`: `hybrid_search(vec, text, top_n)` usando `rrf_fuse` de `domain/scoring` | Alta | F3.10, F2.4 | Alta | ✅ Concluído | ✓ |
| F3.12 | Adapters/Driven | `adapters/driven/cross_encoder/reranker.py`: `CrossEncoderReranker` (sentence-transformers + BAAI/bge-reranker-v2-m3; singleton lazy) implementa `RerankerPort` | Alta | F2.7 | Média | ✅ Concluído | ✓ |
| F3.13 | Tests/Fixtures | `tests/fixtures/corpus_mini/`: 1 amostra por formato (pdf/docx/epub/txt/md), conteúdo curto e citável | Alta | F1.16 | Baixa | ✅ Concluído | ✓ |
| F3.14 | Tests/Integration | `tests/integration/test_toml_loader.py` (read/write/roundtrip + permissões XDG) | Alta | F3.1 | Baixa | ✅ Concluído | ✓ |
| F3.15 | Tests/Integration | `tests/integration/test_ollama_manager.py` via respx mockando 11434 (probe/spawn/list/pull) | Alta | F3.2 | Média | ✅ Concluído | ✓ |
| F3.16 | Tests/Integration | `tests/integration/test_ollama_embedder.py` via respx (batch, retry, dim mismatch, falha sem zero-vector) | Alta | F3.3 | Média | ✅ Concluído | ✓ |
| F3.17 | Tests/Integration | `tests/integration/test_loaders.py` (cada loader produz `Document` correto; registry escolhe loader certo) | Alta | F3.8, F3.13 | Média | ✅ Concluído | ✓ |
| F3.18 | Tests/Integration | `tests/integration/test_vector_store.py` (upsert + hybrid_search + delete_by_source + count) | Alta | F3.11 | Média | ✅ Concluído | ✓ |
| F3.19 | Tests/Integration | `tests/integration/test_reranker.py` (reordena chunks por relevância; singleton; CPU) | Alta | F3.12 | Média | ✅ Concluído | ✓ |
| F4.1 | Application | `application/ingest_use_case.py`: `IngestUseCase` recebe `EmbedderPort`, `VectorStorePort`, callable `loader_for`, `AppConfig` via construtor (DI) | Alta | F3.3, F3.11, F3.8, F2.9 | Média | ✅ Concluído | ✓ |
| F4.2 | Application | `application/ingest_use_case.py`: métodos `scan_changes` (mtime+sha256), `ingest_incremental`, `recreate_all` (idempotente e reportável) | Alta | F4.1 | Média | ✅ Concluído | ✓ |
| F4.3 | Application | `application/query_use_case.py`: `QueryUseCase` recebe `EmbedderPort`, `VectorStorePort`, `RerankerPort`; método `answer(query, top_k, alpha) -> QueryResult` | Alta | F3.3, F3.11, F3.12 | Média | ✅ Concluído | ✓ |
| F4.4 | Composition | `composition/container.py`: monta o grafo (TOML → `AppConfig` → adapters concretos → use cases), com hooks de override para testes (injeção de fakes via ports) | Alta | F4.1, F4.3 | Média | ✅ Concluído | ✓ |
| F4.5 | Tests/Integration | `tests/integration/test_ingest_use_case.py` (adapters reais + `corpus_mini`; verifica zero-vector proibido) | Alta | F4.2, F3.13 | Média | ✅ Concluído | ✓ |
| F4.6 | Tests/Integration | `tests/integration/test_query_use_case.py` (adapters reais + `corpus_mini`; verifica rerank_score decrescente) | Alta | F4.3, F3.13 | Média | ✅ Concluído | ✓ |
| F4.7 | Tests/Unit | `tests/unit/test_container.py` (composição correta + injeção de fakes via ports sem instanciar adapters reais) | Alta | F4.4 | Média | ✅ Concluído | ✓ |
| F5.1 | CLI | `adapters/driving/cli/main.py`: Typer app + Rich console + subcomandos stub | Alta | F4.4 | Baixa | ✅ Concluído | ✓ |
| F5.2 | CLI | Comando `rag status [--json]` (versão, paths, nº de docs/chunks, estado do Ollama) | Alta | F5.1 | Baixa | ✅ Concluído | ✓ |
| F5.3 | CLI | Comando `rag ingest [--corpus DIR] [--full] [--yes] [--json]` | Alta | F5.1, F4.2 | Média | ✅ Concluído | ✓ |
| F5.4 | CLI | Comando `rag query TEXTO [--top-k N] [--alpha F] [--json]` (stdout limpo, erros em stderr) | Alta | F5.1, F4.3 | Média | ✅ Concluído | ✓ |
| F5.5 | CLI | Comando `rag config get/set/path` (escrita atômica via `adapters/driven/config`) | Alta | F5.1, F2.9 | Média | ✅ Concluído | ✓ |
| F5.6 | CLI | Comando `rag ignore add/rm/list` (manipula `[ignored].paths` no TOML) | Alta | F5.1 | Baixa | ✅ Concluído | ✓ |
| F5.7 | CLI | Comando `rag doctor` (diagnóstico: Ollama, modelo bge-m3, reranker, permissões, espaço em disco) | Alta | F5.1 | Média | ✅ Concluído | ✓ |
| F5.8 | CLI | Exit codes padronizados (0 sucesso, 1 user error, 2 config, 3 Ollama, 4 modelo, 5 banco, 6 corpus vazio, 70 interno) documentados no `--help` | Alta | F5.2, F5.3, F5.4, F5.5, F5.6, F5.7 | Baixa | ✅ Concluído | ✓ |
| F5.9 | CLI | Entry point `rag` no `pyproject.toml` (`[project.scripts]`) | Alta | F5.1 | Baixa | ✅ Concluído | ✓ |
| F5.10 | AGENTS.md | Escrever `AGENTS.md` completo: schema v1, exemplos JSON reais, workflow recomendado, limites, códigos de erro, lista "não fazer" (ver plano) | Alta | F5.8 | Média | ✅ Concluído | ✓ |
| F5.11 | Tests/E2E | `tests/e2e/test_cli.py` via subprocess com `--json` (status, ingest dry-run, query, exit codes) | Alta | F5.8 | Média | ✅ Concluído | ✓ |
| F6.1 | GUI Qt6 | Adicionar `PySide6>=6.7` ao `pyproject.toml` (extra `gui`) + `pytest-qt` no extra `dev` | Média | F1.4 | Baixa | ✅ Concluído | ✓ |
| F6.2 | GUI Qt6 | `adapters/driving/gui/app.py`: `QApplication` + tema + global error handler + integração com `composition/container` | Média | F6.1, F4.4 | Média | ✅ Concluído | ✓ |
| F6.3 | GUI Qt6 | `adapters/driving/gui/main_window.py`: `QMainWindow` + abas (Corpus/Consulta/Settings) + statusbar | Média | F6.2 | Média | ✅ Concluído | ✓ |
| F6.4 | GUI Qt6 | `adapters/driving/gui/workers.py`: `IngestWorker`, `QueryWorker` em `QThread` com signals tipados; UI nunca bloqueia | Média | F4.2, F4.3 | Alta | ✅ Concluído | ✓ |
| F6.5 | GUI Qt6 | `adapters/driving/gui/widgets/corpus_panel.py`: seletor de pasta, tabela "arquivo/status/chunks/mtime", botões "Ingerir mudanças" e "Reconstruir tudo" | Média | F6.3, F6.4 | Média | ✅ Concluído | ✓ |
| F6.6 | GUI Qt6 | `adapters/driving/gui/widgets/query_panel.py`: campo de busca, slider `top_k`, tabela "score/arquivo/página/seção/trecho", duplo-clique abre no viewer do SO | Média | F6.3, F6.4 | Média | ✅ Concluído | ✓ |
| F6.7 | GUI Qt6 | `adapters/driving/gui/widgets/settings_panel.py`: form para editar TOML (paths, chunking, retrieval, reranker) | Média | F6.3, F2.9 | Média | ✅ Concluído | ✓ |
| F6.8 | GUI Qt6 | StatusBar com estado do Ollama (verde/amarelo/vermelho) + modelo carregado + contador de chunks no banco | Média | F6.3 | Baixa | ✅ Concluído | ✓ |
| F6.9 | GUI Qt6 | Entry point `rag-gui` no `pyproject.toml` (`[project.scripts]`) | Média | F1.4 | Baixa | ✅ Concluído | ✓ |
| F6.10 | GUI Qt6 | Smoke test manual (WCAG AA: contraste, navegação por teclado, focus visível): abrir, ingerir mini corpus, rodar query | Média | F6.9 | Baixa | ✅ Concluído | ✓ |
| F7.1 | Polimento | Shell completion Typer (`rag --install-completion`) | Baixa | F5.1 | Baixa | ✅ Concluído | ✓ |
| F7.2 | Polimento | `scripts/benchmark_retrieval.py` (latência por etapa do pipeline: embed/search/rerank) | Baixa | F4.3 | Média | ✅ Concluído | ✓ |
| F7.3 | Polimento | `README.md` (quickstart humano, stack, screenshots da GUI, troubleshooting, link para AGENTS.md) | Média | F5.10, F6.10 | Baixa | ✅ Concluído | ✓ |
| F7.4 | Polimento | `.pre-commit-config.yaml` (ruff check/format + mypy + bandit + lint-imports + pytest unit curto) | Baixa | F1.6, F1.7, F1.13, F1.14 | Baixa | ✅ Concluído | ✓ |
| F7.5 | Distribuição | `uv build` → wheel + sdist em `dist/`; verificar metadata | Média | F7.4 | Baixa | ✅ Concluído | ✓ |
| F7.6 | Distribuição | Testar `pipx install dist/*.whl` em ambiente limpo (binários `rag` e `rag-gui` no PATH) | Média | F7.5 | Baixa | 🔍 Pendente verificação | — |
| F7.7 | Distribuição | Commit final (Conventional Commits) + tag `v0.1.0` | Média | F7.6 | Baixa | ⏳ Pendente | — |
