# AI Coder Contract — rag_maker (Python Hexagonal Project)

> **Audience:** AI coding agents (Claude Code, ChatGPT, Gemini, Copilot, etc.) trabalhando no projeto `rag_maker`.
> **Purpose:** Referencia obrigatoria ANTES de escrever, modificar ou revisar qualquer linha de codigo Python neste repositorio.
> **Authority:** Regras usam palavras-chave RFC 2119 — **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, **MAY**.
> **Testing & Audit:** Todos os procedimentos de teste, auditoria e qualidade estao em [TESTES.md](TESTES.md). Este contrato aponta o que rodar e quando; o COMO esta la.
> **Pendencias:** A tabela de tarefas aprovadas esta em [TODO.md](TODO.md). Nenhuma linha de codigo **MUST** ser escrita sem uma tarefa ID correspondente.

---

## Table of Contents

1. [How to Use This Document](#1-how-to-use-this-document)
2. [Python Fundamentals for this Project](#2-python-fundamentals-for-this-project)
3. [SOLID Principles (Python Edition)](#3-solid-principles-python-edition)
4. [Design Patterns — Python Edition](#4-design-patterns--python-edition)
5. [Architecture Layers (Hexagonal + Front/Mid/Back)](#5-architecture-layers-hexagonal--frontmidback)
6. [Clean Code Rules (Python)](#6-clean-code-rules-python)
7. [UI/UX Guidelines for PySide6](#7-uiux-guidelines-for-pyside6)
8. [Security](#8-security)
9. [Performance](#9-performance)
10. [Git Process](#10-git-process)
11. [Testing & Audit Mandate](#11-testing--audit-mandate)
12. [Python-Specific Rules](#12-python-specific-rules)
13. [Framework-Specific Rules](#13-framework-specific-rules)

---

## 1. How to Use This Document

### 1.1 Decision Flow para a IA

```
Nova solicitacao recebida
      |
      v
Ler TODO.md: existe tarefa aprovada para isto?
      |-- Nao --> PARAR. Pedir que o usuario registre a pendencia e aprove.
      |
      v
Ler os arquivos que serao modificados (Read tool) ANTES de qualquer edicao
      |
      v
Identificar a camada afetada (domain / application / adapters.driving / adapters.driven / composition)
      |
      v
Aplicar regras desta secao 5 (quem pode importar quem) e das secoes 3, 4, 6
      |
      v
Escrever codigo em Python 3.11+ com type hints e from __future__ import annotations
      |
      v
Rodar: ruff check . && mypy --strict src && pytest
      |
      v
Zero violations + zero errors + zero failures?
      |-- Nao --> Corrigir antes de commitar.
      |
      v
Commit com Conventional Commits (ver secao 10)
      |
      v
Done
```

### 1.2 Checklist Pre-Escrita (obrigatorio)

```
[ ] Existe tarefa em TODO.md autorizada para esta mudanca?
[ ] Ja li o arquivo que vou modificar (nunca editar as cegas)?
[ ] Identifiquei a camada: domain / application / adapters.driving.* / adapters.driven.* / composition?
[ ] Estou respeitando a regra da seta Frontend -> Middleware -> Backend <- Infrastructure?
[ ] Nenhum import de lancedb, ollama, pypdf, PySide6, sentence_transformers vai dentro de domain/ ou application/?
[ ] Vou usar type hints modernos (list[str], X | None, nao List[str] / Optional[X])?
[ ] Vou adicionar from __future__ import annotations no topo do arquivo?
[ ] Todo novo Protocol vai em domain/ports/?
[ ] Toda nova lib externa vai isolada em um unico adapter em adapters/driven/?
```

### 1.3 O Que a IA NUNCA Deve Fazer

- **MUST NOT** escrever codigo sem tarefa autorizada em `TODO.md`.
- **MUST NOT** remover ou alterar arquivos em `legacy/` — e somente-leitura e serve de referencia historica.
- **MUST NOT** introduzir LLM local para sintese. O projeto e retrieval-only; a sintese e feita por IA externa consumindo chunks via CLI.
- **MUST NOT** importar `lancedb`, `ollama`, `sentence_transformers`, `pypdf`, `PySide6`, `typer`, `rich` em `domain/` ou `application/`.
- **MUST NOT** escrever `from typing import List, Dict, Optional, Tuple` — use `list`, `dict`, `X | None`, `tuple` (PEP 585 / 604).
- **MUST NOT** usar `except Exception: pass`. Sempre logar e/ou re-levantar.
- **MUST NOT** injetar vetor zero como fallback quando embedding falhar. Lance `EmbeddingError`.
- **MUST NOT** commitar segredos. A config fica em `~/.config/rag_maker/config.toml` (fora do repo).
- **MUST NOT** reescrever codigo-fonte Python em runtime. Estado mutavel **MUST** ir em TOML.
- **MUST NOT** usar `type: ignore` sem comentario justificando.
- **MUST NOT** usar funcao de impressao direta em codigo de producao — sempre `structlog`.
- **MUST NOT** usar `--no-verify` em commits nem fazer force-push em `main`.

---

## 2. Python Fundamentals for this Project

### 2.1 Versao e Ferramentas

| Item | Regra |
|---|---|
| Python | **MUST** ser >= 3.11. CI trava versao. |
| Gerenciador | `uv` + `pyproject.toml` + `uv.lock`. **MUST NOT** usar instalacoes sem lockfile. |
| Lint | `ruff` (substitui flake8, isort, pyupgrade). Zero violations permitidas. |
| Type check | `mypy --strict`. Zero `Any` implicito. |
| Test | `pytest`, `pytest-cov`, `hypothesis`, `respx`. |
| Logging | `structlog`. Nunca a funcao de impressao em src/. |

### 2.2 Type Hints sao Contrato

Type hints sao obrigatorios em todo codigo em `src/`. Mypy roda com `--strict`. Exemplos do dominio real:

```python
# INCORRECT
def embed(texts):
    return [[0.0] * 1024 for _ in texts]

# CORRECT
from __future__ import annotations

def embed(texts: list[str]) -> list[list[float]]:
    ...
```

```python
# INCORRECT — tipagem fraca
def buscar(q, k=10):
    ...

# CORRECT — tipagem forte com dominio
from __future__ import annotations
from rag_maker.domain.models import Chunk, Query

def buscar(query: Query, *, k: int = 10) -> list[Chunk]:
    ...
```

**Regras:**
- **MUST** usar `from __future__ import annotations` no topo de TODO arquivo `.py` em `src/`.
- **MUST** preferir `list[T]`, `dict[K, V]`, `tuple[A, B]`, `X | None` (PEP 585 / 604).
- **MUST NOT** usar `List`, `Dict`, `Optional`, `Union`, `Tuple` do `typing` — obsoletos.
- **SHOULD** usar `Iterable[T]` / `Sequence[T]` / `Mapping[K, V]` em parametros publicos.
- **MUST** tipar retorno explicitamente. Funcoes sem return anotado sao rejeitadas.

### 2.3 Frozen Dataclasses

Modelos do dominio sao imutaveis. Use `@dataclass(frozen=True, slots=True, kw_only=True)`.

```python
# CORRECT — modelo imutavel e slotted
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True, slots=True, kw_only=True)
class Chunk:
    id: str
    text: str
    source: Path
    page: int | None
    vector: tuple[float, ...]  # tuplas imutaveis, nao listas

# INCORRECT — mutavel, sem slots
@dataclass
class Chunk:
    id: str
    text: str
    vector: list[float]  # mutavel, permite bug por alias
```

**Regras:**
- **MUST** marcar `frozen=True` em todo modelo de `domain/models.py`.
- **MUST** marcar `slots=True` (economia de memoria e previne atributos acidentais).
- **MUST** marcar `kw_only=True` (chamadas explicitas, nunca posicionais).
- **MUST** usar `tuple[float, ...]` em vez de `list[float]` para vetores armazenados em modelos.

### 2.4 Protocols (Structural Typing)

Portas (contratos hexagonais) sao `typing.Protocol`. NUNCA classes abstratas (`ABC`) para ports — Protocols sao duck typing verificado estaticamente.

```python
# CORRECT — porta em domain/ports/embedder.py
from __future__ import annotations
from typing import Protocol

class EmbedderPort(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    @property
    def dim(self) -> int: ...
```

```python
# INCORRECT — nao use ABC para ports
from abc import ABC, abstractmethod

class EmbedderPort(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

- **MUST** usar `Protocol` para toda porta em `domain/ports/`.
- **MUST NOT** colocar implementacao em Protocol (sem `raise NotImplementedError`).
- **MAY** usar `@runtime_checkable` SOMENTE quando `isinstance` for genuinamente necessario (raro).

### 2.5 pathlib (Nunca os.path)

```python
# INCORRECT
import os
config_path = os.path.join(os.path.expanduser("~"), ".config", "rag_maker", "config.toml")
if os.path.exists(config_path):
    ...

# CORRECT
from pathlib import Path
config_path = Path.home() / ".config" / "rag_maker" / "config.toml"
if config_path.exists():
    ...
```

### 2.6 Context Managers para Recursos

Toda abertura de arquivo, conexao ou recurso **MUST** usar `with`.

```python
# INCORRECT
f = open(path, "rb")
data = f.read()
f.close()  # vaza se .read() levantar

# CORRECT
with path.open("rb") as f:
    data = f.read()
```

Para recursos proprios, implemente `__enter__` / `__exit__` (ou use `contextlib.contextmanager`):

```python
from __future__ import annotations
from contextlib import contextmanager
from typing import Iterator
import lancedb

@contextmanager
def open_lancedb(uri: Path) -> Iterator[lancedb.DBConnection]:
    db = lancedb.connect(uri)
    try:
        yield db
    finally:
        # lancedb nao exige close explicito, mas deixamos o hook pronto
        pass
```

---

## 3. SOLID Principles (Python Edition)

Todos os exemplos usam o dominio real: `EmbedderPort`, `OllamaEmbedder`, `VectorStorePort`, `LanceDbVectorStore`, `RerankerPort`, `LoaderPort`, `PdfLoader`, `IngestUseCase`, `QueryUseCase`.

### 3.1 S — Single Responsibility Principle

> Uma classe (ou modulo) tem uma unica razao para mudar.

```python
# INCORRECT — uma classe carrega ingestao, embedding, storage e scoring
class RagService:
    def ingest(self, path: Path) -> None:
        # le PDF, divide, embeda, salva, reindexa, loga
        ...
    def query(self, q: str) -> list[Chunk]:
        # embeda query, busca vetorial, FTS, fusion, rerank, formata
        ...
```

```python
# CORRECT — responsabilidades distribuidas
class PdfLoader:          # implementa LoaderPort
    def load(self, path: Path) -> Iterable[RawDocument]: ...

class OllamaEmbedder:     # implementa EmbedderPort
    def embed(self, texts: list[str]) -> list[list[float]]: ...

class LanceDbVectorStore: # implementa VectorStorePort
    def upsert(self, chunks: list[Chunk]) -> None: ...
    def search(self, vector: list[float], *, k: int) -> list[Chunk]: ...

class IngestUseCase:
    def __init__(self, loader: LoaderPort, embedder: EmbedderPort, store: VectorStorePort) -> None: ...

class QueryUseCase:
    def __init__(self, embedder: EmbedderPort, store: VectorStorePort, reranker: RerankerPort) -> None: ...
```

**Teste de cheiro:** se voce descreve a classe e precisa usar "e", divida.
"`RagService` le PDF E embeda E salva" -> 3 classes.

### 3.2 O — Open/Closed Principle

> Aberto para extensao, fechado para modificacao.

Adicionar um novo tipo de loader (ex: EPUB) **MUST NOT** exigir editar `IngestUseCase` nem o registry existente:

```python
# CORRECT — novo loader via porta e registry
# domain/ports/loader.py
class LoaderPort(Protocol):
    def supports(self, path: Path) -> bool: ...
    def load(self, path: Path) -> Iterable[RawDocument]: ...

# adapters/driven/loaders/pdf.py
class PdfLoader:
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"
    def load(self, path: Path) -> Iterable[RawDocument]: ...

# adapters/driven/loaders/epub.py  (NOVO — nenhum arquivo existente muda)
class EpubLoader:
    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".epub"
    def load(self, path: Path) -> Iterable[RawDocument]: ...

# composition/container.py registra loaders em uma lista
LOADERS: list[LoaderPort] = [PdfLoader(), DocxLoader(), EpubLoader(), TextLoader()]
```

### 3.3 L — Liskov Substitution Principle

> Qualquer implementacao de `EmbedderPort` **MUST** ser substituivel sem quebrar o `QueryUseCase`.

```python
# INCORRECT — implementacao "nula" que retorna vetor zero silenciosamente
class NullEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1024 for _ in texts]  # LSP violado: comportamento silenciosamente errado
    @property
    def dim(self) -> int:
        return 1024

# CORRECT — fake explicito para testes, com intent claro
class FakeEmbedder:
    """Embedder deterministico para testes. Nao use em producao."""
    def __init__(self, dim: int = 1024) -> None:
        self._dim = dim
    def embed(self, texts: list[str]) -> list[list[float]]:
        # hash-based pseudo-embedding deterministico
        return [self._hash_vec(t) for t in texts]
    @property
    def dim(self) -> int:
        return self._dim
    def _hash_vec(self, text: str) -> list[float]: ...
```

Regras derivadas:
- Override **MUST NOT** enfraquecer preconditions (nao pede mais do que a base).
- Override **MUST NOT** fortalecer postconditions (nao promete mais restritivo).
- Override **MUST NOT** levantar excecoes novas alem das declaradas.

### 3.4 I — Interface Segregation Principle

> Clientes nao devem depender de metodos que nao usam.

```python
# INCORRECT — porta gorda mistura leitura, escrita, indexacao e exportacao
class VectorStorePort(Protocol):
    def upsert(self, chunks: list[Chunk]) -> None: ...
    def search(self, vector: list[float], *, k: int) -> list[Chunk]: ...
    def fts_search(self, query: str, *, k: int) -> list[Chunk]: ...
    def rebuild_index(self) -> None: ...
    def export_csv(self, path: Path) -> None: ...  # nao pertence
    def backup(self, path: Path) -> None: ...       # nao pertence
```

```python
# CORRECT — segregado em papeis
class VectorStoreReader(Protocol):
    def search(self, vector: list[float], *, k: int) -> list[Chunk]: ...
    def fts_search(self, query: str, *, k: int) -> list[Chunk]: ...

class VectorStoreWriter(Protocol):
    def upsert(self, chunks: list[Chunk]) -> None: ...
    def rebuild_index(self) -> None: ...

class VectorStorePort(VectorStoreReader, VectorStoreWriter, Protocol): ...

# QueryUseCase depende apenas de VectorStoreReader
class QueryUseCase:
    def __init__(self, store: VectorStoreReader, ...) -> None: ...
```

- **SHOULD** manter portas com <= 5 metodos. Acima disso, considere segregar.

### 3.5 D — Dependency Inversion Principle

> Modulos de alto nivel (`application/`) **MUST NOT** depender de modulos de baixo nivel (`adapters/driven/`). Ambos dependem de abstracoes (`domain/ports/`).

```python
# INCORRECT — QueryUseCase importa concreto de adapter
from rag_maker.adapters.driven.lancedb.store import LanceDbVectorStore
from rag_maker.adapters.driven.ollama.embedder import OllamaEmbedder

class QueryUseCase:
    def __init__(self) -> None:
        self._store = LanceDbVectorStore(...)   # violacao: DI invertido
        self._embedder = OllamaEmbedder(...)    # violacao
```

```python
# CORRECT — depende de ports; composicao injeta concretos
from rag_maker.domain.ports.embedder import EmbedderPort
from rag_maker.domain.ports.vector_store import VectorStoreReader
from rag_maker.domain.ports.reranker import RerankerPort

class QueryUseCase:
    def __init__(
        self,
        *,
        embedder: EmbedderPort,
        store: VectorStoreReader,
        reranker: RerankerPort,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._reranker = reranker

# composition/container.py  faz o wiring concreto
def build_query_use_case(config: AppConfig) -> QueryUseCase:
    embedder = OllamaEmbedder(base_url=config.ollama_url, model=config.embed_model)
    store = LanceDbVectorStore(uri=config.db_path)
    reranker = CrossEncoderReranker(model_name=config.reranker_model)
    return QueryUseCase(embedder=embedder, store=store, reranker=reranker)
```

**Regra de ferro:** DI e feito UMA VEZ em `composition/container.py`. Nao em `__main__`. Nao em testes (testes fazem DI manual com fakes).

---

## 4. Design Patterns — Python Edition

Aplicar padroes quando resolvem um problema real. **MUST NOT** aplicar padroes especulativamente.

### 4.1 Patterns que USAMOS

| Pattern | Onde aplicar | Observacao |
|---|---|---|
| **Strategy** | `domain/ports/reranker.py` e variacoes do reranker | Via `Protocol`. Alternar reranker em runtime sem editar use case. |
| **Adapter** | `adapters/driven/ollama/embedder.py` | Traduz API HTTP do Ollama para `EmbedderPort`. |
| **Repository** | `domain/ports/vector_store.py` | `VectorStorePort` abstrai LanceDB. |
| **Factory / Registry** | `composition/container.py` (lista de `LoaderPort`) | Escolhe loader conforme `path.suffix`. |
| **Dependency Injection** | `composition/container.py` | Unica regiao que conhece concretos. |
| **Null Object** | `FakeEmbedder` para testes, `NoOpReranker` se config desabilita rerank | Nunca como fallback silencioso em producao. |
| **Singleton (lazy)** | `CrossEncoderReranker` — modelo pesado carregado uma vez | Via instancia modulo-level ou `functools.lru_cache`. Nunca para configuracoes. |
| **Context Manager** | Conexoes com LanceDB, leitura de PDFs grandes | `with ... as ...`. |
| **Iterator / Generator** | `LoaderPort.load() -> Iterable[RawDocument]` | Stream de documentos grandes em vez de carregar tudo. |

### 4.2 Strategy via Protocol (exemplo real)

```python
# domain/ports/reranker.py
from typing import Protocol

class RerankerPort(Protocol):
    def rerank(self, query: str, candidates: list[Chunk], *, top_k: int) -> list[Chunk]: ...

# adapters/driven/cross_encoder/bge.py
class BgeCrossEncoderReranker:
    def __init__(self, model_name: str) -> None: ...
    def rerank(self, query: str, candidates: list[Chunk], *, top_k: int) -> list[Chunk]: ...

# adapters/driven/cross_encoder/noop.py
class NoOpReranker:
    """Passthrough para testes e configuracoes sem rerank."""
    def rerank(self, query: str, candidates: list[Chunk], *, top_k: int) -> list[Chunk]:
        return candidates[:top_k]
```

### 4.3 Factory / Registry de Loaders

```python
# composition/container.py
from pathlib import Path
from rag_maker.domain.ports.loader import LoaderPort
from rag_maker.adapters.driven.loaders.pdf import PdfLoader
from rag_maker.adapters.driven.loaders.docx import DocxLoader
from rag_maker.adapters.driven.loaders.epub import EpubLoader
from rag_maker.adapters.driven.loaders.text import TextLoader

_LOADERS: list[LoaderPort] = [PdfLoader(), DocxLoader(), EpubLoader(), TextLoader()]

def resolve_loader(path: Path) -> LoaderPort:
    for loader in _LOADERS:
        if loader.supports(path):
            return loader
    raise ValueError(f"Nenhum loader disponivel para {path.suffix}")
```

### 4.4 Singleton Lazy (so para recursos pesados)

```python
# adapters/driven/cross_encoder/bge.py
from functools import lru_cache
from sentence_transformers import CrossEncoder

@lru_cache(maxsize=1)
def _get_model(model_name: str) -> CrossEncoder:
    return CrossEncoder(model_name, device="auto")

class BgeCrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
    def rerank(self, query: str, candidates: list[Chunk], *, top_k: int) -> list[Chunk]:
        model = _get_model(self._model_name)  # carrega 1x no primeiro uso
        ...
```

- **MAY** usar singleton lazy apenas para modelos pesados (reranker) ou conexoes reutilizaveis.
- **MUST NOT** usar singleton para configuracao, logger, ou estado de aplicacao.

### 4.5 Patterns PROIBIDOS / AVOID

| Anti-pattern | Por que evitar | Alternativa |
|---|---|---|
| **Service Locator** (`Container.get("embedder")`) | Dependencia escondida, dificil testar. | Constructor injection. |
| **God Object** (`class RagManager`) | Viola SRP. | Dividir em use cases. |
| **Manager / Util / Helper catch-all** | Nome nao revela intencao. | Nomear pela responsabilidade real (`ChunkScorer`, `RrfFuser`). |
| **Classes com so metodos estaticos** | Use modulo de funcoes livres. | `scoring.py` com `def reciprocal_rank_fusion(...)`. |
| **Herancas para reuso de codigo** | Viola LSP / acoplamento. | Composicao + protocol. |
| **Metaclasses** | Overkill, dificulta mypy. | Preferir `__init_subclass__` ou, melhor, nao precisar. |
| **Mutacao global** (`_registry = {}` mutavel) | Concorrencia, teste flaky. | Passar registry via construtor. |

---

## 5. Architecture Layers (Hexagonal + Front/Mid/Back)

### 5.1 Estrutura de Diretorios (obrigatoria)

```
src/rag_maker/
|-- domain/                           # BACK — nucleo puro
|   |-- models.py                     # frozen dataclasses + EmbeddingError
|   |-- chunker.py                    # puro; delega split para langchain-text-splitters
|   |-- scoring.py                    # RRF, fusao, score helpers
|   |-- errors.py                     # hierarquia de excecoes de dominio
|   `-- ports/                        # Protocols
|       |-- __init__.py
|       |-- embedder.py               # EmbedderPort
|       |-- vector_store.py           # VectorStorePort, VectorStoreReader, VectorStoreWriter
|       |-- reranker.py               # RerankerPort
|       `-- loader.py                 # LoaderPort
|-- application/                      # MID — use cases
|   |-- config.py                     # AppConfig via pydantic-settings
|   |-- ingest_use_case.py            # IngestUseCase
|   `-- query_use_case.py             # QueryUseCase
|-- adapters/
|   |-- driving/                      # FRONT — primarios
|   |   |-- cli/
|   |   |   `-- main.py               # Typer app
|   |   `-- gui/
|   |       |-- app.py                # PySide6 QApplication
|   |       |-- windows/
|   |       |-- widgets/
|   |       `-- workers/              # QThread workers
|   `-- driven/                       # BACK — secundarios (I/O)
|       |-- ollama/
|       |   `-- embedder.py           # implementa EmbedderPort
|       |-- lancedb/
|       |   `-- store.py              # implementa VectorStorePort
|       |-- cross_encoder/
|       |   |-- bge.py                # implementa RerankerPort
|       |   `-- noop.py               # NoOpReranker
|       |-- loaders/
|       |   |-- pdf.py                # PdfLoader (pypdf)
|       |   |-- docx.py               # DocxLoader (python-docx)
|       |   |-- epub.py               # EpubLoader (ebooklib + beautifulsoup4)
|       |   `-- text.py               # TextLoader (stdlib)
|       `-- config/
|           `-- toml_loader.py        # le ~/.config/rag_maker/config.toml
`-- composition/                      # MID — DI / wiring
    `-- container.py                  # build_* functions
```

### 5.2 Tabela de Camadas: CAN / CANNOT

| Camada | Pasta | CAN | CANNOT |
|---|---|---|---|
| **Frontend / Driving** | `adapters/driving/cli`, `adapters/driving/gui` | Conversar com `application/` via `composition/container`, formatar saida, renderizar UI, parsear argumentos. | Importar `domain/*` exceto tipos de retorno; importar `adapters/driven/*`; acessar LanceDB/Ollama/filesystem diretamente. |
| **Middleware / Application** | `application/`, `composition/` | Orquestrar use cases; conhecer `domain/ports/` e invoca-las; montar grafo de objetos em `composition/container.py`. | Importar `adapters/driving/*`; importar concreto de `adapters/driven/*` em `application/` (so `composition/` pode). |
| **Backend / Domain** | `domain/` | stdlib + `typing` + `dataclasses` + `pathlib`. Logica pura. Definir Protocols. | Importar qualquer lib externa (`lancedb`, `ollama`, `pypdf`, `PySide6`, `httpx`, `structlog`, `pydantic`, etc.) ou qualquer outra camada. |
| **Infrastructure / Driven** | `adapters/driven/*` | Implementar `domain/ports/*`. Usar UMA lib externa por pasta. Logar com `structlog`. | Importar `application/` ou `adapters/driving/`; conter regra de negocio. |

### 5.3 Regra da Seta de Dependencia

```
Frontend (adapters/driving)        Infrastructure (adapters/driven)
        |                                      |
        v                                      v
  Middleware (application + composition)  <----+
        |
        v
  Backend (domain — incluindo ports)
```

- **domain/** nao aponta para ninguem. E folha.
- **application/** aponta SO para `domain/`.
- **adapters/driven/** aponta SO para `domain/ports/` (implementa).
- **adapters/driving/** aponta para `application/` via `composition/container`.
- **composition/** e o UNICO lugar que importa concretos de `adapters/driven/*`.

### 5.4 Violacoes que a IA MUST Detectar e Recusar

| Linha detectada | Em arquivo | Acao |
|---|---|---|
| `from lancedb import ...` | qualquer coisa em `domain/` ou `application/` | RECUSAR. LanceDB so em `adapters/driven/lancedb/`. |
| `import ollama` ou `from rag_maker.adapters.driven.ollama import ...` | qualquer coisa em `domain/` ou `application/` | RECUSAR. Ollama so em `adapters/driven/ollama/`. |
| `from PySide6 ...` | qualquer coisa fora de `adapters/driving/gui/` | RECUSAR. |
| `from sentence_transformers import ...` | qualquer coisa fora de `adapters/driven/cross_encoder/` | RECUSAR. |
| `import pypdf` / `from docx import ...` / `from ebooklib import ...` | fora da respectiva subpasta de `adapters/driven/loaders/` | RECUSAR. |
| `from rag_maker.adapters.driven...` | em `application/` (nao em `composition/`) | RECUSAR. |
| `from rag_maker.adapters.driving...` | em `application/`, `domain/`, ou em `adapters/driven/` | RECUSAR. |
| `except Exception: pass` | qualquer lugar | RECUSAR. |
| Fallback com vetor zero em embedder | `adapters/driven/ollama/embedder.py` | RECUSAR. Lance `EmbeddingError`. |
| Funcao de impressao em `src/` | qualquer lugar | RECUSAR. Use `structlog`. |

Essas regras sao automatizadas via **import-linter** (ver `TESTES.md`). A IA **MUST** rodar `lint-imports` antes do commit.

### 5.5 Checklist de Camadas Pre-Commit

```
[ ] Classe/funcao nova pertence a exatamente uma camada?
[ ] Nenhum import cruza a seta (Frontend -> Middleware -> Backend <- Infra)?
[ ] domain/ so usa stdlib + typing + dataclasses + pathlib?
[ ] Novo Protocol foi colocado em domain/ports/?
[ ] Nova lib externa esta isolada em um unico subdiretorio de adapters/driven/?
[ ] composition/container.py continua sendo o unico lugar que monta concretos?
[ ] lint-imports (import-linter) passa sem violacoes?
```

---

## 6. Clean Code Rules (Python)

### 6.1 Naming

| Elemento | Convencao | Exemplo |
|---|---|---|
| Modulo / arquivo | `snake_case.py` | `ingest_use_case.py` |
| Pacote | `snake_case/` | `rag_maker/` |
| Classe / dataclass / Protocol | `PascalCase` | `OllamaEmbedder`, `EmbedderPort`, `Chunk` |
| Funcao / metodo | `snake_case` | `embed_batch`, `resolve_loader` |
| Variavel / parametro | `snake_case` | `base_url`, `top_k` |
| Constante de modulo | `UPPER_SNAKE_CASE` | `DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"` |
| Privado (convencao) | prefixo `_` | `_model`, `_resolve_path()` |
| Dunder / magico | `__x__` | somente o que o Python define |
| Type variable | `PascalCase` curto | `T`, `K`, `V`, `ChunkT` |

- Nomes **MUST** revelar intencao. Nenhuma abreviacao obscura (`ctx`, `cfg` ok; `mgr`, `hdlr` nao).
- Funcoes **MUST** ser `verbo_substantivo` ou `verbo`: `load_chunks`, `build_query_use_case`, `embed`, `rerank`.
- Booleans **MUST** prefixar `is_`, `has_`, `can_`, `should_`: `is_valid`, `has_cache`, `can_retry`.
- **MUST NOT** usar nomes de uma letra, exceto contadores de loop (`i`, `j`) e variaveis matematicas claras.
- **MUST NOT** usar `data`, `info`, `obj`, `item`, `thing` como nomes de alto nivel.

### 6.2 Tamanho de Funcoes e Classes

- Funcoes **MUST NOT** ultrapassar 40 linhas. Se passar, extraia sub-funcoes.
- Funcoes **MUST NOT** receber mais de 4 parametros posicionais/obrigatorios. Agrupe em dataclass se necessario.
- Use `*` para forcar keyword-only quando houver mais de 2 params: `def search(query: Query, *, k: int = 10, rerank: bool = True)`.
- Classes **SHOULD NOT** ultrapassar 300 linhas.
- Nesting **MUST NOT** ultrapassar 3 niveis de indentacao dentro do corpo de uma funcao.

### 6.3 Early Return / Guard Clauses

```python
# INCORRECT — nesting profundo
def process(chunk: Chunk) -> None:
    if chunk.text:
        if len(chunk.text) > MIN_LEN:
            if chunk.vector:
                store.upsert([chunk])

# CORRECT — early returns
def process(chunk: Chunk) -> None:
    if not chunk.text:
        return
    if len(chunk.text) <= MIN_LEN:
        return
    if not chunk.vector:
        raise EmbeddingError(f"chunk {chunk.id} sem vetor")
    store.upsert([chunk])
```

### 6.4 Docstrings e Comentarios

- **MUST** escrever docstring em API publica (funcoes/classes sem `_` prefix), em estilo Google ou NumPy, consistente dentro do modulo.
- **SHOULD NOT** escrever docstring repetindo type hints ("retorna uma lista de strings" quando a assinatura ja diz).
- **MUST** comentar o porque, nunca o o que.
- **MUST** marcar gambiarras com `# HACK:` ou `# FIXME:` + contexto + ticket.

```python
# INCORRECT
i += 1  # incrementa i

# CORRECT
# bge-m3 retorna dim 1024; Ollama > 0.3.x as vezes embrulha em {"embeddings": [...]}
# e as vezes retorna {"embedding": [...]}. Normalizamos aqui.
vec = response.get("embedding") or response["embeddings"][0]
```

### 6.5 f-Strings Obrigatorias

```python
# INCORRECT
msg = "Chunk %s com %d caracteres" % (chunk_id, length)
msg = "Chunk {} com {} caracteres".format(chunk_id, length)

# CORRECT
msg = f"Chunk {chunk_id} com {length} caracteres"

# CORRECT para logging estruturado — variaveis vao em kwargs, nao interpolados
log.info("chunk_processed", chunk_id=chunk_id, length=length)
```

### 6.6 Error Handling

Hierarquia em `domain/errors.py`:

```python
# domain/errors.py
class RagMakerError(Exception):
    """Base de todos os erros de dominio."""

class EmbeddingError(RagMakerError):
    """Falha ao gerar embedding."""

class VectorStoreError(RagMakerError):
    """Falha na camada de persistencia vetorial."""

class LoaderError(RagMakerError):
    """Falha ao carregar documento."""

class ConfigError(RagMakerError):
    """Config ausente ou invalida."""
```

Regras:
- **MUST** definir excecoes de dominio em `domain/errors.py` (ou `domain/models.py` para `EmbeddingError` se preferido).
- **MUST NOT** usar `except Exception: pass`. Proibido.
- **MUST NOT** usar `except:` sem tipo. Proibido.
- **MUST** adicionar contexto ao re-lancar: `raise EmbeddingError("ollama offline") from err`.
- **MUST** logar erros com `structlog` com contexto: `log.error("embed_failed", model=m, n=len(texts), exc_info=True)`.
- **MUST NOT** usar excecoes para controle de fluxo (ex: `try: ...; except StopIteration: ...`). Use return values.
- **MAY** modelar resultados esperados com Option/Result via `X | None` ou tipos de uniao discriminada; lance excecao apenas para erros excepcionais.

```python
# INCORRECT — swallow silencioso
try:
    vec = embedder.embed([text])
except Exception:
    vec = [[0.0] * 1024]  # vetor zero fantasma

# CORRECT
from rag_maker.domain.errors import EmbeddingError

try:
    vecs = embedder.embed([text])
except httpx.HTTPError as err:
    log.error("embed_http_error", text_len=len(text), exc_info=True)
    raise EmbeddingError(f"falha ao embedar texto de {len(text)} chars") from err
```

### 6.7 Constantes e Magic Numbers

```python
# INCORRECT
if retries > 3:
    raise EmbeddingError("too many")
vec_dim = 1024

# CORRECT — em domain/models.py ou application/config.py
from typing import Final

MAX_EMBED_RETRIES: Final[int] = 3
BGE_M3_DIM: Final[int] = 1024
DEFAULT_BATCH_SIZE: Final[int] = 32
SEARCH_DEBOUNCE_MS: Final[int] = 300

if retries > MAX_EMBED_RETRIES:
    raise EmbeddingError(...)
```

- **MUST** usar `typing.Final` para constantes.
- **MUST** usar ALL_CAPS para constantes module-level.

### 6.8 Imports

```python
# CORRECT — ordem: __future__, stdlib, terceiros, locais, separados por linha em branco
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
import structlog

from rag_maker.domain.models import Chunk
from rag_maker.domain.ports.embedder import EmbedderPort
```

- **MUST NOT** usar `from x import *`.
- **MUST NOT** usar imports relativos profundos (`from ...foo import bar`). Use caminho absoluto.
- **SHOULD** usar `TYPE_CHECKING` para imports so-de-tipo (ver secao 12).

---

## 7. UI/UX Guidelines for PySide6

### 7.1 Threading

- **MUST** manter UI thread livre de I/O e computacao pesada. Qualquer embed, busca LanceDB ou carregamento de PDF vai em worker.
- **MUST** usar `QThread` + `QObject.moveToThread()`, nao `QThread.run()` subclassado (anti-pattern antigo).
- **MUST** comunicar resultados via `Signal`/`Slot` com tipos declarados.
- **MUST NOT** chamar `QThread.sleep()` na UI thread.
- **MUST NOT** manipular widgets de dentro de uma worker thread — emita signal e deixe a UI thread atualizar.

```python
# CORRECT — worker por composicao, nao heranca
from PySide6.QtCore import QObject, QThread, Signal

class QueryWorker(QObject):
    finished = Signal(list)      # list[Chunk]
    failed = Signal(str)

    def __init__(self, use_case: QueryUseCase, query: Query) -> None:
        super().__init__()
        self._use_case = use_case
        self._query = query

    def run(self) -> None:
        try:
            chunks = self._use_case.execute(self._query)
        except RagMakerError as err:
            self.failed.emit(str(err))
            return
        self.finished.emit(chunks)

# Uso:
thread = QThread()
worker = QueryWorker(use_case, query)
worker.moveToThread(thread)
thread.started.connect(worker.run)
worker.finished.connect(on_results)
worker.failed.connect(on_error)
worker.finished.connect(thread.quit)
thread.start()
```

### 7.2 Feedback ao Usuario

- Cada acao **MUST** produzir feedback visivel em < 200ms.
- Operacoes > 3s **MUST** ser cancelaveis (botao Cancel ou ESC).
- Operacoes > 500ms **MUST** mostrar spinner ou progress bar.
- Mensagens de erro **MUST** ser legiveis (nao stack trace). Detalhes tecnicos vao pra log, nao pra UI.
- Estados vazios (zero resultados, corpus vazio) **MUST** ter texto explicativo, nao tela em branco.

### 7.3 Acessibilidade (WCAG AA)

- Contraste texto/fundo **MUST** ser >= 4.5:1 para texto normal.
- Contraste **MUST** ser >= 3:1 para texto grande (>= 18pt).
- Todos os widgets interativos **MUST** ser alcancaveis via Tab.
- Todos os botoes e inputs **MUST** ter `setAccessibleName(...)` e, quando util, `setAccessibleDescription(...)`.
- **MUST NOT** transmitir informacao SO por cor (erro vermelho sem icone nao basta).

### 7.4 Estilo (QSS Centralizado)

- Estilos **MUST** vir de um unico QSS central aplicado via `QApplication.setStyleSheet(...)`.
- **MUST NOT** chamar `widget.setStyleSheet("color: #...")` com cores hardcoded espalhadas pelos widgets.
- Tokens (cores, espacamentos, fontes) **MUST** ser declarados em um unico lugar em Python ou em constantes QSS.
- Tipografia: corpo 13px, subtitulo 12px, titulo 16-18px. Grid de 8px para margens/paddings.

### 7.5 Inputs e Formularios

- Validacao **MUST** ocorrer no submit, nao silenciosamente no `blur`.
- Erros **MUST** aparecer ao lado do campo, nunca soltos no topo.
- Botoes de submit **MUST** desabilitar durante operacao assincrona.
- Formularios **MUST NOT** ser limpos em caso de erro — preserve o input.

---

## 8. Security

> Procedimentos completos em [TESTES.md](TESTES.md).

### 8.1 OWASP Top 10 Ajustado ao Dominio

| # | Risco | Regra aplicada ao rag_maker |
|---|---|---|
| A01 | Broken Access Control | N/A (app local single-user); **MUST NOT** expor a API de ingestao em servidor web. |
| A02 | Cryptographic Failures | N/A relevante (sem autenticacao); **MUST** usar HTTPS em qualquer remote fetch futuro. |
| A03 | Injection / Path Traversal | **MUST** resolver paths com `Path.resolve()` e validar que estao dentro do corpus configurado. **MUST NOT** concatenar strings em paths ou queries. |
| A04 | Insecure Design | **MUST** revisar ports novos em TODO.md antes de implementar. |
| A05 | Security Misconfiguration | **MUST NOT** fazer ship com log-level=DEBUG ou com URLs remotas por padrao. `base_url` padrao e `http://127.0.0.1:11434` (Ollama local). |
| A06 | Vulnerable Components | **MUST** rodar `pip-audit` no CI. Zero CRITICAL unpatched. |
| A07 | Auth Failures | N/A. |
| A08 | Software Integrity | **MUST** commitar `uv.lock`. Pipeline **MUST** falhar se `uv.lock` divergir. |
| A09 | Logging Failures | **MUST NOT** logar conteudo integral de queries ou chunks em producao — podem conter dados sensiveis do usuario. Logar apenas `query_hash`, `chunk_id`, tamanho. |
| A10 | SSRF | **MUST** manter allowlist de URLs: por padrao so `http://127.0.0.1:11434` (Ollama). Qualquer URL fora do allowlist **MUST** vir de config explicita. |

### 8.2 Hardcoded Secrets — Zero Tolerancia

- **MUST NOT** hardcodar senhas, tokens, chaves de API em `src/`.
- **MAY** manter config nao-secreta em `~/.config/rag_maker/config.toml` — arquivo local do usuario, fora do repo.
- **MUST** ler credenciais via variavel de ambiente ou TOML local.
- Arquivos proibidos de commit: `.env`, `*.key`, `*.pem`, `credentials*.json`, qualquer coisa em `secrets/`.

```python
# INCORRECT
OLLAMA_TOKEN = "abc123-secret"

# CORRECT — via pydantic-settings
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        toml_file=Path.home() / ".config" / "rag_maker" / "config.toml",
    )
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_token: str | None = None  # vem do env RAG_OLLAMA_TOKEN ou TOML
```

### 8.3 Input Validation

- **MUST** validar todo path recebido do usuario: `user_path.resolve()` e checar se esta sob o corpus configurado.
- **MUST** validar tamanho de query e de arquivo antes de processar (rejeitar > N MB configurado).
- **MUST** normalizar encoding para UTF-8 na entrada.
- **MUST NOT** confiar em dados de resposta de Ollama — validar `dim` e tipos.

```python
def _validate_in_corpus(path: Path, corpus_root: Path) -> Path:
    resolved = path.resolve(strict=True)
    corpus = corpus_root.resolve(strict=True)
    try:
        resolved.relative_to(corpus)
    except ValueError as err:
        raise LoaderError(f"path fora do corpus: {path}") from err
    return resolved
```

### 8.4 Config (TOML Local) — Runtime Nao Escreve Codigo

- **MUST NOT** reescrever codigo-fonte Python em runtime.
- Estado mutavel **MUST** viver em `~/.config/rag_maker/config.toml` (ou arquivo apontado por `RAG_CONFIG`).
- **MUST** usar `tomllib` (stdlib, 3.11+) para leitura.
- **MUST** usar `tomli-w` para escrita programatica.
- `pydantic-settings` **MUST** validar e aplicar defaults.

---

## 9. Performance

### 9.1 Regras Gerais

- **MUST** profilear antes de otimizar. Ferramentas: `py-spy`, `cProfile`, `memray`, `line_profiler`.
- **MUST NOT** otimizar sem evidencia de bottleneck.
- **MUST** cachear resultados custosos. LanceDB ja persiste embeddings; **MUST NOT** re-embedar chunks ja presentes.
- **SHOULD** usar lazy-loading para modelos pesados (reranker) e conexoes.

### 9.2 Embeddings em Lote

- **MUST** batchar chamadas ao Ollama com tamanho >= 32 (configuravel via `embed_batch_size`).
- **MUST NOT** chamar Ollama em loop item-a-item quando houver > 1 chunk.
- **MUST** validar dim do primeiro batch e cachear em `AppConfig.embed_dim`. Divergencia subsequente => `EmbeddingError`.

### 9.3 Debounce na GUI

- Busca incremental na GUI **MUST** debouncar em >= 300ms apos ultima tecla.
- Cancelar requests anteriores ao submeter nova.

```python
# CORRECT — debounce com QTimer
self._debounce = QTimer(self)
self._debounce.setSingleShot(True)
self._debounce.setInterval(SEARCH_DEBOUNCE_MS)
self._debounce.timeout.connect(self._do_search)
self._input.textChanged.connect(lambda _t: self._debounce.start())
```

### 9.4 Streaming de PDFs Grandes

- Loaders **MUST** retornar `Iterable[RawDocument]` (generator), nao `list` inteira.
- **MUST** permitir que `IngestUseCase` processe pagina-a-pagina (ou secao-a-secao) sem carregar o PDF inteiro em memoria.

### 9.5 Reranker Lazy-Load

- Modelo de reranker (`bge-reranker-v2-m3`, ~500MB) **MUST** ser lazy singleton via `@lru_cache`.
- CLI **MUST** oferecer `rag doctor` que precarrega o modelo para evitar first-call slow.

### 9.6 LanceDB

- HNSW index **MUST** ser criado apos o batch inicial de inserts (nao antes, nao a cada insert).
- FTS (tantivy) index **MUST** ser configurado na coluna `text`.
- Busca hibrida: RRF em `domain/scoring.py` a partir de listas vetorial + FTS, ou `.search().rerank(...)` nativo se disponivel.

---

## 10. Git Process

### 10.1 Antes de Qualquer Codigo

```bash
# MUST: ler os arquivos que serao alterados (use a Read tool, nao cat)
# MUST: conferir TODO.md — existe tarefa aprovada?
# MUST: verificar ambiente limpo
uv sync --frozen
ruff check .
mypy --strict src
pytest -q
```

Todos **MUST** passar antes de comecar.

### 10.2 Conventional Commits (OBRIGATORIO)

Formato: `<type>(<scope>): <description>`

| Type | Quando usar |
|---|---|
| `feat` | Nova feature (novo use case, novo adapter, novo comando CLI). |
| `fix` | Correcao de bug. |
| `refactor` | Mudanca sem alterar comportamento observavel. |
| `docs` | Documentacao apenas (README, CONTRACT, TESTES, AGENTS). |
| `test` | Testes novos ou ajustes em testes. |
| `chore` | Build, CI, deps, tooling (uv.lock, ruff config). |
| `perf` | Melhoria de performance (medida!). |
| `style` | Formatacao; nunca logica. |
| `revert` | Reverter commit anterior. |

Exemplos do dominio:

```bash
# CORRECT
git commit -m "feat(ingest): add EpubLoader using ebooklib and beautifulsoup4"
git commit -m "fix(embedder): raise EmbeddingError when ollama returns empty vector"
git commit -m "refactor(scoring): extract reciprocal_rank_fusion to domain/scoring.py"
git commit -m "test(chunker): property-based tests for chunk size invariants with hypothesis"
git commit -m "docs(contract): document hexagonal layers and import-linter rules"
git commit -m "perf(query): batch ollama embed calls with size 64 (p50 -40%)"
git commit -m "chore(deps): bump lancedb to 0.11.0 in uv.lock"

# INCORRECT
git commit -m "fix stuff"
git commit -m "WIP"
git commit -m "update"
```

### 10.3 Branch Naming

```
feat/nome-da-feature-curta
fix/descricao-do-bug
refactor/modulo-afetado
docs/nome-do-documento
chore/ferramenta-ou-dep
test/modulo-testado
perf/operacao-otimizada
```

Ex.: `feat/epub-loader`, `fix/ollama-empty-vector`, `refactor/rrf-fusion`.

### 10.4 Checklist Pre-Commit (OBRIGATORIO)

```
[ ] Tarefa ID em TODO.md autorizada?
[ ] ruff check . sem violations
[ ] ruff format --check . sem diff
[ ] mypy --strict src sem erros
[ ] pytest -q passa (unit + integration marcados)
[ ] lint-imports sem violations (import-linter)
[ ] pip-audit sem CRITICAL
[ ] Nenhum arquivo .env, credentials*, *.key staged
[ ] Nenhum arquivo em legacy/ modificado
[ ] Commit message segue Conventional Commits
[ ] Apenas arquivos relacionados a uma tarefa staged (no unrelated changes)
```

### 10.5 Proibicoes Absolutas

- **MUST NOT** force-push em `main` / `master`.
- **MUST NOT** usar `--no-verify` em commits (hooks existem por uma razao).
- **MUST NOT** usar `--amend` em commits ja publicados.
- **MUST NOT** commitar `.env`, `credentials*.json`, `*.key`, `*.pem`.
- **MUST NOT** commitar artefatos de build (`dist/`, `build/`, `*.egg-info/`, `__pycache__/`).
- **MUST NOT** misturar mudancas nao relacionadas num mesmo commit.
- **MUST NOT** modificar arquivos sob `legacy/`.

### 10.6 Template de PR

```markdown
## What
[Uma frase: o que este PR faz]

## Why
[Uma frase: por que era necessario. Referencia a tarefa em TODO.md.]

## How
- [Decisao tecnica 1]
- [Decisao tecnica 2]

## Checklist
- [ ] ruff / mypy --strict / pytest passam localmente
- [ ] import-linter sem violations
- [ ] pip-audit sem CRITICAL
- [ ] Cobertura >= 70% (ou justificativa)
- [ ] Docs atualizados (CONTRACT / TESTES / AGENTS) se contrato mudou
- [ ] TODO.md com status atualizado
```

---

## 11. Testing & Audit Mandate

> Procedimentos e comandos completos: **[TESTES.md](TESTES.md)**

### 11.1 Quando Rodar Cada Grupo

| Evento | Testes obrigatorios |
|---|---|
| Cada commit | `ruff check`, `ruff format --check`, `mypy --strict`, `pytest -q` |
| Feature concluida | Tudo acima + `pytest --cov` >= 70%, `lint-imports` |
| Mudanca em `adapters/driven/ollama/` ou `adapters/driven/lancedb/` | `pytest -m integration` + `pytest -m e2e` |
| Nova dependencia | `pip-audit`, atualizar `uv.lock`, conferir licenca |
| Mudanca em `domain/ports/` | Revalidar todos os fakes em `tests/fakes/`; rodar suite inteira |
| Mudanca em `application/` | Rodar testes de integracao com fakes + smoke E2E |
| Mudanca na GUI | Teste manual + `pytest-qt` se aplicavel |
| Mudanca em CLI | Smoke test `rag --help`, `rag ingest`, `rag query --json` |
| Antes de release | Suite completa + auditoria descrita em TESTES.md |

### 11.2 Minimum Quality Gates (MUST passar antes de release)

```
[ ] ruff check          : 0 erros
[ ] ruff format --check : 0 diff
[ ] mypy --strict src   : 0 erros
[ ] pytest              : 0 failures, 0 errors
[ ] pytest --cov=src    : >= 70% line coverage
[ ] lint-imports        : 0 violations (hexagonal boundaries)
[ ] pip-audit           : 0 CRITICAL unpatched
[ ] Nenhuma funcao de impressao em src/
[ ] Nenhum TODO / FIXME sem issue link
```

### 11.3 Categorias de Teste (marcadores pytest)

| Marker | Escopo | Quando rodar |
|---|---|---|
| (default) | Unit, puro, rapido | Sempre. |
| `@pytest.mark.integration` | Toca disco / rede local (LanceDB file, Ollama mock via respx) | Antes de PR. |
| `@pytest.mark.e2e` | Exercita CLI completa via subprocess | Antes de release. |
| `@pytest.mark.slow` | > 1s, cobre loaders reais, modelos reais | Noturno / CI especifico. |

---

## 12. Python-Specific Rules

### 12.1 Type Hints: Deep Dive

- **MUST** `from __future__ import annotations` no TOPO de todo `.py` em `src/` e `tests/`.
- **MUST** usar sintaxe moderna (PEP 585 / PEP 604): `list[X]`, `X | None`, `tuple[A, B]`.
- **MUST NOT** usar `Any` exceto em boundary com lib mal tipada, e mesmo assim com comentario justificando.
- **MUST NOT** usar `type: ignore` sem explicacao: `# type: ignore[arg-type]  # httpx.Response.json() devolve Any`.
- **MUST** preferir `Iterable[T]` / `Sequence[T]` / `Mapping[K, V]` em parametros.
- **MUST** preferir `list[T]` / `dict[K, V]` em retornos concretos.
- **SHOULD** usar `Final` para constantes, `Literal` para enums simples, `TypedDict` para JSON tipado.
- **SHOULD** usar `TYPE_CHECKING` para imports pesados usados apenas em anotacoes:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import lancedb  # nao carregado em runtime se arquivo estiver em adapter correto
    from rag_maker.domain.models import Chunk
```

### 12.2 Frozen Dataclasses

- **MUST** usar `@dataclass(frozen=True, slots=True, kw_only=True)` em modelos de `domain/models.py`.
- **MUST** armazenar vetores como `tuple[float, ...]`, nao `list[float]`.
- **MUST** expor fabricas via `@classmethod` quando a construcao exigir validacao:

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class Chunk:
    id: str
    text: str
    source: Path
    page: int | None
    vector: tuple[float, ...]

    @classmethod
    def create(cls, *, id: str, text: str, source: Path, page: int | None,
               vector: Sequence[float]) -> Chunk:
        if not text.strip():
            raise ValueError("chunk text vazio")
        if len(vector) != BGE_M3_DIM:
            raise EmbeddingError(f"dim esperada {BGE_M3_DIM}, recebida {len(vector)}")
        return cls(id=id, text=text, source=source, page=page, vector=tuple(vector))
```

### 12.3 Protocols

- **MUST** usar `Protocol` para TODA porta em `domain/ports/`.
- **MUST NOT** usar `ABC` / `abstractmethod` para ports.
- **MAY** marcar `@runtime_checkable` APENAS quando `isinstance(obj, Port)` for necessario (normalmente: NUNCA).
- **MUST** manter Protocols livres de implementacao (sem `raise NotImplementedError`).

### 12.4 Bibliotecas Escolhidas (e o porque)

| Escolha | Em vez de | Razao |
|---|---|---|
| `pathlib.Path` | `os.path` | Orientado a objeto, cross-platform. |
| `tomllib` | `toml` / `tomlkit` | Stdlib a partir do 3.11. Leitura apenas; `tomli-w` para escrita. |
| `httpx` | `requests` | async-ready, typed, suporta HTTP/2, transport customizavel. |
| `structlog` | `logging` direto | Logging estruturado JSON-friendly, contexto acumulavel. |
| `pydantic-settings` | variaveis de ambiente cruas | Validacao + TOML + env em ordem definida. |
| `uv` | `pip` / `poetry` | Lockfile reproduzivel, rapido. |
| `ruff` | `flake8 + isort + pyupgrade` | Um binario, config unificada. |
| `typer[all]` | `argparse` | Types-driven, `--help` bonito via rich. |
| `pytest` | `unittest` | Fixtures, markers, parametrizacao. |
| `hypothesis` | casos manuais exaustivos | Property-based em logica pura (chunker, scoring). |

### 12.5 Logging com structlog

```python
# CORRECT — estruturado
import structlog
log = structlog.get_logger(__name__)

log.info("ingest_started", corpus=str(root), n_files=len(files))
try:
    chunks = list(use_case.ingest(path))
except RagMakerError:
    log.error("ingest_failed", path=str(path), exc_info=True)
    raise
log.info("ingest_finished", path=str(path), n_chunks=len(chunks))

# INCORRECT — saida direta na console e proibida em src/
# use estritamente structlog ao inves de chamadas diretas a logging ou a funcao builtin de impressao
```

### 12.6 pytest: Convencoes

- **MUST** usar fixtures com scope explicito (`scope="function"` default; `"module"` / `"session"` so com razao).
- **MUST** nomear testes como `test_<funcionalidade>_<condicao>_<resultado_esperado>`.
- **MUST** usar `@pytest.mark.parametrize` em vez de loops no teste.
- **MUST** marcar testes lentos/integration/e2e (ver 11.3).
- **SHOULD** usar `hypothesis` para propriedades da logica pura (`chunker.split`, `scoring.rrf`, `AppConfig` parsing).
- **MUST** usar `respx` para mockar `httpx` (Ollama HTTP), jamais bater no servico real em unit.

```python
# CORRECT
import pytest
from hypothesis import given, strategies as st

@given(text=st.text(min_size=1, max_size=10_000), chunk_size=st.integers(20, 2_000))
def test_chunker_preserva_tamanho_maximo(text: str, chunk_size: int) -> None:
    chunks = split(text, chunk_size=chunk_size, overlap=0)
    assert all(len(c) <= chunk_size for c in chunks)
```

### 12.7 Mixin vs Composicao

- **SHOULD** preferir composicao (passar dependencia como parametro) em vez de mixins.
- **MUST NOT** usar heranca multipla para agrupar funcionalidades nao relacionadas.

### 12.8 Proibicoes Python

- **MUST NOT** usar a funcao builtin de avaliacao dinamica de strings.
- **MUST NOT** usar `__import__` dinamico.
- **MUST NOT** usar `globals()` / `locals()` para escrita.
- **MUST NOT** usar `getattr(obj, "x")` quando `obj.x` e estaticamente conhecido.
- **MUST NOT** serializar dados do usuario via serializadores binarios nativos nao seguros (use LanceDB / JSON / TOML).
- **MUST NOT** usar `assert` em path critico de producao (pode ser desabilitado com `-O`). Use `raise`.

---

## 13. Framework-Specific Rules

Apenas frameworks que o `rag_maker` utiliza. Nada mais.

### 13.1 Typer (CLI)

- **MUST** separar subcomandos em funcoes distintas (`rag ingest`, `rag query`, `rag doctor`).
- **MUST** usar `Annotated[T, typer.Option(...)]` para opcoes tipadas.
- **MUST** definir exit codes explicitos (`raise typer.Exit(code=2)` para erro de uso).
- **MUST** ter flag `--json` que escreve JSON machine-readable no `stdout`. Logs vao no `stderr` via structlog.
- **MUST** usar `rich` para saida humana (tabelas, syntax highlight, progress).
- **MUST NOT** misturar saida humana e logs estruturados. Saida de dados = `typer.echo` / `rich.print` no stdout; logs = structlog no stderr.

```python
from __future__ import annotations
from typing import Annotated
import typer

app = typer.Typer(add_completion=False, no_args_is_help=True)

@app.command()
def query(
    text: Annotated[str, typer.Argument(help="Consulta em linguagem natural")],
    k: Annotated[int, typer.Option("--k", help="Top-k resultados")] = 10,
    as_json: Annotated[bool, typer.Option("--json", help="Saida JSON no stdout")] = False,
) -> None:
    """Executa consulta e imprime chunks rankeados."""
    ...
```

### 13.2 PySide6 (GUI)

- **MUST** usar `QMainWindow` como janela principal; widgets em modulos separados.
- **MUST** mover trabalho pesado para `QThread` workers com `moveToThread`.
- **MUST** usar `Signal` / `Slot` tipados: `Signal(list)` para `list[Chunk]` com `@Slot(list)` no receptor.
- **MUST NOT** fazer I/O sincrono na thread principal.
- **MUST** centralizar QSS em `adapters/driving/gui/assets/theme.qss` ou equivalente.
- **MUST** expor `setAccessibleName` em todo widget interativo.
- **MUST** permitir cancelamento de operacoes > 3s (ex: busca que demora).

### 13.3 Pydantic-Settings

- **MUST** declarar config em `application/config.py` como `BaseSettings`.
- **MUST** definir fontes na ordem: init -> env (prefix `RAG_`) -> TOML (`~/.config/rag_maker/config.toml`) -> defaults.
- **MUST** validar paths com `@field_validator` resolvendo para absoluto e checando existencia quando aplicavel.
- **MUST NOT** colocar `SecretStr` em logs.

```python
from __future__ import annotations
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_",
        env_nested_delimiter="__",
        toml_file=Path.home() / ".config" / "rag_maker" / "config.toml",
    )
    corpus_root: Path = Path.home() / "rag_maker_corpus"
    db_path: Path = Path.home() / ".local" / "share" / "rag_maker" / "lancedb"
    ollama_base_url: str = "http://127.0.0.1:11434"
    embed_model: str = "bge-m3:latest"
    embed_dim: int = 1024
    embed_batch_size: int = Field(default=32, ge=1, le=256)
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    @field_validator("corpus_root", "db_path")
    @classmethod
    def _resolve(cls, v: Path) -> Path:
        return v.expanduser().resolve()
```

### 13.4 LanceDB

- **MUST** definir schema via `pyarrow.schema(...)` explicito; nao confiar em inferencia.
- **MUST** criar index HNSW APOS batch inicial significativo (nao a cada insert).
- **MUST** criar FTS index em coluna `text`.
- **SHOULD** usar busca hibrida: RRF via `domain/scoring.py` combinando `.search(vector)` + FTS `.search(query, query_type="fts")`.
- **MUST NOT** importar `lancedb` fora de `adapters/driven/lancedb/`.
- **MUST** cercar operacoes com `try/except` e mapear erros para `VectorStoreError`.

### 13.5 Ollama HTTP

- **MUST** chamar via `httpx.Client` (sincrono) com `timeout=httpx.Timeout(connect=5.0, read=60.0)`.
- **MUST** validar a resposta: presenca de `embedding`/`embeddings`, tipo, tamanho == `embed_dim`.
- **MUST** batchar (enviar lista de textos em uma requisicao quando a API suportar).
- **MUST** cachear `embed_dim` no primeiro uso e falhar com `EmbeddingError` se futuro batch divergir.
- **MUST NOT** importar `httpx` fora de adapters (ex: `adapters/driven/ollama/`).

```python
# adapters/driven/ollama/embedder.py (resumido)
from __future__ import annotations
import httpx
import structlog
from rag_maker.domain.errors import EmbeddingError

log = structlog.get_logger(__name__)
_TIMEOUT = httpx.Timeout(connect=5.0, read=60.0)

class OllamaEmbedder:
    def __init__(self, *, base_url: str, model: str, expected_dim: int) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._expected_dim = expected_dim
        self._client = httpx.Client(base_url=self._base_url, timeout=_TIMEOUT)

    @property
    def dim(self) -> int:
        return self._expected_dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            r = self._client.post("/api/embed", json={"model": self._model, "input": texts})
            r.raise_for_status()
            payload = r.json()
        except httpx.HTTPError as err:
            log.error("ollama_http_error", n=len(texts), exc_info=True)
            raise EmbeddingError("falha HTTP ao embedar") from err

        vectors = payload.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise EmbeddingError("resposta ollama malformada")
        for v in vectors:
            if len(v) != self._expected_dim:
                raise EmbeddingError(
                    f"dim esperada {self._expected_dim}, recebida {len(v)}"
                )
        return vectors
```

### 13.6 sentence-transformers (Reranker)

- **MUST** usar singleton lazy (`@lru_cache(maxsize=1)`) para o modelo.
- **MUST** usar `device="auto"` (deixa o `sentence_transformers` escolher GPU/MPS/CPU).
- **MUST** oferecer `NoOpReranker` para testes e para configuracao sem rerank.
- **MUST** precarregar via `rag doctor` para evitar latencia na primeira query.
- **MUST NOT** importar `sentence_transformers` fora de `adapters/driven/cross_encoder/`.

### 13.7 pytest

- **MUST** colocar testes em `tests/` espelhando a arvore de `src/rag_maker/`.
- **MUST** usar fixtures em `tests/conftest.py` ou `tests/<camada>/conftest.py` com scope explicito.
- **MUST** separar `tests/unit/`, `tests/integration/`, `tests/e2e/` ou usar markers.
- **MUST** fornecer fakes em `tests/fakes/`: `FakeEmbedder`, `FakeVectorStore`, `FakeReranker`, `FakeLoader`.
- **MUST** usar `respx` para mock de HTTP (Ollama) em unit/integration.
- **SHOULD** usar `@pytest.mark.parametrize` extensivamente.
- **SHOULD** usar `hypothesis` em logica pura (`chunker`, `scoring`, `AppConfig`).

### 13.8 ruff + mypy

- `pyproject.toml` **MUST** conter config para ruff e mypy.
- Ruff: enable pelo menos `E`, `F`, `W`, `I`, `N`, `UP`, `B`, `A`, `C4`, `SIM`, `TID`, `TCH`, `RUF`.
- Mypy: `strict = true`, `warn_unused_ignores = true`, `disallow_any_explicit = true`.
- **MUST NOT** desabilitar regras globalmente sem justificativa em comentario.

### 13.9 import-linter

- `.importlinter` (ou bloco em `pyproject.toml`) **MUST** declarar contratos:
  - `domain/` independente de `adapters/`, `application/`, `composition/`.
  - `application/` nao importa `adapters/`.
  - `adapters/driving/` nao importa `adapters/driven/`.
  - `adapters/driven/<lib>/` contem UM import de cada lib externa proprietaria.
- `lint-imports` **MUST** rodar no CI e bloquear merge em violacao.

---

*Este contrato e a referencia normativa para todo codigo escrito no projeto `rag_maker`.*
*Qualquer conflito entre este documento e codigo existente: o codigo esta errado e deve ser corrigido (mediante tarefa em TODO.md).*
*Para procedimentos executaveis de teste e auditoria veja [TESTES.md](TESTES.md).*
*Para a lista de pendencias autorizadas veja [TODO.md](TODO.md).*
*Ultima atualizacao: 2026-04-19.*
