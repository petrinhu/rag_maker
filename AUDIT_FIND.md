# Dossiê de Auditoria Interna — rag_maker

**Data:** 2026-07-11
**Auditor responsável (consolidação):** internal-auditor (Fable 5)
**Projeto:** rag_maker — ferramenta de recuperação (retrieval-only) offline; arquitetura hexagonal (Ports & Adapters); modelo local único `bge-m3:latest` via Ollama; reranker `BAAI/bge-reranker-v2-m3`; store LanceDB.

## 1. Escopo e método

### Escopo auditado
- **Incluído:** todo o código novo em `src/rag_maker/` (domain, application, adapters driving/driven, composition), a suíte de testes (`tests/`), o pipeline de CI (`.forgejo/workflows/ci.yml`), hooks (`.pre-commit-config.yaml`), scripts (`scripts/preci.sh`), metadados de empacotamento (`pyproject.toml`, wheel/sdist gerado), e os documentos de contrato/consumo (`CONTRACT.md`, `AGENTS.md`, `README.md`, `TODO.md`, `rag_maker.toml.example`).
- **Explicitamente NÃO auditado:** o diretório `legacy/` (projeto antigo, somente-leitura, nunca importado pelo novo — fora de escopo por decisão de arquitetura do projeto).

### Lentes rodadas
Cinco lentes de auditoria: **INPUT** (validação/robustez de entrada), **SEC** (segurança, supply-chain, hardening, LGPD), **CORRECT** (corretude de domínio/pipeline), **TEST** (rede de segurança de testes e CI), **CI/DOCS** (gates de pipeline e fidelidade da documentação ao código).

### Método (três papéis distintos)
1. **Finder (Sonnet 5):** varreu cada lente e levantou achados candidatos com repro proposto.
2. **Verificador adversarial (distinto do finder):** para cada achado, LEU o código real e EXECUTOU o repro (via `uv run`), com mandato de refutar. Reclassificou severidades onde a evidência divergiu do finder (ex.: AUD-SEC-2 rebaixado CRÍTICO→IMPORTANTE; AUD-INPUT-4 e AUD-SEC-6 subidos COSMÉTICO→IMPORTANTE; AUD-TEST-3b subido IMPORTANTE→CRÍTICO após repro real de 20 GB de RSS).
3. **Consolidação (Fable 5):** este documento — reúne, classifica e rastreia; não re-executa.

### Calibração de porte
Projeto **solo / early-stage** (retrieval-only, single-user, offline, sem superfície de rede exposta). Severidade segue [[AUDITORIAS]] sem inflar nem minimizar: como não há multi-tenant nem exposição de rede, os vetores de segurança de rede/auth têm superfície mínima; o peso real recai sobre **robustez de entrada de arquivos não confiáveis** (o produto ingere PDFs/EPUBs/DOCX baixados da internet), **corretude do índice** (propósito central do produto) e **gates de pipeline prometidos mas inativos**.

> Nota de pré-flight: existe `TODO.md` na raiz — o trabalho abaixo referencia os IDs de tarefa (F1.14, F1.15) quando relevantes. Não há divergência de onda a sinalizar.

---

## 2. Sumário executivo

**Contagem por severidade** (somente CONFIRMADOS + PLAUSÍVEIS; nenhum achado foi refutado):

| Severidade | Quantidade |
|---|---|
| 🔴 CRÍTICO | 7 |
| 🟠 IMPORTANTE | 16 |
| 🟢 COSMÉTICO | 5 |
| **Total** | **28** (27 confirmados + 1 plausível) |

**Postura geral:** o rag_maker tem um **núcleo de domínio sólido e honestamente testado** — RRF com testes de propriedade (Hypothesis), reranker com fakes precisos, chunker bem coberto — e os gates que de fato rodam (ruff, mypy --strict, import-linter, bandit) estão verdes de verdade, não são teatro. Mas o projeto **não está pronto para um auditor externo** por três razões estruturais confirmadas com repro executável: (1) a superfície de ingestão de arquivos não confiáveis não tem **nenhum** guard de tamanho/descompressão — um EPUB de 2,1 MB derruba o processo com ~20 GB de RSS (DoS trivial); (2) o pipeline de retrieval sofre **corrupção silenciosa e permanente do índice** ao reingerir arquivos modificados e a **busca lexical (FTS) está morta em produção**, degradando exatamente a proposta de valor do produto sem qualquer sinal de erro; (3) o CI só roda metade da suíte, o gate de cobertura e o `pip-audit` (MUST explícito do CONTRACT.md) são **configuração morta**, deixando 27 CVEs conhecidas e regressões nos adapters de I/O passarem para uma tag pública sem alarme. Nenhum 🔴 fica sem plano de remediação. O livro é honesto: lista o que falhou, não maquia.

---

## 3. Índice mestre

| ID | Lente | Severidade | Veredito | Título |
|---|---|---|---|---|
| AUD-INPUT-2 | INPUT | 🔴 CRÍTICO | CONFIRMADO | Loaders sem guard de tamanho/descompressão — zip-bomb e arquivo gigante sem limite |
| AUD-CORRECT-1 | CORRECT | 🔴 CRÍTICO | CONFIRMADO | Reingestão de arquivo modificado não remove chunks órfãos — corrupção silenciosa do índice |
| AUD-TEST-1 | TEST | 🔴 CRÍTICO | CONFIRMADO | CI roda só testes unit (47% da suíte) — integration/e2e nunca validam |
| AUD-TEST-2 | TEST | 🔴 CRÍTICO | CONFIRMADO | Busca lexical (FTS) morta em produção — `ensure_fts_index()` nunca chamado |
| AUD-TEST-3 | TEST | 🔴 CRÍTICO | CONFIRMADO | DOCX/EPUB sem limite de descompressão — DoS (176s, 1.8GB de <1MB) |
| AUD-TEST-3b | TEST | 🔴 CRÍTICO | CONFIRMADO | EPUB decompression bomb confirmado (~20 GB de RSS a partir de 2,1 MB) |
| AUD-CIDOCS-1 | CI/DOCS | 🔴 CRÍTICO | CONFIRMADO | pip-audit é MUST no CONTRACT.md mas nunca roda; 27 CVEs não detectadas |
| AUD-INPUT-1 | INPUT | 🟠 IMPORTANTE | CONFIRMADO | PdfLoader guarda só a abertura; laço de extração escapa exceção crua |
| AUD-INPUT-3 | INPUT | 🟠 IMPORTANTE | CONFIRMADO | TextLoader sempre decodifica via latin-1 — binário disfarçado indexado como lixo |
| AUD-INPUT-4 | INPUT | 🟠 IMPORTANTE | CONFIRMADO | CLI `--top-k` aceita negativo/zero sem validação — slice silenciosamente errado |
| AUD-SEC-1 | SEC | 🟠 IMPORTANTE | CONFIRMADO | Gate SCA (pip-audit) declarado mas nunca executado em CI/pre-commit |
| AUD-SEC-3 | SEC | 🟠 IMPORTANTE | CONFIRMADO | bandit `severity: medium` suprime classe Low sem `#nosec`/justificativa |
| AUD-SEC-5 | SEC | 🟠 IMPORTANTE | CONFIRMADO | Download de modelos ML (HF + Ollama) sem pin de integridade/revisão |
| AUD-SEC-6 | SEC | 🟠 IMPORTANTE | CONFIRMADO | Paths ignorados usam prefix-match de string — casa diretório-irmão por engano |
| AUD-TEST-4 | TEST | 🟠 IMPORTANTE | CONFIRMADO | Ciclo de vida do daemon Ollama (spawn/wait/pull) sem nenhum teste |
| AUD-TEST-5 | TEST | 🟠 IMPORTANTE | CONFIRMADO | Retry-com-backoff do OllamaEmbedder nunca exercitado por teste |
| AUD-TEST-6 | TEST | 🟠 IMPORTANTE | CONFIRMADO | cli/main.py: coverage cego + comandos reais (ingest/doctor) sem teste |
| AUD-CIDOCS-2 | CI/DOCS | 🟠 IMPORTANTE | CONFIRMADO | Exit code 5 ("banco corrompido") é código morto; corrupção cai em exit 6 |
| AUD-CIDOCS-3 | CI/DOCS | 🟠 IMPORTANTE | CONFIRMADO | CI só `pytest -m unit`; integration/e2e nunca rodam, inclusive no release |
| AUD-CIDOCS-4 | CI/DOCS | 🟠 IMPORTANTE | CONFIRMADO | Gate de cobertura (`fail_under=70`) é config morta (`--no-cov`) |
| AUD-CIDOCS-5 | CI/DOCS | 🟠 IMPORTANTE | CONFIRMADO | pyproject.toml não declara `license`/classifier AGPL no metadata do wheel |
| AUD-CIDOCS-8 | CI/DOCS | 🟠 IMPORTANTE | CONFIRMADO | `[retrieval].alpha` documentado como knob funcional, mas é dead config |
| AUD-SEC-2 | SEC | 🟠 IMPORTANTE | PLAUSÍVEL | pypdf 6.10.2 desatualizado com múltiplas CVEs de DoS reachable |
| AUD-SEC-4 | SEC | 🟢 COSMÉTICO | CONFIRMADO | Nenhuma ferramenta de secret-scanning em pre-commit/CI |
| AUD-CORRECT-2 | CORRECT | 🟢 COSMÉTICO | CONFIRMADO | Coluna `content_hash` no schema LanceDB sempre vazia e nunca lida |
| AUD-TEST-7 | TEST | 🟢 COSMÉTICO | CONFIRMADO | Parâmetro `alpha` é no-op documentado mas sem teste que fixe o comportamento |
| AUD-CIDOCS-6 | CI/DOCS | 🟢 COSMÉTICO | CONFIRMADO | Nenhum dos 44 .py em src/ carrega header SPDX-License-Identifier |
| AUD-CIDOCS-7 | CI/DOCS | 🟢 COSMÉTICO | CONFIRMADO | AGENTS.md §4 omite flags `--full`/`--yes` que o próprio doc referencia |

