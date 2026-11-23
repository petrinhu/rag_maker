# Arquitetura do rag_maker

Mapa de `src/rag_maker/`. As regras de dependência entre as camadas estão na RM-04 do `GODS_LAWS.md`.

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
