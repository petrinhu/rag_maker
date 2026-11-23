# GODS_LAWS.md: rag_maker

> Ordens do líder para este projeto. Cada lei tem um gatilho, conferido no momento da ação.

## Protocolo de uso

1. Antes de agir, confira o índice de gatilhos do `CLAUDE.md` deste projeto; se um gatilho casa, leia a lei inteira antes do primeiro comando.
2. Siga o protocolo de uso do `~/.claude/GODS_LAWS.md`. No que este arquivo silencia, vale a lei global; `L-NN` sem prefixo é lei global e `RM-NN` é lei daqui.

---

## RM-01

**Data:** regra permanente.

Use como único modelo local o `bge-m3:latest` via Ollama, só para embeddings (dim=1024). Não use LLM local para síntese, porque quem redige é o consumidor externo (a IA).

## RM-02

**Data:** regra permanente.

Trate `legacy/` como somente leitura e nunca o importe no projeto novo, porque é o projeto antigo.

## RM-03

**Data:** regra permanente.

Consulte o `TODO.md` antes de qualquer alteração. Não escreva nenhuma linha de código antes de a tarefa correspondente existir na tabela e de o usuário autorizar a execução.

## RM-04

**Data:** regra permanente.

Siga a arquitetura hexagonal (ports e adapters) de `src/rag_maker/`, mapeada em `docs/claude/arquitetura.md`. Estas cinco regras são invioláveis:

1. Não importe em `domain/` nada de `adapters/`, de `application/`, de libs externas nem da stdlib de I/O.
2. Faça `application/` conhecer só `domain/` (inclui `domain/ports/`).
3. Faça os `adapters/driven/` implementarem os Protocols de `domain/ports/`.
4. Faça os `adapters/driving/` conversarem com `application/` só via `composition/container`.
5. Use libs externas (lancedb, ollama, pypdf, PySide6 etc.) só em `adapters/`.