---

## 4. Achados CONFIRMADOS

### AUD-INPUT-2 — Loaders sem guard de tamanho/descompressão (zip-bomb e arquivo gigante)

- **Severidade:** 🔴 CRÍTICO
- **Símbolo/arquivo:** `DocxLoader.load` / `EpubLoader.load` / `TextLoader._read` / `PdfLoader.load` — `src/rag_maker/adapters/driven/loaders/{docx,epub,text,pdf}.py`; call-site `application/ingest_use_case.py:169`

**Failure (input → efeito):** nenhum loader (nem `_utils.sha256_file`) checa `path.stat().st_size` nem o tamanho de descompressão ANTES de entregar o arquivo para python-docx/ebooklib/pypdf/`read_text()`. Um `.docx`/`.epub` de ~600 KB com XML altamente compressível (ratio ~1000:1) força alocação de centenas de MB a GB. Sem `ulimit`, a alocação tem sucesso silencioso; escalando a razão de compressão, um arquivo de poucos MB força OOM-kill do processo `rag ingest` pelo kernel (SIGKILL que nenhum try/except captura). O mesmo, sem componente zip, vale para TextLoader (`read_text()`) e PdfLoader (assembla `content` inteiro em memória).

**Repro:** criar `.docx` de 615 KB com `word/document.xml` de ~600 MB (payload fatiado em 120 nós `<w:t>` de 5 MB para contornar o limite incidental de nó-único do libxml2), depois `DocxLoader().load(...)`.

**Evidência observada:** repro executado sem `ulimit` (ambiente real). Resultado: `LOADED_OK len=629145719` (~600 MB de conteúdo), **sem exceção**, RSS de pico medido por `/usr/bin/time -v` = **1.891.056 KB (~1,9 GB)** a partir de arquivo de 615 KB (amplificação ~3070:1 arquivo→RSS). Nota adversarial: a primeira tentativa (payload num nó de texto único) falhou por um limite incidental do libxml2 (`Text node too long`, ~10 MB), o que poderia ter levado a refutar — mas o verificador demonstrou que esse "guard" é acidental e trivialmente contornável fatiando o payload em nós menores, preservando o mesmo arquivo minúsculo. EPUB confirmado análogo (ver AUD-TEST-3b). TextLoader e PdfLoader lidos linha a linha: montam conteúdo inteiro sem checagem. `grep` por `max_file_size|st_size|file_size|max_size` = zero em `src/`. Auditoria-dominó: ausência uniforme nos 4 loaders + `_utils.py`.

**Remediação sugerida:** (1) checar `path.stat().st_size` contra `max_file_size_mb` configurável (AppConfig) e recusar com `LoadError` antes de abrir; (2) para docx/epub (zip-based), abrir com `zipfile.ZipFile` e somar `zi.file_size` de `infolist()` contra um teto (ex.: 200 MB) ANTES de deixar python-docx/ebooklib descomprimir. Os limites incidentais de parsers não são confiáveis (ebooklib decodifica o item cru ANTES de qualquer parsing).

---

### AUD-CORRECT-1 — Reingestão não remove chunks órfãos: corrupção silenciosa e permanente do índice

- **Severidade:** 🔴 CRÍTICO
- **Símbolo/arquivo:** `IngestUseCase.ingest_incremental` / `_ingest_file` (`application/ingest_use_case.py`) + `RecursiveCharacterChunker._make_chunk_id` (`domain/chunker.py:41-43`) + `LanceVectorStore.upsert` (`adapters/driven/lancedb/vector_store.py`)

**Failure (input → efeito):** `chunk_id = sha256(f"{path}:{offset}")[:24]` depende só de path+offset, nunca do conteúdo. No caminho `changes.modified`, `ingest_incremental` chama só `_ingest_file` + `store.upsert(indexed)` — nunca `delete_by_source(path)` antes de reinserir (`delete_by_source` só roda para `changes.removed`). `merge_insert("chunk_id")` só atualiza/insere por chunk_id, nunca deleta o que não veio no lote novo. Se o documento editado gera MENOS chunks (ou offsets diferentes), os chunks antigos permanecem no LanceDB para sempre e continuam sendo retornados por `hybrid_search` como se fossem conteúdo atual — a IA consumidora recebe trechos que não existem mais no documento fonte, sem erro, sem log.

**Repro (executado contra a stack real, só embedder fake):**
```python
f.write_text('A' * 3000)   # -> 4 chunks
uc.ingest_incremental(corpus); print(store.count())  # 4
f.write_text('B' * 20)     # -> 1 chunk (arquivo encolheu)
uc.ingest_incremental(corpus); print(store.count())  # 4  <-- BUG: deveria ser 1
```

**Evidência observada:** saída real `after modify+ingest: updated=1 count=4`; `sources: {'.../doc.txt': 4}` — 3 dos 4 chunks continuam sendo `'AAAA...'` mesmo após o arquivo virar 20 'B'. O verificador foi além e chamou `hybrid_search()` pelo termo antigo `'AAAAAAAAAA'`: os 3 chunks órfãos são efetivamente retornados (e melhor ranqueados que o chunk atual). Confirmado também que `recreate_all` NÃO tem o bug (apaga por source antes de reingerir). É plausível em uso real: qualquer edição que reduza a contagem de chunks (cortar parágrafo, resumir) dispara a corrupção.

**Remediação sugerida:** no branch `modified` de `ingest_incremental`, chamar `self._store.delete_by_source(str(path))` antes de `upsert(indexed)` (ou tornar delete-then-insert o padrão para qualquer arquivo reprocessado). Adicionar teste de integração cobrindo arquivo que encolhe/muda de chunk count entre duas ingestões (hoje ausente). Observação: `content_hash` no schema é campo morto (ver AUD-CORRECT-2) — decisão de design a levar ao TODO.md, não inline.

---

### AUD-TEST-1 — CI roda apenas testes unit (47% da suíte)

- **Severidade:** 🔴 CRÍTICO
- **Símbolo/arquivo:** job `smoke`, step "Unit tests" — `.forgejo/workflows/ci.yml:67-72`

**Failure (input → efeito):** o único workflow roda `uv run pytest -m unit -q --no-cov`. `-m unit` coleta 82/155; `-m integration` (65) e `-m e2e` (8) — 73 testes cobrindo vector_store/hybrid_search, ingest, loaders, embedder/manager e todo o CLI — nunca rodam em CI. Um PR pode quebrar hybrid_search, um loader, o CLI inteiro ou a integração Ollama e o CI fica verde. O `--no-cov` desativa o gate `fail_under=70`.

**Repro:** `pytest -m unit --collect-only -q` → 82/155; `pytest --cov=src/rag_maker -q` → FAIL 67.44% < 70%.

