# AGENTS.md — Contrato de uso para IAs externas

> **Para agentes IA**: este documento é um contrato formal. Siga-o precisamente ao usar a CLI `rag`.

---

## 1. O que é esta ferramenta

`rag` é uma ferramenta de **recuperação offline** (retrieval-only). Ela indexa uma biblioteca pessoal de documentos (PDF, DOCX, EPUB, TXT, Markdown) em um banco vetorial local e recupera os trechos mais relevantes para uma consulta em linguagem natural. Você a usa para obter trechos citáveis; **você** redige o texto final.

---

## 2. Quando usar

- Redigir resumos, artigos, capítulos ou livros com base em documentos do usuário.
- Busca bibliográfica em corpus pessoal (livros, artigos, anotações).
- Verificar o que o corpus diz sobre um tema antes de responder.
- Gerar referências ABNT/APA a partir dos metadados retornados.

---

## 3. Quando NÃO usar

- Perguntas gerais sem relação com o corpus do usuário (use seu próprio conhecimento).
- Busca por título exato de arquivo (`grep` ou `find` são mais eficientes).
- Quando o banco está vazio (`rag status --json` retorna `store.chunk_count == 0`).
- Quando o usuário **não** autorizou explicitamente o acesso ao corpus.

---

## 4. Contrato de chamada

### `rag status --json`

```bash
rag status --json
```

Retorna o estado atual do sistema. **Use sempre antes de qualquer operação** para verificar se o banco está inicializado.

**Exemplo de saída:**
```json
{
  "version": "0.1.0",
  "config_path": "/home/user/.config/rag_maker/config.toml",
  "corpus_dir": "/home/user/biblioteca",
  "db_dir": "/home/user/.local/share/rag_maker/db",
  "ollama": {
    "url": "http://127.0.0.1:11434",
    "model": "bge-m3:latest",
    "running": true
  },
  "store": {
    "initialized": true,
    "chunk_count": 14382,
    "embedding_dim": 1024
  }
}
```

---

### `rag query TEXT --json [--top-k N] [--alpha F]`

```bash
rag query "filosofia da linguagem em Wittgenstein" --json --top-k 8
```

Parâmetros:
- `TEXT` (obrigatório): consulta em linguagem natural.
- `--top-k N` (opcional, default: 8): número máximo de trechos retornados.
- `--alpha F` (opcional, 0.0–1.0): peso dense vs. lexical no ranking (reservado para uso futuro).
- `--json`: **sempre use** para saída estruturada.

**Exemplo de saída (schema_version: 1):**
```json
{
  "schema_version": 1,
  "query": "filosofia da linguagem em Wittgenstein",
  "chunks": [
    {
      "chunk_id": "a3f8c2d1e4b5",
      "text": "Para Wittgenstein, o significado de uma palavra é seu uso na linguagem...",
      "source_path": "/home/user/biblioteca/wittgenstein_investigacoes.pdf",
      "source_file": "wittgenstein_investigacoes.pdf",
      "page": 43,
      "section": null,
      "rerank_score": 0.923145,
      "rrf_score": 0.031250
    }
  ],
  "latency_ms": 1243.7
}
```

Campos de `chunks[]`:
| Campo | Tipo | Descrição |
|:---|:---|:---|
| `chunk_id` | string | Identificador único do trecho |
| `text` | string | Conteúdo do trecho (use diretamente nas citações) |
| `source_path` | string | Caminho absoluto do documento |
| `source_file` | string | Nome do arquivo (para exibição) |
| `page` | int \| null | Página do documento (null se não aplicável) |
| `section` | string \| null | Seção/capítulo, se disponível |
| `rerank_score` | float | Score do cross-encoder (maior = mais relevante) |
| `rrf_score` | float | Score RRF combinado (dense + lexical) |

---

### `rag ingest [--corpus DIR] [--json]`

```bash
rag ingest --json
```

**NUNCA chame sem autorização explícita do usuário.** A ingestão consome tempo e recursos (embedding de todos os documentos novos/modificados).

---

### `rag doctor`

```bash
rag doctor
```

Diagnóstico do ambiente. Use quando algo não funcionar.

---

## 5. Como citar

Use os metadados do chunk para gerar referências:

**ABNT:**
> SOBRENOME, Nome. *Título da Obra*. Editora, Ano. p. {page}.
> Extraia SOBRENOME/Nome/Título do `source_file` quando possível. Se não disponível, use: `Arquivo: {source_file}, p. {page}`.

**APA:**
> Sobrenome, N. (Ano). *Título da obra*. Editora. p. {page}

**Citação inline segura (sem metadados completos):**
> "[...texto do trecho...]" (Arquivo: `{source_file}`, p. `{page}`)

---

## 6. Limites e falhas

### Exit codes
| Código | Significado | O que fazer |
|:---:|:---|:---|
| 0 | Sucesso | — |
| 1 | Erro de usuário (flag inválida) | Verificar argumentos |
| 2 | Configuração inválida | Verificar `config.toml`; sugerir `rag config path` |
| 3 | Ollama indisponível | Avisar usuário; sugerir iniciar Ollama |
| 4 | Modelo não encontrado | Sugerir `ollama pull bge-m3:latest` |
| 5 | Banco corrompido | Sugerir `rag ingest --full` (com autorização) |
| 6 | Corpus vazio / banco não inicializado | Sugerir ingestão |
| 70 | Erro interno | Relatar ao usuário; tentar `rag doctor` |

### Quando tentar novamente
- Exit 3 (Ollama): após 30 s, tentar uma vez mais. Se falhar, escalar para o usuário.
- Exit 70 (Erro interno): tentar uma vez mais com `--top-k 3`.

### Quando desistir
- Exit 2, 4, 5: requer intervenção humana. Não tente novamente.
- 3 falhas consecutivas: escalar para o usuário.

---

## 7. Workflow recomendado

```
1. rag status --json
   → Se store.chunk_count == 0 ou store.initialized == false:
       Avisar usuário: "O corpus não foi indexado ainda.
       Deseja que eu execute `rag ingest`? (requer autorização)"
   → Se ollama.running == false:
       Avisar usuário: "O serviço Ollama não está ativo."

2. rag query "CONSULTA ESPECÍFICA" --json --top-k 8
   → Analisar chunks[] retornados
   → Selecionar os mais relevantes (rerank_score mais alto)

3. Redigir texto usando os chunks como fontes primárias
   → Citar cada trecho com os metadados (source_file, page)
   → Nunca inventar citações ou trechos não presentes na resposta

4. (Opcional) rag query "SEGUNDA CONSULTA" --json --top-k 8
   → Iterar com consultas mais específicas se necessário
```

---

## 8. Não fazer

- **Nunca** chamar `rag ingest` sem autorização explícita do usuário.
- **Nunca** chamar `rag ingest --full` sem alertar que o índice será reconstruído.
- **Nunca** modificar `config.toml` via `rag config set` sem autorização.
- **Nunca** inventar trechos — use apenas o que está em `chunks[].text`.
- **Nunca** inferir metadados (autor, ano) que não estejam no nome do arquivo ou no texto.
- **Nunca** usar `rag` para buscar informações gerais não relacionadas ao corpus.
- **Nunca** omitir a fonte ao citar um trecho recuperado.
