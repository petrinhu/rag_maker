# rag-maker

Ferramenta de **recuperação offline** (retrieval-only) para bibliotecas pessoais de documentos. Indexa PDF, DOCX, EPUB, TXT e Markdown num banco vetorial local e expõe os trechos mais relevantes via CLI ou GUI — para que IAs externas (Claude Code, ChatGPT, Gemini) redijam resumos, artigos e livros com citações reais.

> **Não é um RAG completo.** Não gera respostas, não usa LLM local para síntese. O único modelo local é o `bge-m3:latest` (embeddings via Ollama). Quem redige é a IA externa.

---

## Quickstart

### Pré-requisitos

| Ferramenta | Versão mínima |
|:---|:---|
| Python | 3.11+ |
| [uv](https://github.com/astral-sh/uv) | 0.4+ |
| [Ollama](https://ollama.ai) | qualquer versão recente |

```bash
# 1. Instalar o Ollama e baixar o modelo de embedding
ollama pull bge-m3:latest

# 2. Instalar o rag-maker
uv tool install git+https://codeberg.org/petrinhu/rag_maker.git

# 3. Configurar a pasta do corpus
rag config set paths.corpus_dir /caminho/para/seus/livros

# 4. Ingerir documentos
rag ingest

# 5. Consultar
rag query "filosofia da linguagem em Wittgenstein" --json --top-k 8
```

---

## Instalação para desenvolvimento

```bash
git clone https://codeberg.org/petrinhu/rag_maker.git
cd rag_maker
uv sync --extra dev --extra gui
uv run pytest
```

---

## Comandos da CLI

```
rag status [--json]                    # estado: Ollama, banco, chunks
rag ingest [--corpus DIR] [--full]     # ingerir corpus (incremental por padrão)
rag query TEXTO [--top-k N] [--json]   # recuperar trechos ranqueados
rag config get [KEY]                   # ler configuração
rag config set KEY VALUE               # alterar configuração (escrita atômica)
rag config path                        # mostrar caminho do config.toml
rag ignore add|rm|list [PATH]          # gerenciar caminhos ignorados
rag doctor                             # diagnóstico do ambiente
rag --version
```

Exit codes: `0` OK · `1` erro de uso · `2` config inválida · `3` Ollama off · `4` modelo ausente · `5` banco corrompido · `6` corpus vazio · `70` erro interno.

---

## GUI (PySide6)

```bash
rag-gui
```

Abre uma janela com três abas: **Corpus** (selecionar pasta, ingerir), **Consulta** (busca + tabela ranqueada, duplo-clique abre o arquivo) e **Configurações** (editar TOML via formulário). A statusbar mostra o estado do Ollama e o número de chunks indexados, atualizando a cada 10 s.

---

## Stack

| Camada | Tecnologia |
|:---|:---|
| Embeddings | Ollama HTTP API — `bge-m3:latest` (dim=1024) |
| Banco vetorial | LanceDB ≥ 0.10 — HNSW cosine + FTS (tantivy/BM25) |
| Fusão de rankings | RRF (Reciprocal Rank Fusion) |
| Reranker | `BAAI/bge-reranker-v2-m3` via sentence-transformers |
| Loaders | pypdf, python-docx, ebooklib + beautifulsoup4, stdlib |
| Chunker | RecursiveCharacterTextSplitter (langchain-text-splitters) |
| CLI | Typer + Rich |
| GUI | PySide6 ≥ 6.7 |
| Config | TOML (tomllib + tomli-w) + pydantic-settings |
| Arquitetura | Hexagonal (Ports & Adapters) — `domain/`, `application/`, `adapters/`, `composition/` |

---

## Para IAs externas

Leia o **[AGENTS.md](AGENTS.md)** — contrato formal que descreve como chamar a CLI, o schema JSON de saída, como citar os trechos e quando não usar a ferramenta.

---

## Configuração

O arquivo de configuração fica em `~/.config/rag_maker/config.toml` (XDG). Um exemplo comentado está em [`rag_maker.toml.example`](rag_maker.toml.example).

```toml
[paths]
corpus_dir = "/home/user/biblioteca"

[ollama]
embedding_model = "bge-m3:latest"
auto_pull       = false

[chunking]
size    = 1000
overlap = 200

[retrieval]
coarse_top_n = 100
rerank_top_k = 8
```

---

## Troubleshooting

| Sintoma | Solução |
|:---|:---|
| `Ollama indisponível` (exit 3) | Execute `ollama serve` ou inicie o serviço systemd do Ollama |
| `Modelo não encontrado` (exit 4) | `ollama pull bge-m3:latest` |
| `Corpus vazio` (exit 6) | Execute `rag ingest` ou `rag config set paths.corpus_dir /caminho` |
| GUI não abre (Wayland) | `QT_QPA_PLATFORM=xcb rag-gui` |
| Reranker lento na 1ª query | Normal — o modelo (~500 MB) carrega na primeira chamada |

---

## Licença

[PolyForm Noncommercial License 1.0.0](LICENSE) — uso não-comercial livre; uso comercial proibido.