**Evidência observada:** 82+65+8 = 155 confirmado; suíte completa com cobertura ativa → `TOTAL 67% ... FAIL Required test coverage of 70.0% not reached. Total coverage: 67.44% / 155 passed in 113.68s`. Ambiente tinha Ollama real (`0.17.7`); integration+e2e rodam local em ~114s. Achado-irmão: o job `release` (publica em tags `v*`) depende só de `needs: smoke` — uma tag pública pode sair com hybrid_search ou CLI quebrados e o release passa verde.

**Remediação sugerida:** adicionar steps `-m integration` (mock via respx) e `-m e2e` (CLI via subprocess) no smoke job; rodar com `--cov` mantendo `fail_under=70`. Testes que exigem Ollama real/modelo HF cacheado ficam em job separado/nightly.

---

### AUD-TEST-2 — Busca lexical (FTS) morta em produção

- **Severidade:** 🔴 CRÍTICO
- **Símbolo/arquivo:** `LanceVectorStore.hybrid_search` / `ensure_fts_index` — `adapters/driven/lancedb/vector_store.py:103-157`

**Failure (input → efeito):** `ensure_fts_index()` é a única forma de criar o índice invertido exigido pelo LanceDB antes de `search(text, query_type="fts")`, mas `grep -rn ensure_fts_index src/` mostra ZERO chamadas (só a definição). Sem o índice, a busca FTS levanta `RuntimeError: Cannot perform full text search unless an INVERTED index has been created`, capturado pelo `except Exception: pass` (linha 121-122) que degrada silenciosamente para dense-only, todo request, para sempre. A "hybrid search" (RRF dense+lexical) documentada na docstring da classe (linha 17: "HNSW + FTS via tantivy") nunca funciona como projetada.

**Repro:** `hybrid_search(qv, 'hermetismo rosacruz', top_n=5)` com um chunk só-lexical e outro só-denso; depois `store._table.search('hermetismo', query_type='fts')`.

**Evidência observada:** `hybrid_search` retornou `[('c1', 0.0), ('c2', 0.0)]` — `lexical_score=0.0` para AMBOS, a fusão lexical nunca contribuiu. A chamada FTS direta produziu `RuntimeError ... Cannot perform full text search unless an INVERTED index has been created` — exatamente a exceção que o `except Exception: pass` engole. Testes existentes (`test_hybrid_search_returns_results`, `test_hybrid_search_top_n_respected`) passam com FTS 100% quebrado porque não afirmam nada sobre `lexical_score`. `ensure_vector_index` (HNSW) também não é chamado, mas o LanceDB faz fallback automático para flat scan sem erro — comportamento aceitável, não é achado.

**Remediação sugerida:** chamar `ensure_fts_index()` (e `ensure_vector_index()`) no `__init__`/`_open_or_create` do adapter (cobre chamadores futuros); trocar o `except Exception: pass` por log explícito + métrica; adicionar teste de integração que force um chunk recuperável SÓ via lexical (falharia hoje).

---

### AUD-TEST-3 — DOCX/EPUB sem limite de descompressão: DoS

- **Severidade:** 🔴 CRÍTICO
- **Símbolo/arquivo:** `DocxLoader.load` (`docx.py:15-32`) / `EpubLoader.load` (`epub.py:17-40`)

**Failure (input → efeito):** nenhum dos dois impõe limite de tamanho descomprimido, número de entradas no zip ou timeout antes de delegar a python-docx/ebooklib, que descomprimem e fazem parse DOM completo em memória. Como `rag ingest` processa arquivo por arquivo sequencialmente (`ingest_use_case.py:207-236`), um único arquivo malicioso trava/derruba (OOM-kill) o processo de ingest inteiro — nenhum outro arquivo é processado até esse terminar ou o processo morrer.

**Repro:** `.docx` de ~1 MB com `word/document.xml` altamente compressível (2M parágrafos), depois medir `DocxLoader().load()` com `resource.getrusage`.

**Evidência observada:** DOCX de 1.032.721 bytes → `document.xml` de 266 MB (ratio ~257:1): **138,6s de CPU, 1.844 MB de RSS de pico**, sem erro nem timeout. EPUB de 734 KB → `chap1.xhtml` de 216 MB (ratio ~294:1): **55,9s de CPU, 4.798 MB de RSS de pico** (~2,6x pior que DOCX, provavelmente por BeautifulSoup construir DOM completo). Processamento sequencial confirmado em `ingest_use_case.py:207-208`. Zero guard em ambos.

**Remediação sugerida:** antes de abrir com python-docx/ebooklib, validar o zip com `zipfile.ZipFile` + somar `ZipInfo.file_size` de todas as entradas (teto ex.: 200 MB, configurável) e rejeitar com `LoadError`; checar `len(infolist())` para limitar número de entradas; complementar com limite de RATIO de compressão (>100:1 já suspeito). Teste de loader com fixture de bomb pequena afirmando `LoadError` rápido.

---

### AUD-TEST-3b — EPUB decompression bomb confirmado (~20 GB de RSS a partir de 2,1 MB)

- **Severidade:** 🔴 CRÍTICO (subido de IMPORTANTE pelo verificador após repro real)
- **Símbolo/arquivo:** `EpubLoader.load` — `epub.py:17-40`

**Failure (input → efeito):** `epub.read_epub()` (ebooklib) descomprime e materializa em memória TODOS os itens do manifesto (`ei.content = self.read_file(...)` → `zf.read(name)`) de forma incondicional durante o parse — pior que o DOCX, que só descomprime o item lido. Sem qualquer checagem de tamanho antes ou depois.

**Repro:** `.epub` válido de 2,1 MB com um único item XHTML que descomprime para ~600 MB, depois `EpubLoader().load(path)` medindo `ru_maxrss`.

**Evidência observada:** saída real: `ok=True content_len=557243245 elapsed=254.44s ... delta_mb=19682.4`; `/usr/bin/time -v` → **Maximum resident set size = 20.201.068 KB (~20,2 GB)**, User time 253.47s, 99% CPU, wall 4:27.81. Arquivo de 2,1 MB → ~20 GB de RSS e ~4m27s a 99% CPU, sem limite/erro, `load()` retornou `ok=True`. Em hardware de consumidor (8-16 GB RAM) isso resulta em OOM-kill/pressão de swap no sistema todo. O payload nem é otimizado (ratio ~285:1). Inspeção de `ebooklib/epub.py::EpubReader._load_manifest` (linhas ~1560-1608) confirma a decodificação eager.

**Remediação sugerida:** idêntica a AUD-TEST-3 — antes de `epub.read_epub()`, abrir com `zipfile.ZipFile` e checar `ZipInfo.file_size` de cada entrada do manifesto contra teto configurável, rejeitando com `LoadError` antes de descomprimir. Grep por `zipfile`/`ZipFile` em `loaders/` para achar gêmeos.

---

### AUD-CIDOCS-1 — pip-audit é MUST no CONTRACT.md mas nunca roda; 27 CVEs não detectadas

- **Severidade:** 🔴 CRÍTICO
- **Símbolo/arquivo:** `jobs.smoke` (`.forgejo/workflows/ci.yml`); `scripts/preci.sh`; `.pre-commit-config.yaml`

**Failure (input → efeito):** CONTRACT.md §8.1 (A06, linha 903) diz "MUST rodar `pip-audit` no CI. Zero CRITICAL unpatched" e §11.2 lista "pip-audit: 0 CRITICAL unpatched" como Minimum Quality Gate MUST antes de release. Nenhum dos três lugares (ci.yml, pre-commit, preci.sh) invoca pip-audit; ele só existe como dev-dependency solta. TODO.md marca F1.14 ("script `uv run pip-audit` no dev workflow") como ✅ Concluído, mas o script não existe.

**Repro:** `grep -n 'pip-audit' .forgejo/workflows/ci.yml .pre-commit-config.yaml scripts/preci.sh` (0 matches); `uv run pip-audit`.

**Evidência observada:** grep = zero matches nos três arquivos. `uv run pip-audit` → **"Found 27 known vulnerabilities in 11 packages"**: cryptography, idna, langchain-core, langsmith, msgpack, pip, pydantic-settings, pypdf (9 CVEs), soupsieve, torch, urllib3. `pypdf` é usado ativamente em `loaders/pdf.py` para parsear PDFs do corpus do usuário — superfície de ataque real de input não confiável. F1.14 no TODO.md (linha 61) marcado ✅ quando o artefato prometido não existe.

