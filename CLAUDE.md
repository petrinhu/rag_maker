# rag_maker

Ferramenta de recuperação (retrieval-only) offline para construção de bibliografia pessoal e assistência a IAs externas (Claude Code / ChatGPT / Gemini) que consomem trechos brutos e redigem resumos, artigos e livros.

## Filosofia

- **Único modelo local**: `bge-m3:latest` via Ollama (apenas embeddings, dim=1024).
- **Sem LLM local para síntese** — o consumidor externo (IA) é quem redige.
- **AGENTS.md é o contrato formal** que instrui IAs externas a chamar a CLI e interpretar as respostas.

## Estrutura

- `legacy/` — projeto antigo, somente-leitura, nunca importado pelo novo.
- `src/rag_maker/` — novo projeto (criado a partir da Fase 1).
- `TODO.md` — tabela de pendências (obrigatório consultar antes de qualquer alteração).

## Arquitetura — Hexagonal (Ports & Adapters)

```
src/rag_maker/
├── domain/            # núcleo puro; zero I/O, zero libs externas
│   ├── models.py      # frozen dataclasses + exceções
│   ├── chunker.py     # lógica pura
│   ├── scoring.py     # RRF
│   └── ports/         # Protocols: EmbedderPort, VectorStorePort, RerankerPort, LoaderPort
├── application/       # use cases — dependem APENAS de ports
│   ├── config.py
│   ├── ingest_use_case.py
│   └── query_use_case.py
├── adapters/
│   ├── driving/       # primários: CLI, GUI (chamam o núcleo)
│   │   ├── cli/
│   │   └── gui/
│   └── driven/        # secundários: núcleo chama I/O via ports
│       ├── ollama/            # implementa EmbedderPort
│       ├── lancedb/           # implementa VectorStorePort
│       ├── cross_encoder/     # implementa RerankerPort
│       ├── loaders/           # implementa LoaderPort (pdf/docx/epub/text)
│       └── config/            # TOML loader
└── composition/       # wiring/DI: liga ports ↔ adapters
    └── container.py
```

**Regras invioláveis:**

1. `domain/` nunca importa de `adapters/`, `application/`, libs externas ou stdlib de I/O.
2. `application/` só conhece `domain/` (inclui `domain/ports/`).
3. `adapters/driven/` implementam os Protocols de `domain/ports/`.
4. `adapters/driving/` só conversam com `application/` via `composition/container`.
5. Libs externas (lancedb, ollama, pypdf, PySide6, etc.) só aparecem em `adapters/`.

## Pendências

A tabela de pendências e planejamento do projeto está em `TODO.md` na raiz.

Regra crítica: **nenhuma linha de código é escrita antes que a tarefa correspondente exista na tabela e o usuário autorize a execução**. Ver `TODO.md` para IDs, status e ordem das fases.

## Referências

- Plano de arquitetura completo: `/home/petrus/.claude/plans/vou-refazer-o-projeto-serene-robin.md`
- Auditoria do legacy: conversa original desta sessão.
