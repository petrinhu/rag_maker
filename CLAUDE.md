# rag_maker

Ferramenta de recuperação (retrieval-only) offline para construção de bibliografia pessoal e assistência a IAs externas (Claude Code / ChatGPT / Gemini) que consomem trechos brutos e redigem resumos, artigos e livros.

## Estrutura

- `src/rag_maker/`: o projeto novo (criado a partir da Fase 1), em arquitetura hexagonal; mapa em [`docs/claude/arquitetura.md`](docs/claude/arquitetura.md).
- `legacy/`: o projeto antigo, só leitura (RM-02).

## Docs

- `AGENTS.md`: contrato formal que instrui as IAs externas a chamar a CLI e interpretar as respostas.
- Plano de arquitetura completo: `/home/petrus/.claude/plans/vou-refazer-o-projeto-serene-robin.md`.
- Auditoria do legacy: conversa original desta sessão.

## Leis do projeto

Leia [`GODS_LAWS.md`](GODS_LAWS.md) antes de agir. `L-NN` sem prefixo é lei global.

| Lei | Gatilho: dispara quando você vai... |
|---|---|
| [RM-01](GODS_LAWS.md#rm-01) | escolher ou ligar modelo local, ou gerar texto no app |
| [RM-02](GODS_LAWS.md#rm-02) | abrir, editar ou importar algo de `legacy/` |
| [RM-03](GODS_LAWS.md#rm-03) | fazer qualquer alteração, ou escrever código |
| [RM-04](GODS_LAWS.md#rm-04) | criar módulo, escrever import ou ligar adapter |

## Pendências

A tabela de pendências e planejamento do projeto está em `TODO.md` na raiz.