**Remediação sugerida:** adicionar `uv run pip-audit --strict` (ou com `--ignore` datado/justificado) em `jobs.smoke` antes do build, e o mesmo em `scripts/preci.sh`. Corrigir F1.14 no TODO.md para 🔍 Pendente verificação. Bump das deps vulneráveis (especialmente pypdf — ver AUD-SEC-2). Adicionar o gate como pré-requisito do job `release`.

---

### AUD-INPUT-1 — PdfLoader guarda só a abertura; laço de extração escapa exceção crua

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `PdfLoader.load` — `src/rag_maker/adapters/driven/loaders/pdf.py`

**Failure (input → efeito):** o `try/except PdfReadError` (linhas 20-25) cobre só `PdfReader(str(path))`; o laço `[page.extract_text() or "" for page in reader.pages]` (linha 27) e `len(reader.pages)` (linha 38) ficam FORA do try. Um PDF com árvore de páginas cíclica abre com sucesso mas dispara `PdfReadError: Detected cyclic page references.` ao acessar `.pages` (lazy), escapando crua de `load()` em vez de virar `LoadError`. O processo não crasha (o `except Exception` genérico de `ingest_incremental` captura), mas `report.errors` guarda o traceback interno do pypdf em vez da mensagem limpa/bilíngue dos outros loaders, degradando a mensagem ao usuário.

**Repro:** construir PDF cíclico mínimo (Pages com `Kids[2 0 R]` apontando para si), depois `PdfLoader().load(Path('/tmp/cyclic.pdf'))`.

**Evidência observada:** saída `ESCAPED as raw exception (BAD): <class 'pypdf.errors.PdfReadError'> Detected cyclic page references.`. Auditoria-dominó: `docx.py` e `epub.py` envolvem TODO o corpo num único `try/except Exception` → `LoadError`; `pdf.py` é o único com try estreito. Ressalva: não existe teste específico de PdfLoader para caminho de erro (só TextLoader vazio/unsupported), mas o padrão de contrato é visivelmente seguido pelos outros dois loaders.

**Remediação sugerida:** mover TODO o corpo de `load()` (construção + laço + `page_count`) para dentro de um `try/except Exception` amplo, sempre relançando como `LoadError(...)`, alinhando ao padrão dos outros 3 loaders.

---

### AUD-INPUT-3 — TextLoader sempre decodifica via latin-1; binário disfarçado indexado como lixo

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `TextLoader._read` — `src/rag_maker/adapters/driven/loaders/text.py`

**Failure (input → efeito):** `_ENCODINGS = ("utf-8", "utf-8-sig", "latin-1", "cp1252")` (linha 9); latin-1 mapeia todo byte 0x00–0xFF para um code point válido, então `read_text(encoding="latin-1")` NUNCA levanta `UnicodeDecodeError` — o `raise LoadError(...)` (linha 35) é código morto. Um binário disfarçado de `.txt`/`.md` é "carregado" como mojibake e segue silenciosamente para o chunker e embedder, poluindo o índice de uma ferramenta cujo propósito é bibliografia confiável.

**Repro:** `cp valid.pdf disguised_binary.txt`; `TextLoader().load(Path('/tmp/disguised_binary.txt'))`.

**Evidência observada:** retornou sucesso com `content = '%PDF-1.3\n%âãÏÓ\n1 0 obj...'`, sem warning. Reforço: 2000 bytes de `os.urandom()` puro com extensão `.txt` também carregam sem erro (`len: 2000`). O roteamento em `loader_for()` é 100% por extensão (`can_load` checa só `path.suffix.lower()`), sem sniffing de magic bytes. Por transitividade, `cp1252` também é código morto (latin-1 nunca falha).

**Remediação sugerida:** (a) detector real de encoding com threshold (charset-normalizer), rejeitando com `LoadError` em baixa confiança; ou (b) checagem de proporção de caracteres de controle pós-decode; ou (c) sniffing de magic bytes no `loader_for()` ANTES de rotear — opção (c) protege TODOS os loaders contra extensão mentirosa.

---

### AUD-INPUT-4 — CLI `--top-k` aceita negativo/zero sem validação

- **Severidade:** 🟠 IMPORTANTE (subido de COSMÉTICO pelo verificador)
- **Símbolo/arquivo:** `query()` (`main.py:229`) → `QueryUseCase.answer` (`query_use_case.py:32-37`) → `CrossEncoderReranker.rerank` (`reranker.py:124`)

**Failure (input → efeito):** `top_k: Annotated[int | None, typer.Option("--top-k", ...)]` não define `min=`; o valor flui sem checagem até `ranked[:top_k]`. Com `top_k` negativo, o slice do Python usa semântica "todos menos os últimos N" em vez de erro; `--top-k 0` retorna lista vazia sem explicar. Nenhum erro/aviso ao usuário ou à IA consumidora.

**Repro:** `rag query "teste" --top-k -2 --json` e `--top-k 0 --json` contra corpus real (163443 chunks, `coarse_top_n=15`).

**Evidência observada:** `--top-k -2` → exit 0, `num chunks returned: 13` (= 15 − 2, confirmando `ranked[:-2]`); `--top-k 0` → exit 0, `num chunks returned: 0`. Nenhuma mensagem sobre `--top-k` inválido. Auditoria-dominó: `--alpha` é só passthrough reservado (não é o mesmo bug ativo); não há outro slice `[:top_k]` em outro reranker.

**Remediação sugerida:** `min=1` no `typer.Option` (Typer/Click valida automaticamente) e/ou guard explícito em `QueryUseCase.answer()` (`if top_k is not None and top_k <= 0: raise ValueError(...)`).

---

### AUD-SEC-1 — Gate SCA (pip-audit) declarado mas nunca executado

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `pyproject.toml [project.optional-dependencies].dev`; `.forgejo/workflows/ci.yml`

**Failure (input → efeito):** `pip-audit>=2.7` listado no extra `dev`, mas nenhum step de ci.yml nem hook de pre-commit o invoca. Dependências com CVE acumulam sem alarme; o scanner instalado nunca roda. (Sobreposição com AUD-CIDOCS-1, que ancora o mesmo gap no contrato formal.)

**Repro:** `grep -n "pip-audit" ci.yml .pre-commit-config.yaml` (0 matches); `.venv/bin/pip-audit --local`.

**Evidência observada:** grep = 0 matches; ci.yml roda só ruff/mypy/import-linter/bandit/pytest unit/build; pre-commit idem. `pip-audit --local` (v2.10.0) → "Found 27 known vulnerabilities in 11 packages" (mais que os 8+ estimados pelo finder). `find .forgejo` → único arquivo é ci.yml, sem workflow agendado/security.

**Remediação sugerida:** step `uv run pip-audit --local` (ou `trivy fs .`) logo após "Sync env" em ci.yml, com falha de build em CVE alto/crítico sem exceção rastreada; schedule semanal para CVEs publicadas após o último commit.

---

### AUD-SEC-3 — bandit `severity: medium` suprime classe Low sem justificativa

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `bandit.yaml`; step "Bandit" em `ci.yml:65`

**Failure (input → efeito):** `bandit.yaml` define `severity: medium` e a CI roda `bandit ... --severity-level medium`; pre-commit roda `bandit -r src/ -ll` (mesmo piso). É floor global, não supressão pontual com `# nosec BXXX` + risco documentado. Sem o piso aparecem 10 achados Low (subprocess sem shell, `os.startfile`) que nunca aparecem em log de CI, mascarando qualquer achado Low futuro (tempfile.mktemp, random não-cripto, bind 0.0.0.0) sem rastro de decisão.

**Repro:** `bandit -r src/rag_maker -x legacy,.venv,tests -q` (10 Low) vs `bandit -c bandit.yaml -r src/rag_maker -q` (0).

**Evidência observada:** 10 issues Low reais: `ollama/manager.py:39` (B603, `Popen(["ollama","serve"])`), `query_panel.py:4` (B404), `:145` (B607+B603, `xdg-open`), `:147` (`open`), `:149` (B606, `os.startfile`). "Total lines skipped (#nosec): 0". Comando exato do CI → "No issues identified.". Auditoria-dominó: o finder citou só query_panel.py; o 4º ponto (`manager.py:39`) precisa entrar na remediação. Nuance: a supressão é 100% por severidade, não por confidence.

**Remediação sugerida:** trocar o floor global por supressão pontual documentada (`# nosec B603,B607 -- args são lista fixa, sem input do usuário`) nas linhas de query_panel.py **e** manager.py:39; voltar bandit.yaml para severity padrão em CI para que Low novo apareça e exija decisão explícita.

