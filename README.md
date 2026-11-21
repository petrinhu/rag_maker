# rag-maker

[![Release](https://img.shields.io/github/v/release/petrinhu/rag_maker?display_name=tag&sort=semver&label=release)](https://github.com/petrinhu/rag_maker/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![uv](https://img.shields.io/badge/managed%20by-uv-purple)](https://github.com/astral-sh/uv)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64.svg)](https://github.com/astral-sh/ruff)
[![Typed: mypy strict](https://img.shields.io/badge/typed-mypy%20strict-blue.svg)](https://mypy-lang.org/)

**[English version below](#english)**

Ferramenta de **recuperação offline** (retrieval-only) para bibliotecas pessoais de documentos. Indexa PDF, DOCX, EPUB, TXT e Markdown em banco vetorial local; expõe trechos relevantes via **CLI** ou **GUI**, para que IAs externas (Claude Code, ChatGPT, Gemini) redijam resumos, artigos e livros com citações reais.

> **Não é um RAG completo.** Não gera respostas, não usa LLM local para síntese. Único modelo local: `bge-m3:latest` (embeddings via Ollama). Quem redige é a IA externa.

---

## Stack

| Camada | Tecnologia |
|:---|:---|
| Linguagem | Python 3.11+ |
| Empacotamento | [`uv`](https://github.com/astral-sh/uv) + `pyproject.toml` (PEP 621) |
| Embeddings | [Ollama](https://ollama.ai) + `bge-m3:latest` (dim=1024) |
| Vetor + lexical | [LanceDB](https://lancedb.com/) (HNSW cosine + FTS via tantivy, fusão RRF) |
| Reranking | [`sentence-transformers`](https://www.sbert.net/) + `BAAI/bge-reranker-v2-m3` |
| Loaders | `pypdf`, `python-docx`, `ebooklib`+`beautifulsoup4` |
| CLI | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) |
| GUI | [PySide6](https://doc.qt.io/qtforpython-6/) (Qt 6) |
| Config | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) + TOML em `~/.config/rag_maker/config.toml` |
| Testes | `pytest`, `pytest-qt`, `pytest-cov`, `hypothesis`, `respx` |
| Qualidade | `ruff`, `mypy --strict`, `bandit`, `pip-audit`, `import-linter` |

---

## Arquitetura

Hexagonal (Ports & Adapters), 4 camadas com dependência unidirecional:

```
src/rag_maker/
├── domain/            # nucleo puro; zero I/O, zero libs externas
│   ├── models.py      # frozen dataclasses + excecoes
│   ├── chunker.py     # RecursiveCharacterChunker
│   ├── scoring.py     # rrf_fuse
│   └── ports/         # Protocols: EmbedderPort, VectorStorePort, RerankerPort, LoaderPort
├── application/       # use cases, so dependem de ports
│   ├── config.py
│   ├── ingest_use_case.py
│   └── query_use_case.py
├── adapters/
│   ├── driving/       # primarios: CLI, GUI
│   │   ├── cli/       # Typer + Rich
│   │   └── gui/       # PySide6
│   └── driven/        # secundarios: I/O via ports
│       ├── ollama/    # EmbedderPort
│       ├── lancedb/   # VectorStorePort
│       ├── cross_encoder/  # RerankerPort
│       ├── loaders/   # LoaderPort (pdf/docx/epub/text)
│       └── config/    # TOML loader
└── composition/       # wiring/DI
    └── container.py
```

**Regras invioláveis** (validadas por `import-linter`):

1. `domain/` nunca importa de `adapters/`, `application/`, libs externas, ou stdlib de I/O.
2. `application/` só conhece `domain/` (inclui `domain/ports/`).
3. `adapters/driven/` implementam Protocols de `domain/ports/`.
4. `adapters/driving/` só conversam com `application/` via `composition/container`.
5. Libs externas (lancedb, ollama, pypdf, PySide6, etc.) só aparecem em `adapters/`.

---

## Pré-requisitos

```bash
# 1. Ollama instalado + modelo de embedding baixado
ollama pull bge-m3:latest

# 2. uv (gerenciador de pacotes Python)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Instalação

### Como usuário (binários `rag` e `rag-gui` no PATH)

```bash
uv tool install git+https://github.com/petrinhu/rag_maker.git
```

Ou via wheel publicado em releases:

```bash
pipx install https://github.com/petrinhu/rag_maker/releases/download/vX.Y.Z/rag_maker-X.Y.Z-py3-none-any.whl
```

### Para desenvolvimento

```bash
git clone https://github.com/petrinhu/rag_maker.git
cd rag_maker
uv sync --all-extras
uv run pytest
```

---

## Uso: CLI (`rag`)

```bash
# Apontar pasta com seus documentos
rag config set paths.corpus_dir ~/biblioteca

# Indexar (incremental: so novos/modificados)
rag ingest

# Reconstruir do zero
rag ingest --full --yes

# Buscar
rag query "filosofia da linguagem em Wittgenstein"
rag query "..." --json --top-k 8     # saida JSON para consumo de IA

# Estado
rag status              # paths, contagem de chunks, Ollama
rag doctor              # diagnostico completo
rag config path         # caminho do TOML

# Ignorar caminhos
rag ignore add ~/biblioteca/rascunhos
rag ignore list
rag ignore rm ~/biblioteca/rascunhos
```

### Exit codes

| Código | Significado |
|:---:|:---|
| 0 | Sucesso |
| 1 | Erro de usuário (args inválidos) |
| 2 | Erro de configuração |
| 3 | Ollama indisponível |
| 4 | Modelo de embedding não encontrado |
| 5 | Erro no banco vetorial |
| 6 | Corpus vazio, sem dados indexados |
| 70 | Erro interno |

---

## Uso: GUI (`rag-gui`)

```bash
rag-gui
```

Três abas:

- **Corpus**: seletor de pasta (drag&drop), tabela "Obra / Status / Chunks / Caminho" com filtros por status (Novo, Modificado, Indexado, Removido) e busca por nome. Botões "Ingerir mudanças" / "Reconstruir tudo" com progresso em tempo real, pausar/parar e notificações de sistema para operações longas (>10s). Duplo-clique abre o arquivo no viewer do SO.
- **Consulta**: campo de busca, slider `top_k`, tabela "Score / Arquivo / Página / Seção / Trecho". Duplo-clique abre o documento.
- **Configurações**: formulário para editar paths, Ollama, chunking, retrieval, reranker. `DB dir` é read-only (derivado do corpus). Botão "Detectar" auto-localiza o Ollama. Trocar a pasta do corpus aqui propaga para a aba Corpus e recria/lê o `rag/` da nova pasta automaticamente.

StatusBar: estado do Ollama (verde/amarelo/vermelho), modelo carregado, contador de chunks.

Workers em `QThread`: UI nunca bloqueia durante ingestão ou query.

---

## `LLM.md`: Contrato para IAs externas

O arquivo `LLM.md` na raiz é um **contrato formal** que orienta agentes LLM (Claude Code, ChatGPT, Gemini, etc.) sobre como invocar a CLI `rag` e interpretar resultados.

Contém:

- O que a ferramenta faz e quando usar.
- Comandos exatos com flags recomendadas.
- Schema JSON da saída de `rag query --json` (chunk_id, text, source_path, page, section, rerank_score, rrf_score).
- Workflow recomendado: `rag status`, depois `rag query`, depois citar.
- Lista explícita do que **não fazer** (inferir conteúdo não retornado, inventar referências, ignorar exit codes).
- Códigos de erro e como reagir a cada um.

Agentes devem ler `LLM.md` antes da primeira invocação e respeitar os contratos lá descritos.

**Onde achar `LLM.md`:**

- Clone do repo: `./LLM.md` na raiz.
- Install via `uv tool install` ou `pipx install`: o arquivo não vai dentro da wheel. Aponte o agente para a URL canônica:
  ```
  https://raw.githubusercontent.com/petrinhu/rag_maker/main/LLM.md
  ```

Instrução padrão para colar no prompt do agente:

> "Antes de invocar a CLI `rag`, leia o contrato em https://raw.githubusercontent.com/petrinhu/rag_maker/main/LLM.md e siga as regras documentadas (schema JSON, exit codes, workflow recomendado)."

---

## Configuração

Arquivo TOML em `~/.config/rag_maker/config.toml` (XDG). Override por env var: `RAG_MAKER_*` com `__` como separador aninhado.

```toml
[paths]
corpus_dir = "/home/usuario/biblioteca"
# db_dir e derivado de corpus_dir/rag, nao edite

[ollama]
url = "http://127.0.0.1:11434"
embedding_model = "bge-m3:latest"
timeout_seconds = 180
auto_pull = false        # true = baixa o modelo automaticamente se faltar

[chunking]
size = 1000
overlap = 200

[retrieval]
coarse_top_n = 100
rerank_top_k = 8
alpha = 0.5              # reservado para uso futuro; ainda nao implementado, sem efeito

[reranker]
model = "BAAI/bge-reranker-v2-m3"
device = "auto"          # "auto" | "cpu" | "cuda" | "mps"
revision = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41"  # opcional, ver "Integridade dos modelos" abaixo

[gui]
recursive_scan = true
```

Override por env:

```bash
RAG_MAKER_OLLAMA__EMBEDDING_MODEL=other-model:latest rag query "..."
```

### Integridade dos modelos (pin de revisão)

`rag-maker` baixa dois modelos de tags/branches mutáveis por padrão: o embedder via Ollama
(`bge-m3:latest`) e o reranker via HuggingFace Hub (`BAAI/bge-reranker-v2-m3`, branch `main`).
Tag/branch mutável significa que o mantenedor (ou uma conta comprometida no registro upstream)
pode republicar pesos diferentes sob o mesmo nome, e a próxima instalação ou carregamento
incorpora isso silenciosamente, sem erro, sem aviso.

- **Reranker (HuggingFace):** fixe `[reranker].revision` com um commit SHA específico do
  repositório do modelo (ver histórico de commits em
  [huggingface.co/BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)).
  Com `revision` definido, `CrossEncoder` resolve exatamente aquele commit, não `main`.
  Deixe em branco (`revision` ausente, o default é `None`) só se você aceita conscientemente
  resolver a branch mutável a cada carregamento: atualização deliberada é trocar o SHA e
  revisar o changelog do modelo antes.
- **Embedder (Ollama):** prefira referenciar o modelo por digest sha256 em vez da tag
  `:latest`, por exemplo `embedding_model = "bge-m3@sha256:<digest>"` (descubra o digest com
  `ollama show bge-m3:latest --modelfile` ou no registry). Isso fixa exatamente os pesos
  puxados, de forma análoga ao `revision` do reranker.
- **`auto_pull = true`:** esse flag deixa o `rag-maker` puxar (`ollama pull`) o modelo
  automaticamente se ele não existir localmente, sem verificação de hash contra um valor
  esperado. Isso implica **confiar no que a tag/digest resolver no momento do pull**. Se você
  fixou `embedding_model` por digest, o risco é baixo (o digest é o próprio hash do conteúdo);
  se ficou com a tag `:latest`, `auto_pull=true` puxa o que estiver publicado sob essa tag
  naquele instante, sem re-verificação posterior. Default é `false` (opt-in explícito).

---

## Testes

```bash
uv run pytest                              # tudo
uv run pytest -m unit                      # so unit
uv run pytest -m integration               # integracao (sem rede via respx)
uv run pytest -m e2e                       # CLI end-to-end via subprocess
uv run pytest --cov=src/rag_maker          # cobertura
```

Quality gates rodam em CI: `ruff check`, `mypy --strict`, `bandit -r src/`, `lint-imports`, `pip-audit`.

---

## Licença

AGPL-3.0, ver [LICENSE](LICENSE).

---

<a id="english"></a>

# rag-maker (English)

[![Release](https://img.shields.io/github/v/release/petrinhu/rag_maker?display_name=tag&sort=semver&label=release)](https://github.com/petrinhu/rag_maker/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

Offline **retrieval-only** tool for personal document libraries. Indexes PDF, DOCX, EPUB, TXT, Markdown into a local vector store; serves relevant chunks via **CLI** or **GUI**, so external AIs (Claude Code, ChatGPT, Gemini) can write summaries, articles, and books with real citations.

> **Not a full RAG.** No answer generation, no local synthesis LLM. Only local model: `bge-m3:latest` (embeddings via Ollama). External AI does the writing.

---

## Stack

| Layer | Technology |
|:---|:---|
| Language | Python 3.11+ |
| Packaging | [`uv`](https://github.com/astral-sh/uv) + `pyproject.toml` (PEP 621) |
| Embeddings | [Ollama](https://ollama.ai) + `bge-m3:latest` (dim=1024) |
| Vector + lexical | [LanceDB](https://lancedb.com/) (HNSW cosine + FTS via tantivy, RRF fusion) |
| Reranking | [`sentence-transformers`](https://www.sbert.net/) + `BAAI/bge-reranker-v2-m3` |
| Loaders | `pypdf`, `python-docx`, `ebooklib`+`beautifulsoup4` |
| CLI | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/) |
| GUI | [PySide6](https://doc.qt.io/qtforpython-6/) (Qt 6) |
| Config | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) + TOML at `~/.config/rag_maker/config.toml` |
| Tests | `pytest`, `pytest-qt`, `pytest-cov`, `hypothesis`, `respx` |
| Quality | `ruff`, `mypy --strict`, `bandit`, `pip-audit`, `import-linter` |

---

## Architecture

Hexagonal (Ports & Adapters), 4 layers, unidirectional dependency:

```
src/rag_maker/
├── domain/            # pure core; zero I/O, zero external libs
├── application/       # use cases, depend only on ports
├── adapters/
│   ├── driving/       # primary: CLI (Typer+Rich), GUI (PySide6)
│   └── driven/        # secondary: ollama, lancedb, cross_encoder, loaders, config
└── composition/       # wiring/DI
```

**Inviolable rules** (enforced by `import-linter`):

1. `domain/` never imports from `adapters/`, `application/`, external libs, or I/O stdlib.
2. `application/` only knows `domain/`.
3. `adapters/driven/` implement `domain/ports/` Protocols.
4. `adapters/driving/` only talk to `application/` via `composition/container`.
5. External libs (lancedb, ollama, pypdf, PySide6, etc.) only in `adapters/`.

---

## Prerequisites

```bash
ollama pull bge-m3:latest
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Install

### As user

```bash
uv tool install git+https://github.com/petrinhu/rag_maker.git
```

Or via wheel from releases:

```bash
pipx install https://github.com/petrinhu/rag_maker/releases/download/vX.Y.Z/rag_maker-X.Y.Z-py3-none-any.whl
```

### For development

```bash
git clone https://github.com/petrinhu/rag_maker.git
cd rag_maker
uv sync --all-extras
uv run pytest
```

---

## CLI usage (`rag`)

```bash
rag config set paths.corpus_dir ~/library
rag ingest                              # incremental
rag ingest --full --yes                 # rebuild from scratch
rag query "philosophy of language in Wittgenstein"
rag query "..." --json --top-k 8        # JSON for AI consumption
rag status
rag doctor
rag config path
rag ignore add ~/library/drafts
rag ignore list
rag ignore rm ~/library/drafts
```

### Exit codes

| Code | Meaning |
|:---:|:---|
| 0 | Success |
| 1 | User error (invalid args) |
| 2 | Configuration error |
| 3 | Ollama unreachable |
| 4 | Embedding model not found |
| 5 | Vector store error |
| 6 | Empty corpus, no indexed data |
| 70 | Internal error |

---

## GUI usage (`rag-gui`)

```bash
rag-gui
```

Three tabs:

- **Corpus**: folder picker (drag&drop), table "Document / Status / Chunks / Path" with filters by status (New, Modified, Indexed, Removed) and filename search. "Ingest changes" / "Rebuild all" buttons with real-time progress, pause/stop, system notifications for long ops (>10s). Double-click opens file in OS viewer.
- **Query**: search field, `top_k` slider, table "Score / File / Page / Section / Excerpt". Double-click opens document.
- **Settings**: form for paths, Ollama, chunking, retrieval, reranker. `DB dir` is read-only (derived from corpus). "Detect" auto-locates Ollama. Changing corpus folder here propagates to Corpus tab and auto-creates/reads new `rag/` folder.

StatusBar: Ollama state (green/yellow/red), loaded model, chunk count.

Workers in `QThread`: UI never blocks.

---

## `LLM.md`: Contract for external AIs

The `LLM.md` file at repo root is a **formal contract** that instructs LLM agents (Claude Code, ChatGPT, Gemini, etc.) on how to invoke the `rag` CLI and interpret results.

It contains:

- What the tool does, when to use it.
- Exact commands with recommended flags.
- JSON schema of `rag query --json` output (chunk_id, text, source_path, page, section, rerank_score, rrf_score).
- Recommended workflow: `rag status`, then `rag query`, then cite.
- Explicit list of what **not to do** (infer content not returned, fabricate references, ignore exit codes).
- Error codes and how to react.

Agents should read `LLM.md` before first use and respect the documented contracts.

**Where to find `LLM.md`:**

- Repo clone: `./LLM.md` at root.
- Installed via `uv tool install` or `pipx install`: file is not bundled in the wheel. Point the agent at the canonical URL:
  ```
  https://raw.githubusercontent.com/petrinhu/rag_maker/main/LLM.md
  ```

Standard instruction to paste into the agent prompt:

> "Before invoking the `rag` CLI, read the contract at https://raw.githubusercontent.com/petrinhu/rag_maker/main/LLM.md and follow the documented rules (JSON schema, exit codes, recommended workflow)."

---

## Configuration

TOML at `~/.config/rag_maker/config.toml` (XDG). Override via env: `RAG_MAKER_*` with `__` as nested separator. See pt-br section above for full TOML example.

> Note: `[retrieval].alpha` is reserved for future use; not implemented yet, has no effect.

```bash
RAG_MAKER_OLLAMA__EMBEDDING_MODEL=other-model:latest rag query "..."
```

### Model integrity (revision pinning)

`rag-maker` downloads two models from mutable tags/branches by default: the embedder via
Ollama (`bge-m3:latest`) and the reranker via HuggingFace Hub (`BAAI/bge-reranker-v2-m3`,
`main` branch). A mutable tag/branch means the maintainer (or a compromised account on the
upstream registry) can republish different weights under the same name, and the next install
or load silently picks that up: no error, no warning.

- **Reranker (HuggingFace):** pin `[reranker].revision` to a specific commit SHA of the model
  repository (see commit history at
  [huggingface.co/BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)).
  With `revision` set, `CrossEncoder` resolves exactly that commit, not `main`. Leave it blank
  (`revision` absent, default is `None`) only if you knowingly accept resolving the mutable
  branch on every load: a deliberate update means bumping the SHA and reviewing the model
  changelog first.
- **Embedder (Ollama):** prefer referencing the model by sha256 digest instead of the
  `:latest` tag, for example `embedding_model = "bge-m3@sha256:<digest>"` (find the digest
  with `ollama show bge-m3:latest --modelfile` or on the registry). This pins the exact
  weights pulled, analogous to the reranker's `revision`.
- **`auto_pull = true`:** this flag lets `rag-maker` pull (`ollama pull`) the model
  automatically when missing locally, with no hash check against an expected value. It
  implies **trusting whatever the tag/digest resolves to at pull time**. If you pinned
  `embedding_model` by digest, the risk is low (the digest is the content hash itself); if
  you kept the `:latest` tag, `auto_pull=true` pulls whatever is published under that tag at
  that moment, with no later re-verification. Default is `false` (explicit opt-in).

---

## Tests

```bash
uv run pytest                              # all
uv run pytest -m unit                      # unit only
uv run pytest -m integration               # integration (no network via respx)
uv run pytest -m e2e                       # CLI end-to-end via subprocess
uv run pytest --cov=src/rag_maker          # coverage
```

Quality gates in CI: `ruff check`, `mypy --strict`, `bandit -r src/`, `lint-imports`, `pip-audit`.

---

## License

AGPL-3.0, see [LICENSE](LICENSE).