---

### AUD-SEC-5 — Download de modelos ML (HF + Ollama) sem pin de integridade/revisão

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `CrossEncoderReranker._get_model` (`reranker.py:80,90,119`); `ensure_model`/`_pull` (`manager.py`); `OllamaConfig.embedding_model` (`config.py:31`)

**Failure (input → efeito):** `CrossEncoder(self._model_name, device=...)` sem `revision=` fixo — resolve a branch mutável `main` de `BAAI/bge-reranker-v2-m3` a CADA carregamento. `OllamaConfig.embedding_model = 'bge-m3:latest'` (tag mutável, não digest sha256); `_pull()` faz `POST /api/pull` sem verificar hash. Se a conta/registro upstream for comprometida ou o mantenedor republicar pesos sob a mesma tag, uma instalação incorpora silenciosamente pesos diferentes.

**Repro:** `grep -n "CrossEncoder(" reranker.py` (sem `revision=`); `grep -n "embedding_model" config.py` (default `bge-m3:latest`).

**Evidência observada:** 3 ocorrências de `CrossEncoder(` (L80/90/119), nenhuma passa `revision=`. `inspect.signature` confirma `revision: str | None = None` aceito mas não usado → HF resolve `main`. `manager.py` só compara nome/prefixo, sem verificação de hash. Ressalva: `auto_pull` default `False` (só roda com opt-in do usuário) reduz a superfície Ollama; o `CrossEncoder(...)` do reranker roda sempre. Formato safetensors (não pickle) mitiga RCE por desserialização; risco residual = pesos degradados incorporados silenciosamente.

**Remediação sugerida:** adicionar campo `revision` opcional em `RerankerConfig` e passar a `CrossEncoder(...)`; documentar tag por digest (`bge-m3@sha256:...`) para Ollama e explicitar no README que `auto_pull=True` implica confiar no que a tag resolve.

---

### AUD-SEC-6 — Paths ignorados usam prefix-match de string (casa diretório-irmão)

- **Severidade:** 🟠 IMPORTANTE (subido de COSMÉTICO pelo verificador)
- **Símbolo/arquivo:** `scan_changes()` — `application/ingest_use_case.py:140`

**Failure (input → efeito):** `if any(str(path).startswith(ig) for ig in ignored)` compara strings sem checar separador. Se `ignored` contém `/home/user/corpus/secret`, um arquivo em `/home/user/corpus/secret2/notas.pdf` também é tratado como ignorado — perda silenciosa de documentos do índice, sem erro/log/aviso, por um cenário de configuração ordinário (nomes de irmão com prefixo comum: `secret`/`secret2`, `draft`/`drafts`, `old`/`old_v2`).

**Repro:** corpus com `secret/real_secret.txt` e `secret2/notas.txt` (irmãos), `ignored.paths=[corpus/"secret"]`, chamar `scan_changes(corpus, recursive=True)`.

**Evidência observada:** repro end-to-end contra o código real: `secret2/notas.txt` foi silenciosamente excluído (nem new, nem modified, nem unchanged), sem erro. `startswith` → True (falso positivo); `Path.is_relative_to` → False (correto). `grep -rn "\.startswith(" src/rag_maker/` retorna só essa ocorrência — sem gêmeo em produção.

**Remediação sugerida:** trocar por `any(Path(path).is_relative_to(Path(ig)) for ig in ignored)`, normalizando todo o conjunto `ignored` (que mistura `Path`→`str` com `db_dir_str`) para `Path` antes da comparação.

---

### AUD-TEST-4 — Ciclo de vida do daemon Ollama sem nenhum teste

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `manager.ensure_running` / `spawn_daemon` / `_pull` — `ollama/manager.py:22-45,69-76`

**Failure (input → efeito):** `coverage` aponta linhas 24-32, 37-39, 66, 70-76 como não cobertas — corpo inteiro de `ensure_running` (busy-wait de até 30s), `spawn_daemon` (Popen `ollama serve` + caso `shutil.which` None) e `_pull` (streaming HTTP). Regressões nesses sub-rotinas (timeout mal calculado, Popen com argumento errado, streaming travando) passariam despercebidas.

**Repro:** `pytest --cov=src/rag_maker/adapters/driven/ollama --cov-report=term-missing tests/integration/test_ollama_manager.py -q`.

**Evidência observada:** `manager.py 48 17 65% Missing: 24-32, 37-39, 66, 70-76`; suíte inteira → idêntico (155 passed). As linhas mapeiam para os 3 símbolos citados; só `probe`/`list_models`/`ensure_model` (sem `auto_pull=True`) são testados. Único arquivo de teste que referencia `manager` é `test_ollama_manager.py`.

**Remediação sugerida:** testes com `monkeypatch` em `time.sleep`/`time.monotonic` para `ensure_running` (timeout sem custar 30s), `shutil.which` retornando None (spawn levanta `OllamaUnavailableError`), `subprocess.Popen` mockado, e `respx` para `POST /api/pull` com `stream=True`.

---

### AUD-TEST-5 — Retry-com-backoff do OllamaEmbedder nunca exercitado

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `OllamaEmbedder._embed_with_retry` — `ollama/embedder.py:42-55`

**Failure (input → efeito):** os testes cobrem vetor-zero/vazio/dim-mismatch (re-lançados imediatamente por `except (DimensionMismatchError, EmbeddingError): raise`). O ramo genérico (ex.: `httpx.ConnectError`) que aciona o loop de retry com `time.sleep(2**attempt)` e eventualmente sucede/esgota nunca é testado — caminho de resiliência de rede sem cobertura.

**Repro:** respx com `side_effect = [ConnectError, ConnectError, Response(200,...)]`, depois `emb.embed('hello')`.

**Evidência observada:** 2 falhas + 1 sucesso → `elapsed: 3.02 len: 8` (recupera, gasta ~3s reais de sleep sem mock); esgotamento (3 falhas, `max_retries=3`) → `raised EmbeddingError: refused elapsed: 3.02` (último erro propagado corretamente). `OllamaEmbedder` só referenciado em `test_ollama_embedder.py`, sem respx de exceção de transporte nem monkeypatch de `time.sleep`.

**Remediação sugerida:** 2 testes com respx (N falhas + sucesso; e esgotamento verificando `EmbeddingError`), com `monkeypatch.setattr(embedder_mod.time, 'sleep', lambda *_: None)` para não gastar tempo real.

---

### AUD-TEST-6 — cli/main.py: coverage cego + comandos reais sem teste

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `ingest` / `doctor` / `config_get` / vários `EXIT_*` — `main.py:1-442`; `tests/e2e/test_cli.py:1-106`

**Failure (input → efeito):** `test_cli.py` invoca a CLI via `subprocess.run` sem `COVERAGE_PROCESS_START`/`sitecustomize.py` — coverage.py não instrumenta o subprocess, então `cli/main.py` aparece com 0% mesmo quando exercitado. Funcionalmente: nenhum teste cobre `ingest` (fluxo `--full`/confirm, agregação de `report.errors`), `doctor`, `config get` sem chave, nem exit codes EXIT_CONFIG / EXIT_OLLAMA / EXIT_MODEL / EXIT_USER (ignore rm inexistente, config get de chave inexistente). Só 8 dos ~13 comportamentos observáveis têm teste.

**Repro:** `pytest --cov=.../cli --cov-report=term-missing tests/e2e/ -q`; execução manual dos comandos.

**Evidência observada:** `8 passed in 84.15s` + `cli/main.py 230 230 0%` + `FAIL ... Total coverage: 0.00%`. Nenhum `COVERAGE_PROCESS_START`/`sitecustomize.py`. Execução manual: `config get naochave.inexistente` → exit 1 (EXIT_USER, nunca testado); `ignore rm /nao/existe` → exit 1 (nunca testado); `doctor` roda sem teste. `ingest` não tem NENHUM teste via CLI (só a use case pura em `test_ingest_use_case.py`).

**Remediação sugerida:** migrar parte dos testes e2e para `typer.testing.CliRunner` (in-process, coverage funciona nativamente), reservando subprocess só para o que exige isolamento; adicionar testes de `ingest`/`doctor`/`config get` sem args/exit codes EXIT_CONFIG/EXIT_USER.

---

### AUD-CIDOCS-2 — Exit code 5 ("banco corrompido") é código morto; corrupção cai em exit 6

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `EXIT_DB` (`main.py:41`); `query()`; `get_store_stats()` (`composition/container.py:152-162`)

**Failure (input → efeito):** AGENTS.md §6 e README documentam exit 5 = "Banco corrompido" com instrução para o agente sugerir `rag ingest --full` (exit 2,4,5 = intervenção humana, não retentar). `EXIT_DB = 5` é definido mas nunca passado a `_abort`/`typer.Exit`. Com banco corrompido (meta.json válido + dataset ilegível), `get_store_stats()` engole a exceção e retorna `initialized=False`; `rag query` cai em `if not stats.initialized` → EXIT_CORPUS=6 ("Banco vazio... Execute `rag ingest` primeiro"). Um agente seguindo o contrato reage a corrupção com o remédio errado (ingest incremental) em vez de `--full`; e exit 6 não está em nenhuma tabela de retry/desistir do AGENTS.md.

**Repro:** corromper `db/chunks.lance/data.lance`, depois `rag query "teste" --json; echo $?`.

**Evidência observada:** saída `Banco vazio ou não inicializado... EXIT: 6` — não 5. `grep` confirma EXIT_DB=5 definido mas sem emissor; os outros exit codes (2,3,4,6,70) têm todos emissor real. AGENTS.md:156 e README.md:149 documentam o exit 5 inexistente.

**Remediação sugerida:** (a) implementar detecção real de corrupção em `get_store_stats`/`LanceVectorStore` (distinguir "não existe/vazio" de "ilegível") e emitir EXIT_DB=5 — preferível, pois o agente precisa de sinal diferenciado; ou (b) remover exit 5 dos docs e cobrir exit 6 na tabela de retry/desistir. Teste e2e que trave o contrato. (Decisão de produto — levar ao TODO.md.)

---

### AUD-CIDOCS-3 — CI só `pytest -m unit`; integration/e2e nunca rodam, inclusive no release

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `jobs.smoke` step "Unit tests" (`ci.yml:72`); `jobs.release`

**Failure (input → efeito):** ci.yml roda só `uv run pytest -m unit -q --no-cov`. 21 testes unit vs 22 integration+e2e — metade da suíte nunca roda. O job `release` (tag `v*`, publica wheel/sdist) só depende de `needs: smoke`. Contradiz CONTRACT.md §11.1 (integration+e2e obrigatórios em mudança de adapters ollama/lancedb e "antes de release") e §11.2 (suíte completa + cobertura ≥70% como MUST). (Mesmo gap que AUD-TEST-1, ancorado aqui na violação do contrato formal.)

**Repro:** `grep -n "pytest -m" ci.yml` (só unit); contagem de `def test_` em integration+e2e.

**Evidência observada:** único comando de teste é `pytest -m unit`; job `release` roda só `uv build` + upload. `pytest -m integration -q --no-cov` → `65 passed in 33.42s` (respx mocka Ollama, sem rede); `pytest -m e2e` → `8 passed in 131.05s` (sem falhas). Remediação viável hoje: ambos passam offline. Nenhum ADR/comentário justifica a exclusão — parece lacuna genuína.

**Remediação sugerida:** `uv run pytest -m integration -q` no job smoke (~34s) e `uv run pytest -m e2e -q` como gate obrigatório do `release` antes de publicar. Testes que exijam Ollama real → marcador extra + runner nightly.

---

### AUD-CIDOCS-4 — Gate de cobertura (`fail_under=70`) é config morta

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `[tool.coverage.report] fail_under` (`pyproject.toml:61`); step "Unit tests" (`ci.yml:72`)

**Failure (input → efeito):** pyproject declara `fail_under = 70` (F1.15, ✅ no TODO.md) e CONTRACT.md §11.1/§11.2 tratam `--cov >= 70%` como MUST antes de release. CI invoca `pytest -m unit -q --no-cov` — a flag desliga completamente a medição; mesmo ligada, só mediria os testes unit. O número "70%" nunca é verificado por máquina.

**Repro:** `grep -n 'no-cov' ci.yml scripts/preci.sh`; `grep -n 'fail_under' pyproject.toml`.

**Evidência observada:** `fail_under = 70` na linha 61; único uso de `cov` em ci.yml é `--no-cov`; `preci.sh:25` espelha o mesmo. Contra-prova: rodando os MESMOS testes unit do CI com `--cov` → `TOTAL 45% ... FAIL Required test coverage of 70.0% not reached. Total coverage: 44.99%`. Ou seja, `--no-cov` silencia um gate que hoje NÃO passaria — o "70%" é provavelmente falso, não só não verificado.

**Remediação sugerida:** trocar `--no-cov` por `--cov=src/rag_maker --cov-report=term-missing` na suíte completa (job dedicado que falha abaixo de 70%); ou, se manter `--no-cov` por velocidade do PR gate, mover cobertura para job nightly e ser honesto no CONTRACT.md/README sobre o que é de fato enforced.

---

### AUD-CIDOCS-5 — pyproject.toml não declara `license`/classifier AGPL no metadata do wheel

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `[project]` (`pyproject.toml`); build-system hatchling

**Failure (input → efeito):** o projeto migrou para AGPL-3.0 (commit 2bbd6a2) com badge/README/LICENSE completos, mas `[project]` não tem `license = "AGPL-3.0-or-later"` (PEP 639) nem classifier AGPL. No METADATA do wheel construído, o único indício é `License-File: LICENSE`. Scanners automatizados (pip show, SBOM, FOSSA, scancode, pip-licenses) não detectam que o pacote é AGPL — risco de consumidor embutir a lib em produto proprietário sem perceber a obrigação de copyleft de rede (AGPL §13).

**Repro:** `uv build -q`; inspecionar linhas `License*` do METADATA no `.whl`.

**Evidência observada:** `grep -in "license\|classifier" pyproject.toml` = vazio. `uv build` → `rag_maker-0.1.4-py3-none-any.whl`. METADATA: única linha com "license" é `License-File: LICENSE`; nenhuma linha `License:`; `Classifier:` = lista vazia. Migração AGPL confirmada no histórico + `LICENSE` na raiz. Ressalva: a versão mínima do hatchling para PEP 639 SPDX-string não foi verificada.

**Remediação sugerida:** adicionar `license = "AGPL-3.0-or-later"` em `[project]` e opcionalmente `classifiers = ["License :: OSI Approved :: GNU Affero General Public License v3"]`; rebuild e reverificar METADATA (confirmando a versão do hatchling).

---

### AUD-CIDOCS-8 — `[retrieval].alpha` documentado como knob funcional, mas é dead config

- **Severidade:** 🟠 IMPORTANTE
- **Símbolo/arquivo:** `AppConfig.retrieval.alpha` (`config.py:45`); `QueryUseCase.answer()`; `--alpha` (`main.py`)

**Failure (input → efeito):** `rag_maker.toml.example:23` e README (pt+en) documentam `alpha = 0.5 # peso dense vs lexical no RRF (0.0=só BM25, 1.0=só HNSW)` sem ressalva. `grep -rn 'retrieval.alpha' src/` = zero — nunca lido no pipeline. O parâmetro `alpha` de `answer()` é aceito mas descartado. Usuário que edita `alpha` no TOML ou passa `--alpha 0.8` não vê efeito, sem erro/aviso. (AGENTS.md já documenta corretamente como "reservado para uso futuro" — a inconsistência é entre AGENTS.md/código de um lado e toml.example/README de outro.)

**Repro:** `grep -rn 'retrieval\.alpha' vector_store.py query_use_case.py` (nenhum resultado).

**Evidência observada:** 4 ocorrências de `alpha` em `src/`: `config.py:45` (nunca lido), `query_use_case.py:29` (descartado no corpo), `main.py:230/248` (passthrough). `hybrid_search` e `rrf_fuse` nem aceitam `alpha` na assinatura. `AppConfig.retrieval.alpha` (default 0.5) lido por ZERO código. Toml.example/README divergem do AGENTS.md.

**Remediação sugerida:** (a) implementar RRF ponderado em `hybrid_search`/`rrf_fuse`; ou (b) remover o campo do toml.example e do README; ou (mais barato) anotar "(ainda não implementado, sem efeito)" nos dois locais, alinhando ao AGENTS.md.

---

### AUD-SEC-4 — Nenhuma ferramenta de secret-scanning em pre-commit/CI

- **Severidade:** 🟢 COSMÉTICO
- **Símbolo/arquivo:** `.pre-commit-config.yaml`; `.forgejo/workflows/ci.yml`

**Failure (input → efeito):** não há segredo commitado hoje (grep confirma), mas nenhum hook impede que aconteça (token de API futuro, path/URL interno via fixture). Gap frente ao kit canônico (gitleaks/trufflehog em pre-commit + CI + history scan).

**Repro:** `grep -riE "gitleaks|trufflehog|detect-secrets" .pre-commit-config.yaml ci.yml` (0 matches).

**Evidência observada:** grep = vazio (exit 1). Ambos os arquivos lidos: só ruff/mypy/bandit/import-linter/pytest. Grep na árvore inteira por `.gitleaks.toml`/`.secrets.baseline` = zero. `bandit.yaml` é SAST puro, não substitui secret-scanning.

**Remediação sugerida:** hook `gitleaks protect --staged` (ou detect-secrets) em pre-commit + step em ci.yml (scan de histórico completo uma vez, depois incremental por PR).

---

### AUD-CORRECT-2 — Coluna `content_hash` no schema LanceDB sempre vazia e nunca lida

- **Severidade:** 🟢 COSMÉTICO
- **Símbolo/arquivo:** `LanceVectorStore._to_row` / `_schema` — `vector_store.py:46,176`

**Failure (input → efeito):** o schema declara `content_hash: string` (linha 46) mas `_to_row` sempre grava `""` (linha 176); nenhum código lê essa coluna de volta (`_row_to_chunk` não a usa; `Chunk` no domínio nem tem o campo). Vestígio morto que sugeria — mas não implementa — chunk_id sensível a conteúdo (mesma raiz de AUD-CORRECT-1).

**Repro:** `grep -n 'content_hash' vector_store.py` (só schema + literal vazio).

**Evidência observada:** confirmado por leitura direta: schema linha 46, literal `""` linha 176, `_row_to_chunk` (181-194) sem referência. `content_hash` de `Document` (models.py:11) é campo separado e funcional (hash de arquivo inteiro, usado no manifesto). As outras colunas do schema são todas lidas de volta; `content_hash` é a única órfã.

**Remediação sugerida:** remover a coluna (migração de schema simples, sem dados legados) OU preenchê-la com `sha256(chunk.content)` e usá-la em conjunto com a correção de AUD-CORRECT-1. Decisão de design — resolver junto com AUD-CORRECT-1 via TODO.md, não inline.

---

### AUD-TEST-7 — Parâmetro `alpha` é no-op sem teste que fixe o comportamento

- **Severidade:** 🟢 COSMÉTICO
- **Símbolo/arquivo:** `QueryUseCase.answer(alpha=...)` / `cli query --alpha` — `query_use_case.py:25-30`; `main.py:220-224`

**Failure (input → efeito):** `alpha` é aceito na assinatura (comentário "reservado para uso futuro") mas nunca lido nem repassado a `hybrid_search`. Nenhum teste documenta essa lacuna; se alguém plugar `alpha` parcialmente no futuro, nada acusa a regressão porque não há baseline pinado. (Faceta de teste do mesmo dead config de AUD-CIDOCS-8.)

**Repro:** `answer("...", alpha=0.0)` vs `alpha=1.0` vs `alpha=None`, comparar rankings.

**Evidência observada:** os três produzem ranking idêntico (`IDENTICAL (0.0 vs 1.0): True`) — no-op comportamental real. `rrf_fuse` nem tem `alpha` na assinatura; `AppConfig.retrieval.alpha` lido por zero código. Nenhum teste existente passa `alpha`.

**Remediação sugerida:** enquanto no-op, adicionar teste leve afirmando que `answer(alpha=0.1)` e `answer(alpha=0.9)` retornam resultados idênticos (pinando o no-op como intencional). Quando `alpha` for implementado, teste de integração provando que valores diferentes mudam a ordenação.

---

### AUD-CIDOCS-6 — Nenhum dos 44 .py em src/ carrega header SPDX-License-Identifier

- **Severidade:** 🟢 COSMÉTICO
- **Símbolo/arquivo:** `src/rag_maker/**/*.py`

**Failure (input → efeito):** AGPL-3.0 não exige headers por arquivo, mas é prática padrão para que um arquivo extraído isoladamente (comum em workflows assistidos por IA que leem um arquivo por vez) carregue sua identificação de licença. Zero de 44 arquivos têm SPDX header.

**Repro:** `grep -rl 'SPDX-License-Identifier' src | wc -l` (0); `find src -name '*.py' | wc -l` (44).

**Evidência observada:** 44 arquivos, 0 com SPDX. `head -5` de `domain/models.py` começa direto com `from __future__ import annotations`, sem SPDX. `grep -ril license src` = vazio.

**Remediação sugerida:** `# SPDX-License-Identifier: AGPL-3.0-or-later` como primeira linha de todos os módulos, via `reuse addheader` (FSFE REUSE tooling) + pre-commit hook, para não depender de disciplina manual.

---

### AUD-CIDOCS-7 — AGENTS.md §4 omite flags `--full`/`--yes` que o próprio doc referencia

- **Severidade:** 🟢 COSMÉTICO
- **Símbolo/arquivo:** `AGENTS.md §4`; `ingest()` em `main.py`

**Failure (input → efeito):** AGENTS.md:110 documenta a assinatura como `rag ingest [--corpus DIR] [--json]`, sem `--full`/`--yes`. A CLI real tem 4 parâmetros (corpus, full, yes, as_json). O mesmo doc, em §8, instrui "Nunca chamar `rag ingest --full` sem alertar" — citando flag não declarada no contrato de chamada. Consequência funcional real: `--full` sem `--yes` dispara `typer.confirm(...)` bloqueante; um agente automatizado sem TTY que seguisse §4 travaria.

**Repro:** `grep -n 'rag ingest' AGENTS.md` (linha 110 só `[--corpus DIR] [--json]`).

**Evidência observada:** §4 linha 110 é a única assinatura formal; `--full`/`--yes` só em prosa (§7/§8). `main.py:153-158` confirma os 4 parâmetros; `172-175` confirma o `typer.confirm`/`typer.Abort()` bloqueante. README (linhas 120-123/356-357) documenta a sintaxe completa corretamente — inconsistência entre os dois docs.

**Remediação sugerida:** atualizar §4 para `rag ingest [--corpus DIR] [--full] [--yes|-y] [--json]`, com uma linha explicando full=reconstrução total, yes=pula confirmação interativa, e o risco de travamento sem TTY.

---

## 5. Achados PLAUSÍVEIS

> Achados com cadeia de exploração confirmada por execução (dependência vulnerável + caminho de código alcançável e sem guard), mas cujo **disparo final do failure não foi executado** — o repro que dispararia o efeito não foi rodado por risco/custo na sandbox. Não contam como refutados; exigem ação, com a ressalva de que o impacto máximo não foi demonstrado ao vivo.

### AUD-SEC-2 — pypdf 6.10.2 desatualizado com múltiplas CVEs de DoS reachable

- **Severidade:** 🟠 IMPORTANTE (rebaixado de CRÍTICO pelo verificador — impacto máximo é DoS local, não RCE/corrupção)
- **Símbolo/arquivo:** `PdfLoader.load()` — `src/rag_maker/adapters/driven/loaders/pdf.py`

**Failure (input → efeito):** `pyproject.toml:17` pina `pypdf[crypto]>=4` sem teto; uv.lock resolveu 6.10.2. pip-audit confirma 9 CVEs corrigidas só em 6.12.0–6.13.3 (CVE-2026-48156/48155/48735/49461/49460/54531/54530/54651, GHSA-jm82-fx9c-mx94: infinite loop / memory exhaustion). `PdfLoader.load()` chama `PdfReader()` + `extract_text()` sobre QUALQUER PDF apontado pelo usuário — cenário central do produto (ingerir PDFs baixados da internet) é o vetor de entrada mais hostil. O laço de extração fica fora do try/except (ver AUD-INPUT-1) e não há timeout no caminho de ingest.

**Repro:** `pip-audit --local -f json` filtrando `pypdf` (9 CVEs, fix_versions ≥ 6.12.0).

**Evidência observada:** `pypdf.__version__` → 6.10.2; `pyproject.toml:17` sem teto; pip-audit lista as 9 CVEs. Código lido: `PdfReader(str(path))` no try estreito, `extract_text()` fora; `_ingest_file`/`ingest_incremental` sem timeout/watchdog. **NÃO** foi construído um PDF malicioso para disparar o hang/OOM real (CVEs de xref-stream/FlateDecode+PNG-predictor não triviais de craftar com segurança; risco de OOM na sandbox). Cadeia de exploração confirmada por execução; o disparo do DoS em si não foi executado — daí o veredito PLAUSÍVEL.

**Remediação sugerida:** bump imediato para `pypdf[crypto]>=6.13.3` em `pyproject.toml:17`; adicionar teto de política (Renovate/Dependabot para patch); envolver `PdfLoader.load()` com try/except amplo + timeout/watchdog (`signal.alarm` ou subprocess isolado) como defesa em profundidade, dado o padrão histórico de CVEs de infinite-loop em parsers de PDF de terceiros.

---

## 6. Achados REFUTADOS

Nenhum achado levantado foi refutado nesta rodada. Todos os 28 achados passaram pela verificação adversarial (leitura do código + execução de repro) e foram confirmados (27) ou classificados como plausíveis com cadeia parcial (1, AUD-SEC-2).

| ID | Título | Motivo de refutação |
|---|---|---|
| — | (nenhum) | — |

> Observação de confiança para o auditor externo: a ausência de refutados **não** indica verificação leniente. Vários achados tiveram a severidade ajustada pelo verificador contra o finder (AUD-SEC-2 rebaixado; AUD-INPUT-4, AUD-SEC-6, AUD-TEST-3b reclassificados), e em ao menos dois casos (AUD-INPUT-2 e AUD-TEST-3b) uma primeira tentativa de repro FALHOU por limites incidentais de bibliotecas, o que quase levou à refutação — a confirmação só veio após demonstrar que esses "guards" eram acidentais e contornáveis. A verificação foi adversarial de fato.

---

## 7. Veredito por lente

**INPUT.** Os 4 loaders têm bom esqueleto (try/except no ponto de abertura, checagem de vazio, fallback de encoding), mas a superfície tem furos reais: o guard do PdfLoader não cobre o laço de extração (AUD-INPUT-1); **nenhum** loader tem guard de tamanho/descompressão, um vetor de DoS clássico de zip-bomb (AUD-INPUT-2, 🔴); o fallback latin-1 do TextLoader nunca falha, indexando binário como mojibake (AUD-INPUT-3); e `--top-k` não valida range (AUD-INPUT-4). O registry `loader_for()` em si é robusto.

**SEC.** A superfície de código própria está limpa (sem shell=True/eval/pickle/yaml.unsafe/segredos hardcoded; escrita de config atômica 0600; SQL predicate do LanceDB escapado). O risco real está na cadeia de suprimento e nos gates: pip-audit nunca roda (AUD-SEC-1), deixando pypdf com CVEs (AUD-SEC-2); bandit suprime a classe Low sem justificativa (AUD-SEC-3); modelos ML baixados sem pin de integridade (AUD-SEC-5); prefix-match de paths perde documentos (AUD-SEC-6); e falta secret-scanning preventivo (AUD-SEC-4). STRIDE (ferramenta local single-user offline): o vetor principal é Tampering (arquivo malicioso → parser → DoS local), controlável com SCA gate + pinning; Information disclosure/Elevation/Spoofing têm superfície mínima.

**CORRECT.** RRF e reranker estão corretos e bem cobertos. O bug real está na fronteira ingest + chunker + vector_store: chunk_id determinístico sem componente de conteúdo + upsert-only sem delete-before-reinsert produz **corrupção silenciosa e permanente** do índice quando um documento editado encolhe (AUD-CORRECT-1, 🔴, confirmado com repro executável e demonstração de que os órfãos são retornados por hybrid_search). `content_hash` órfão no schema (AUD-CORRECT-2) é sintoma da mesma raiz.

**TEST.** Suíte grande (155 testes) com núcleo de boa qualidade (Hypothesis no chunker, fakes precisos no reranker/ingest). Mas a rede de segurança está furada onde mais importa: CI roda só metade (AUD-TEST-1, 🔴), escondendo dois bugs reais e demonstráveis — FTS morta em produção (AUD-TEST-2, 🔴) e decompression bomb em DOCX/EPUB (AUD-TEST-3/3b, 🔴). Cobertura declarada (70%) não é aplicada em CI e o run real fica em 67% (44,99% na fatia unit). Lacunas de cobertura em código de infraestrutura (ollama manager AUD-TEST-4, retry embedder AUD-TEST-5, CLI AUD-TEST-6) e no-op não pinado (AUD-TEST-7).

**CI/DOCS.** Os gates que rodam (ruff, mypy --strict, import-linter, bandit) estão verdes de verdade — não é teatro. Mas o pipeline real é mais fraco do que o CONTRACT.md promete: pip-audit é MUST e nunca roda, com 27 CVEs sem alerta (AUD-CIDOCS-1, 🔴); integration/e2e nunca rodam, inclusive no release (AUD-CIDOCS-3); o gate de cobertura é config morta (AUD-CIDOCS-4); exit 5 documentado é código morto (AUD-CIDOCS-2); `alpha` é dead config divergente entre docs (AUD-CIDOCS-8); metadata de licença AGPL ausente no wheel (AUD-CIDOCS-5); sem SPDX headers (AUD-CIDOCS-6); AGENTS.md §4 omite flags (AUD-CIDOCS-7).

**Parecer de prontidão para auditor externo:** NÃO PRONTO. Os 7 achados 🔴 (3 de robustez de entrada/DoS, 1 de corrupção de índice, 1 de feature central morta, 2 de gate de pipeline) precisam de remediação e re-teste antes de expor o livro a um auditor externo. Vários se resolvem juntos (delete-then-insert cobre AUD-CORRECT-1 e informa AUD-CORRECT-2; guard de zip cobre AUD-INPUT-2 + AUD-TEST-3/3b; ativar pip-audit + integration/e2e + cobertura no CI cobre AUD-CIDOCS-1/3/4 e AUD-SEC-1). Recomenda-se levar as decisões de design (delete-then-insert vs chunk_id sensível a conteúdo; exit 5 real vs remover doc; implementar alpha vs remover) ao líder via TODO.md antes de qualquer código, conforme a regra do projeto.

---

## 8. Tabela de rastreamento de remediação

| ID | Severidade | Status remediação |
|---|---|---|
| AUD-INPUT-2 | 🔴 CRÍTICO | ⏳ Pendente |
| AUD-CORRECT-1 | 🔴 CRÍTICO | ⏳ Pendente |
| AUD-TEST-1 | 🔴 CRÍTICO | ⏳ Pendente |
| AUD-TEST-2 | 🔴 CRÍTICO | ⏳ Pendente |
| AUD-TEST-3 | 🔴 CRÍTICO | ⏳ Pendente |
| AUD-TEST-3b | 🔴 CRÍTICO | ⏳ Pendente |
| AUD-CIDOCS-1 | 🔴 CRÍTICO | ⏳ Pendente |
| AUD-INPUT-1 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-INPUT-3 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-INPUT-4 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-SEC-1 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-SEC-2 | 🟠 IMPORTANTE (plausível) | ⏳ Pendente |
| AUD-SEC-3 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-SEC-5 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-SEC-6 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-TEST-4 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-TEST-5 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-TEST-6 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-CIDOCS-2 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-CIDOCS-3 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-CIDOCS-4 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-CIDOCS-5 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-CIDOCS-8 | 🟠 IMPORTANTE | ⏳ Pendente |
| AUD-SEC-4 | 🟢 COSMÉTICO | ⏳ Pendente |
| AUD-CORRECT-2 | 🟢 COSMÉTICO | ⏳ Pendente |
| AUD-TEST-7 | 🟢 COSMÉTICO | ⏳ Pendente |
| AUD-CIDOCS-6 | 🟢 COSMÉTICO | ⏳ Pendente |
| AUD-CIDOCS-7 | 🟢 COSMÉTICO | ⏳ Pendente |

**Legenda de Estado Auditado (a preencher no re-teste):** `—` não remediado / `✓` remediado e re-testado / `⚠` remediado parcialmente ou pendente de re-teste. Todos iniciam em `⏳ Pendente` (equivalente a `—`).

---

*Fim do dossiê. Documento honesto e rastreável, calibrado para porte solo/early-stage, pronto para receber os planos de remediação por achado antes de ser entregue a um auditor externo. Nenhuma linha de código foi alterada na produção deste livro; toda ação de remediação deve entrar no `TODO.md` com autorização do líder antes da execução por agente especialista.*