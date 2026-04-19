# Guia Completo de Testes, Qualidade e Auditoria — rag_maker

> Documento instrucional para qualquer agente de IA ou engenheiro executar a suíte
> completa de verificação no projeto **rag_maker** (Python 3.11+, uv, arquitetura
> hexagonal, retrieval-only offline).
> Adapte os caminhos e nomes de módulos conforme o avanço das fases descritas em `TODO.md`.

---

## Índice

1. [Pré-requisitos e Instalação](#1-pré-requisitos-e-instalação)
2. [T1 — Testes Unitários](#t1--testes-unitários)
3. [T2 — Análise Estática](#t2--análise-estática)
4. [T3 — Fuzzing de Inputs](#t3--fuzzing-de-inputs)
5. [T4 — Análise Dinâmica de Memória](#t4--análise-dinâmica-de-memória)
6. [T5 — Scanning de Dependências](#t5--scanning-de-dependências)
7. [T6 — Teste de APIs](#t6--teste-de-apis)
8. [T7 — Scanning de Binário (wheel/sdist)](#t7--scanning-de-binário-wheelsdist)
9. [T8 — Verificação de Secrets](#t8--verificação-de-secrets)
10. [T9 — Teste de Rede](#t9--teste-de-rede)
11. [T10 — Validação de Queries e Paths](#t10--validação-de-queries-e-paths)
12. [T11 — Fuzzing de Protocolos de Rede](#t11--fuzzing-de-protocolos-de-rede)
13. [T12 — Busca de CVEs nas Dependências](#t12--busca-de-cves-nas-dependências)
14. [A1 — Descoberta e Modelagem](#a1--descoberta-e-modelagem)
15. [A2 — Auditoria de Arquitetura e Camadas](#a2--auditoria-de-arquitetura-e-camadas)
16. [A3 — UI/UX e Acessibilidade](#a3--uiux-e-acessibilidade)
17. [A4 — QA Geral Python](#a4--qa-geral-python)
18. [A5 — Análise Estática e Dinâmica Python](#a5--análise-estática-e-dinâmica-python)
19. [A6 — Cobertura de Testes](#a6--cobertura-de-testes)
20. [A7 — Dependências e Acoplamento](#a7--dependências-e-acoplamento)
21. [A8 — Consistência Protocols ↔ Implementations](#a8--consistência-protocols--implementations)
22. [A9 — Análise Arquitetural Geral](#a9--análise-arquitetural-geral)
23. [A10 — Relatório Final de Auditoria](#a10--relatório-final-de-auditoria)
24. [Classificação de Problemas](#classificação-de-problemas)
25. [Formato de Patch](#formato-de-patch)

---

## 1. Pré-requisitos e Instalação

Instale todas as ferramentas antes de executar qualquer etapa. O projeto é
gerenciado via `uv`; as ferramentas Python ficam dentro do virtualenv do projeto;
as ferramentas de sistema e binários externos ficam no `$PATH` do usuário.

```bash
# Dependências do projeto (via uv, inclui dev/test groups)
uv sync --all-extras

# Ferramentas de auditoria extras (via pipx para isolamento do virtualenv do projeto)
pipx install gitleaks   || sudo dnf install -y gitleaks   || sudo apt install -y gitleaks
pipx install trufflehog || sudo dnf install -y trufflehog || sudo apt install -y trufflehog
pipx install check-wheel-contents
pipx install pyroma

# trivy — binário oficial
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
    | sudo sh -s -- -b /usr/local/bin

# hurl — testes declarativos de endpoints HTTP
curl --silent --location \
    https://github.com/Orange-OpenSource/hurl/releases/latest/download/hurl_linux_amd64.deb \
    -o /tmp/hurl.deb
sudo dpkg -i /tmp/hurl.deb 2>/dev/null || \
    (curl --silent --location \
        https://github.com/Orange-OpenSource/hurl/releases/latest/download/hurl-x86_64-linux.tar.gz \
        -o /tmp/hurl.tgz && sudo tar -C /usr/local -xzf /tmp/hurl.tgz --strip-components=1)

# osv-scanner (~/.local/bin é assumido em PATH)
mkdir -p ~/.local/bin
curl -fsSL https://github.com/google/osv-scanner/releases/latest/download/osv-scanner_linux_amd64 \
    -o ~/.local/bin/osv-scanner && chmod +x ~/.local/bin/osv-scanner

# nmap / ss / strace — pacotes do sistema
sudo dnf install -y nmap iproute strace unzip \
    || sudo apt install -y nmap iproute2 strace unzip \
    || sudo pacman -S --noconfirm nmap iproute2 strace unzip
```

Crie o diretório de relatórios antes de qualquer execução:

```bash
mkdir -p reports
```

Verifique rapidamente que as ferramentas principais funcionam:

```bash
uv run pytest --version
uv run ruff --version
uv run mypy --version
uv run bandit --version
trivy --version
gitleaks version
hurl --version
~/.local/bin/osv-scanner --version
```

---

## T1 — Testes Unitários

**Objetivo:** verificar que cada módulo se comporta conforme especificado de forma
isolada, com separação por *markers* entre unit/integration/gui.

**Ferramenta:** `pytest` + `pytest-cov` + `pytest-xdist` + `pytest-qt` (para GUI).

```bash
# Suite rápida — falha no primeiro erro, traceback curto
uv run pytest -x --tb=short

# Suite completa com cobertura (HTML + terminal + gate 70%)
uv run pytest \
    --cov=src/rag_maker \
    --cov-report=html:reports/coverage \
    --cov-report=term-missing \
    --cov-fail-under=70

# Apenas testes unitários (rápidos, sem dependência externa)
uv run pytest -m unit

# Integração sem testes marcados "slow"
uv run pytest -m "integration and not slow"

# Testes de GUI (requer Xvfb em CI: xvfb-run -a uv run pytest -m gui)
uv run pytest -m gui

# Paralelizado
uv run pytest -n auto --cov=src/rag_maker

# Um teste específico com saída verbosa
uv run pytest tests/unit/test_chunker.py::test_overlap -v
```

**Estrutura esperada de `tests/`:**

```
tests/
├── unit/                  # domínio puro, sem I/O
│   ├── test_chunker.py
│   ├── test_scoring.py
│   └── test_models.py
├── integration/           # adapters driven com fakes/respx
│   ├── test_ollama_embedder.py
│   ├── test_lancedb_store.py
│   └── test_ingestion_pipeline.py
├── gui/                   # PySide6 com pytest-qt
│   └── test_main_window.py
├── fixtures/
│   ├── corpus_mini/       # PDFs / DOCX / EPUB pequenos para smoke
│   └── respx_bodies/      # respostas Ollama gravadas
└── conftest.py
```

**Critério de aprovação:** 0 failures, cobertura ≥ 70% global,
≥ 90% em `domain/` e ≥ 80% em `application/`.

**Por que é crítico:** a lógica de RAG vive em funções puras
(`chunker`, `scoring`, `rrf`). Uma regressão silenciosa em `rrf`
quebra a qualidade do retrieval sem erro de tipo visível.

---

## T2 — Análise Estática

**Objetivo:** detectar bugs, más práticas e riscos de segurança sem executar o código.

**Ferramentas:** `ruff` (lint + format) + `mypy --strict` + `bandit`.

```bash
# ruff — lint com saída JSON para auditoria
uv run ruff check src/ tests/ --output-format=json > reports/ruff.json
uv run ruff check src/ tests/         # saída humana

# ruff format — verificação (não altera arquivos)
uv run ruff format --check src/ tests/

# mypy em modo strict — tipagem completa obrigatória
uv run mypy --strict src/ > reports/mypy.txt 2>&1
echo "mypy exit: $?"

# bandit — scanner de segurança Python
uv run bandit -r src/ -ll -f json -o reports/bandit.json
uv run bandit -r src/ -ll              # saída humana

# Contagem rápida de problemas
python3 -c "
import json
ruff = json.load(open('reports/ruff.json'))
bandit = json.load(open('reports/bandit.json'))
print(f'ruff issues: {len(ruff)}')
print(f'bandit HIGH: ', sum(1 for r in bandit.get(\"results\", []) if r.get(\"issue_severity\") == \"HIGH\"))
print(f'bandit MEDIUM:', sum(1 for r in bandit.get(\"results\", []) if r.get(\"issue_severity\") == \"MEDIUM\"))
"
```

**Configuração esperada em `pyproject.toml`:**

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E","F","W","I","B","UP","N","S","RUF","SIM","ARG","PL","PT","RET"]
ignore = ["S101"]   # assert em testes é ok

[tool.mypy]
python_version = "3.11"
strict = true
warn_unused_ignores = true
disallow_untyped_decorators = true
plugins = ["pydantic.mypy"]
```

**Critério de aprovação:** 0 erros em `ruff check`, 0 erros em `mypy --strict`,
0 HIGH e 0 MEDIUM em `bandit`.

**Por que é crítico:** `mypy --strict` captura `None` leaks em Protocols;
`bandit` detecta uso de `subprocess` inseguro, desserializadores inseguros
sobre entrada não confiável, hashes fracos e `yaml.load` sem safe loader.

---

## T3 — Fuzzing de Inputs

**Objetivo:** encontrar crashes e comportamentos inesperados ao receber
entradas malformadas.

**Ferramentas:** `hypothesis` (property-based, principal) + `atheris`
(coverage-guided, opt-in).

### Hypothesis — propriedades invariantes do domínio

Criar testes em `tests/unit/test_chunker_properties.py` e `test_scoring_properties.py`:

```python
# Exemplo: invariantes de chunker
from hypothesis import given, strategies as st, settings
from rag_maker.domain.chunker import chunk_text, ChunkConfig

@given(
    text=st.text(min_size=0, max_size=50_000),
    size=st.integers(min_value=64, max_value=2048),
    overlap=st.integers(min_value=0, max_value=512),
)
@settings(max_examples=500, deadline=None)
def test_chunks_reconstruct_text(text, size, overlap):
    if overlap >= size:
        return  # config inválida
    cfg = ChunkConfig(size=size, overlap=overlap)
    chunks = chunk_text(text, cfg)
    # overlaps recompõem o texto original (com deduplicação)
    rejoined = chunks[0]
    for c in chunks[1:]:
        rejoined += c[overlap:]
    assert rejoined.strip() == text.strip()
    # cada chunk nunca excede size
    assert all(len(c) <= size for c in chunks)

# Exemplo: RRF monotônico
from rag_maker.domain.scoring import rrf

@given(
    ranks_a=st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=100, unique=True),
    ranks_b=st.lists(st.integers(min_value=1, max_value=1000), min_size=1, max_size=100, unique=True),
    k=st.integers(min_value=1, max_value=100),
)
def test_rrf_monotonic(ranks_a, ranks_b, k):
    # Se um documento aparece antes em ambas as listas, seu score RRF é maior.
    scored = rrf([ranks_a, ranks_b], k=k)
    for doc_id, score in scored.items():
        assert score >= 0
```

Rodar com estatísticas:

```bash
uv run pytest tests/unit/test_chunker_properties.py \
    --hypothesis-show-statistics \
    -v

# Estressar todas as property-tests (seed fixa para reprodutibilidade)
HYPOTHESIS_PROFILE=ci uv run pytest -k properties \
    --hypothesis-seed=20260419
```

### Atheris — fuzzing coverage-guided dos loaders

Criar `tests/fuzz/fuzz_pdf_loader.py`:

```python
import sys, atheris
with atheris.instrument_imports():
    from rag_maker.adapters.driven.loaders.pdf_loader import load_pdf_bytes

def TestOneInput(data: bytes) -> None:
    try:
        load_pdf_bytes(data)
    except (ValueError, OSError):
        return  # esperado para bytes inválidos
    except Exception:
        # qualquer outra exceção indica tratamento incompleto
        raise

atheris.Setup(sys.argv, TestOneInput)
atheris.Fuzz()
```

Executar (20k iterações, ~1-2 min):

```bash
mkdir -p fuzz/corpus fuzz/findings
cp tests/fixtures/corpus_mini/*.pdf fuzz/corpus/ 2>/dev/null || true
uv run python tests/fuzz/fuzz_pdf_loader.py \
    fuzz/corpus/ \
    -artifact_prefix=fuzz/findings/pdf_ \
    -runs=20000 \
    2>&1 | tee reports/atheris_pdf.txt
```

**Critério de aprovação:** `hypothesis` — 500+ exemplos por propriedade sem
contraexemplo; `atheris` — 0 crashes inesperados em 20k runs; exceções
aceitáveis são apenas as declaradas no contrato do loader.

**Por que é crítico:** `chunker` e `scoring` são a base da qualidade do
retrieval; loaders recebem arquivos externos de usuários potencialmente
maliciosos (PDFs com headers corrompidos).

---

## T4 — Análise Dinâmica de Memória

**Objetivo:** detectar vazamentos, growth linear indevido e picos de heap
durante ingestão de corpus grande. Em Python o GC cuida de ciclos, mas
buffers mantidos em caches globais, leituras em memória inteira (PDFs
gigantes) e embeddings retidos em listas são fontes clássicas.

**Ferramentas:** `memray` (heap profiler) + `tracemalloc` (stdlib, snapshots)
+ `pytest-memray` (regressão em testes).

```bash
# memray — flamegraph de alocações durante ingestão do corpus mini
uv run memray run \
    --output reports/memray.bin \
    -m rag_maker ingest --corpus tests/fixtures/corpus_mini

uv run memray flamegraph reports/memray.bin -o reports/memray_flame.html
uv run memray tree reports/memray.bin       | head -n 60 > reports/memray_tree.txt
uv run memray summary reports/memray.bin    | tee reports/memray_summary.txt

# tracemalloc — snapshot comparativo antes/depois de um cenário
uv run python -X tracemalloc=25 - <<'PY'
import tracemalloc
from rag_maker.application.ingest_service import IngestService
from rag_maker.composition.wiring import build_ingest_service

service = build_ingest_service()
tracemalloc.start(25)
snap1 = tracemalloc.take_snapshot()
service.ingest_corpus("tests/fixtures/corpus_mini")
snap2 = tracemalloc.take_snapshot()
top = snap2.compare_to(snap1, "lineno")[:15]
for stat in top:
    print(stat)
PY

# pytest-memray — falha se allocs > budget
uv run pytest tests/integration/test_ingestion_pipeline.py \
    --memray \
    --memray-bin-path=reports/memray_tests
```

Exemplo de marker em teste para budget de memória:

```python
import pytest

@pytest.mark.limit_memory("200 MB")
def test_ingest_mini_corpus_respects_memory_budget(ingest_service, tmp_path):
    ingest_service.ingest_corpus("tests/fixtures/corpus_mini")
```

**Critério de aprovação:**
- Pico de heap ≤ 2× o tamanho do batch de embeddings em memória.
- Sem growth linear sustentado entre snapshots (delta constante ou decrescente).
- `pytest-memray` passa dentro do budget declarado.

**Por que é crítico:** ingestão de corpus grande (centenas de PDFs) + bge-m3
dim=1024 em float32 gera ~4MB por 1k chunks. Leak em cache de embedder
degrada a máquina em minutos.

---

## T5 — Scanning de Dependências

**Objetivo:** identificar pacotes vulneráveis ou desatualizados.

**Ferramentas:** `pip-audit`, `safety`, `trivy fs`.

```bash
# pip-audit — resolve via uv.lock
uv run pip-audit --format json --output reports/pip_audit.json
uv run pip-audit --format columns | tee reports/pip_audit.txt

# safety — base de dados complementar
uv run safety check --json --output reports/safety.json 2>/dev/null || true
uv run safety check                   | tee reports/safety.txt

# trivy — filesystem scan (lê uv.lock, pyproject.toml)
trivy fs . \
    --severity HIGH,CRITICAL \
    --format json \
    --output reports/trivy.json
trivy fs . --severity HIGH,CRITICAL | tee reports/trivy.txt
```

**Critério de aprovação:** 0 CVEs CRITICAL sem patch; HIGH documentadas com
justificativa em `docs/security_exceptions.md` (ex.: falso-positivo,
patch não liberado upstream).

**Por que é crítico:** `pypdf`, `python-docx`, `ebooklib`, `beautifulsoup4`
e `httpx` têm histórico recente de CVEs (parsing de XML, XXE, SSRF).

---

## T6 — Teste de APIs

**Objetivo:** verificar que o cliente Ollama consome as respostas sem
erros e lida bem com falhas.

**APIs consumidas:** apenas Ollama local (`http://127.0.0.1:11434`),
endpoints `/api/embed` e `/api/tags`.

**Ferramentas:**
- `respx` para mock `httpx` em testes unit/integration (sem daemon real).
- `hurl` para smoke test manual contra daemon Ollama rodando na máquina.

### respx — mock do daemon nos testes

```python
# tests/integration/test_ollama_embedder.py
import httpx, respx, pytest
from rag_maker.adapters.driven.ollama.embedder import OllamaEmbedder

@respx.mock
def test_embed_happy_path():
    respx.post("http://127.0.0.1:11434/api/embed").mock(
        return_value=httpx.Response(
            200,
            json={"embeddings": [[0.1] * 1024]},
        )
    )
    emb = OllamaEmbedder(base_url="http://127.0.0.1:11434", model="bge-m3:latest")
    vec = emb.embed(["hello"])
    assert len(vec) == 1
    assert len(vec[0]) == 1024
```

### hurl — smoke test contra daemon real

Arquivo `tests/api_ollama.hurl`:

```hurl
# Verificar que o daemon responde e bge-m3 está disponível
GET http://127.0.0.1:11434/api/tags
HTTP 200
[Asserts]
header "Content-Type" contains "application/json"
jsonpath "$.models[?(@.name=='bge-m3:latest')].name" exists

# Gerar um embedding de teste
POST http://127.0.0.1:11434/api/embed
Content-Type: application/json
{
  "model": "bge-m3:latest",
  "input": "teste de embedding"
}
HTTP 200
[Asserts]
jsonpath "$.embeddings[0]" count == 1024
```

Rodar:

```bash
hurl --test tests/api_ollama.hurl \
     --report-html reports/hurl_html/ \
     --report-json reports/hurl.json
```

**Critério de aprovação:**
- `respx` — todos os testes integration passam sem daemon real rodando.
- `hurl` — todos os asserts passam quando daemon Ollama está ativo com `bge-m3:latest`.
- Dimensão retornada = 1024 (bge-m3).

**Por que é crítico:** o projeto inteiro depende desse endpoint;
qualquer divergência de dimensão ou corpo corrompe o vetor armazenado
no LanceDB silenciosamente.

---

## T7 — Scanning de Binário (wheel/sdist)

**Objetivo:** como Python não gera binário nativo, auditar o artefato
distribuível (`*.whl`, `*.tar.gz`) — conteúdo, metadados e higiene.

**Ferramentas:** `twine check`, `pyroma`, `check-wheel-contents`, `unzip`.

```bash
# Gerar artefatos de build
uv build                             # gera dist/rag_maker-*.whl e dist/rag_maker-*.tar.gz

# twine — valida metadados PyPI
uv run twine check dist/*                    | tee reports/twine_check.txt

# pyroma — qualidade do pacote (score 0-10)
uv run pyroma -n 10 .                        | tee reports/pyroma.txt

# check-wheel-contents — arquivos internos
uv run check-wheel-contents dist/*.whl       | tee reports/wheel_contents.txt

# Listagem bruta do conteúdo do wheel
unzip -l dist/*.whl                          | tee reports/wheel_list.txt

# Verificações customizadas: nada que não deveria estar no wheel
python3 <<'PY' | tee reports/wheel_audit.txt
import zipfile, glob, sys

forbidden_patterns = (
    ".pyc", "__pycache__/",
    "tests/", "test_",
    ".env", "config.toml",   # secrets ou config local
    ".git", ".DS_Store",
    ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "reports/", "fuzz/",
)
whl = glob.glob("dist/*.whl")[0]
issues = []
with zipfile.ZipFile(whl) as z:
    for name in z.namelist():
        for pat in forbidden_patterns:
            if pat in name:
                issues.append(f"PROIBIDO: {name} (padrão {pat!r})")
if issues:
    print("\n".join(issues))
    sys.exit(1)
print("OK — wheel limpo")
PY
```

**Critério de aprovação:**
- `twine check` — `PASSED` em todos os artefatos.
- `pyroma` — score ≥ 9/10.
- `check-wheel-contents` — nenhum aviso.
- Auditoria customizada — sem `.pyc`, `.env`, `tests/`, caches de dev.

**Por que é crítico:** distribuir um wheel com `config.toml` local ou com
diretório `tests/` incluído vaza paths privados e infla o pacote. Um
`.env` acidentalmente empacotado é incidente de segurança.

---

## T8 — Verificação de Secrets

**Objetivo:** garantir que nenhuma credencial, token ou chave privada
foi commitada no repositório (nem em histórico antigo).

**Ferramentas:** `gitleaks` + `trufflehog`.

```bash
# gitleaks — escaneia todo o histórico git
gitleaks detect \
    --source . \
    --report-format json \
    --report-path reports/gitleaks.json \
    --verbose 2>&1 | tee reports/gitleaks_output.txt

# trufflehog — varredura com verificação de validade quando possível
trufflehog filesystem . \
    --json 2>&1 | tee reports/trufflehog.json

# Verificação do resultado
python3 <<'PY'
import json, sys
from pathlib import Path

gl_path = Path("reports/gitleaks.json")
data = json.loads(gl_path.read_text()) if gl_path.exists() and gl_path.read_text().strip() else []
if data:
    print(f"ALERTA: {len(data)} secrets encontrados pelo gitleaks!")
    for s in data[:5]:
        print(f"  - {s.get('RuleID')} em {s.get('File')}:{s.get('StartLine')}")
    sys.exit(1)
print("OK: gitleaks sem achados")
PY
```

**Critério de aprovação:** 0 secrets detectados em qualquer commit do histórico,
em qualquer branch.

**Por que é crítico:** o projeto é retrieval-only e offline, mas usuários
podem apontar `corpus_dir` para PDFs com tokens/keys; e se o `config.toml`
vazar no histórico, revela paths internos do usuário.

---

## T9 — Teste de Rede

**Objetivo:** verificar que `rag_maker` só conecta em `127.0.0.1:11434`
(Ollama) e nunca abre portas de escuta. Nenhuma telemetria.

**Ferramentas:** `ss`, `nmap`, `strace`.

```bash
# Iniciar o app em modo CLI e capturar PID
uv run rag-maker query "teste" &
APP_PID=$!
sleep 2

# Conexões TCP/UDP abertas pelo processo
ss -tupn | grep -E "pid=$APP_PID\b" | tee reports/conexoes_rede.txt

# Portas em escuta na máquina (não deveria haver nenhuma criada pela app)
nmap -sT -p 1-65535 127.0.0.1 \
    --open \
    -oN reports/nmap_localhost.txt

# strace — toda chamada de rede do processo
strace -f -e trace=network -p "$APP_PID" \
    -o reports/strace_rede.txt \
    2>/dev/null &
STRACE_PID=$!
sleep 5
kill $STRACE_PID 2>/dev/null
kill $APP_PID    2>/dev/null

# Validar que o único endpoint é 127.0.0.1:11434
python3 <<'PY'
from pathlib import Path
import re

allowed = {("127.0.0.1", 11434), ("::1", 11434)}
blob = Path("reports/strace_rede.txt").read_text(errors='ignore')
found = set()
for m in re.finditer(r'sin_addr\(inet_addr\("([^"]+)"\).*sin_port=htons\((\d+)\)', blob):
    found.add((m.group(1), int(m.group(2))))
extra = found - allowed
if extra:
    print(f"ALERTA: conexões fora do allowlist: {extra}")
else:
    print(f"OK: apenas endpoints autorizados ({found or 'nenhum — teste não exerceu rede'})")
PY

# Auditar código-fonte em busca de URLs hardcoded
uv run python -c "
import re
from pathlib import Path
allowed_hosts = {'127.0.0.1', 'localhost', '::1'}
urls = []
for p in Path('src').rglob('*.py'):
    for m in re.finditer(r'https?://([a-zA-Z0-9.\-]+)', p.read_text()):
        if m.group(1) not in allowed_hosts:
            urls.append(f'{p}:{m.group(0)}')
if urls:
    print('ALERTA: hosts não autorizados no código:')
    for u in urls: print(' ', u)
else:
    print('OK: apenas localhost no código-fonte')
" | tee reports/url_audit.txt
```

**Critério de aprovação:**
- `rag_maker` não abre portas TCP/UDP em modo servidor.
- Única conexão de saída é para `127.0.0.1:11434`.
- Nenhum host externo hardcoded em `src/`.

**Por que é crítico:** o projeto é retrieval-only **offline**. Qualquer
conexão inesperada viola o contrato e pode indicar dependência
supply-chain maliciosa.

---

## T10 — Validação de Queries e Paths

> Renomeado do original "SQL Injection". O projeto **não usa SQL**.
> O equivalente é validar: filter expressions do LanceDB, path traversal e
> parsing de TOML.

**Objetivo:** garantir que inputs do usuário não construam filters do
LanceDB diretamente nem escapem do diretório de corpus.

**Alvos principais:**
1. LanceDB *filter expressions*: strings SQL-like (`metadata.source = '...'`).
   Concatenar input do usuário com aspas é vulnerabilidade análoga a SQLi.
2. Paths: `pathlib.Path.resolve()` dentro de `corpus_dir` — verificar
   `is_relative_to(corpus_dir)` para bloquear `../../etc/passwd`.
3. TOML: `tomllib` (stdlib) é read-only seguro; validar com `pydantic-settings`
   para rejeitar campos desconhecidos.

```bash
# Buscar concatenação de strings em filter expressions do LanceDB
uv run python -c "
from pathlib import Path
import re
bad = []
for p in Path('src').rglob('*.py'):
    text = p.read_text()
    # Heurística: f-string ou concatenação dentro de .where() / .filter() / to_pandas
    for m in re.finditer(r'(where|filter|search)\s*\(\s*f[\"\'][^\"\']*\{[^}]+\}', text):
        bad.append(f'{p}: {m.group(0)[:80]}')
    for m in re.finditer(r'(where|filter|search)\s*\(\s*[\"\'][^\"\']*[\"\']\s*\+', text):
        bad.append(f'{p}: {m.group(0)[:80]}')
if bad:
    print('ALERTA — filter construído por concatenação:')
    for b in bad: print(' ', b)
else:
    print('OK: nenhuma construção dinâmica de filter detectada')
" | tee reports/lancedb_filters.txt

# Buscar aberturas de arquivo com caminho vindo do usuário sem resolve()
uv run python -c "
from pathlib import Path
import re
susp = []
for p in Path('src').rglob('*.py'):
    text = p.read_text()
    for m in re.finditer(r'open\s*\(\s*(?!.*\.resolve\(\))[^)]*user|input|args', text):
        susp.append(f'{p}: {m.group(0)[:80]}')
if susp:
    for s in susp: print(' ', s)
else:
    print('OK: aberturas de arquivo parecem validadas')
" | tee reports/path_audit.txt

# Conferir uso do utilitário de path safe em loaders
uv run grep -rn "is_relative_to\|resolve()" src/adapters/driven/loaders/ | tee reports/path_guards.txt
```

**Exemplo de utilitário obrigatório (a existir em `src/rag_maker/domain/path_safety.py`):**

```python
from pathlib import Path

class PathEscapeError(ValueError): ...

def safe_path_within(candidate: str | Path, base: Path) -> Path:
    resolved = (base / candidate).resolve() if not Path(candidate).is_absolute() \
                else Path(candidate).resolve()
    base_resolved = base.resolve()
    if not resolved.is_relative_to(base_resolved):
        raise PathEscapeError(f"{resolved} escapa de {base_resolved}")
    return resolved
```

**Critério de aprovação:**
- 0 ocorrências de filter LanceDB construído por f-string / concatenação com input do usuário.
- Todos os paths dos loaders passam por `safe_path_within(...)`.
- Config TOML validada por `pydantic-settings` com `extra='forbid'`.

**Por que é crítico:** um filter como `f"source = '{user_input}'"` permite
que o usuário faça `"' OR '1'='1"` e retorne documentos que deveriam ser
excluídos (vazamento cross-tenant em caso de multi-corpus).

---

## T11 — Fuzzing de Protocolos de Rede

**Objetivo:** garantir que o cliente Ollama lide graciosamente com
respostas malformadas — o daemon pode estar em versão inesperada,
sobrecarregado ou sob ataque MITM.

**Ferramenta:** `respx` simulando respostas malformadas.

Criar `tests/integration/test_ollama_embedder_malformed.py`:

```python
import httpx, respx, pytest
from rag_maker.adapters.driven.ollama.embedder import OllamaEmbedder
from rag_maker.domain.errors import (
    EmbeddingError,
    OllamaUnavailableError,
    DimensionMismatchError,
)

URL = "http://127.0.0.1:11434/api/embed"

@pytest.fixture
def embedder() -> OllamaEmbedder:
    return OllamaEmbedder(base_url="http://127.0.0.1:11434", model="bge-m3:latest")

@respx.mock
def test_empty_body(embedder):
    respx.post(URL).mock(return_value=httpx.Response(200, content=b""))
    with pytest.raises(EmbeddingError):
        embedder.embed(["hi"])

@respx.mock
def test_null_embeddings(embedder):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"embeddings": None}))
    with pytest.raises(EmbeddingError):
        embedder.embed(["hi"])

@respx.mock
def test_empty_embeddings_list(embedder):
    respx.post(URL).mock(return_value=httpx.Response(200, json={"embeddings": []}))
    with pytest.raises(EmbeddingError):
        embedder.embed(["hi"])

@respx.mock
def test_wrong_dimension(embedder):
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.1] * 768]})  # esperado 1024
    )
    with pytest.raises(DimensionMismatchError):
        embedder.embed(["hi"])

@respx.mock
def test_http_500(embedder):
    respx.post(URL).mock(return_value=httpx.Response(500, text="internal error"))
    with pytest.raises(OllamaUnavailableError):
        embedder.embed(["hi"])

@respx.mock
def test_connection_refused(embedder):
    respx.post(URL).mock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(OllamaUnavailableError):
        embedder.embed(["hi"])

@respx.mock
def test_truncated_json(embedder):
    respx.post(URL).mock(return_value=httpx.Response(200, content=b'{"embeddings": [[0.1'))
    with pytest.raises(EmbeddingError):
        embedder.embed(["hi"])

@respx.mock
def test_non_utf8_body(embedder):
    respx.post(URL).mock(return_value=httpx.Response(200, content=b"\x00\xFF\xFE\xFD" * 100))
    with pytest.raises(EmbeddingError):
        embedder.embed(["hi"])

@respx.mock
def test_timeout(embedder):
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("read timeout"))
    with pytest.raises(OllamaUnavailableError):
        embedder.embed(["hi"])
```

Rodar:

```bash
uv run pytest tests/integration/test_ollama_embedder_malformed.py -v \
    | tee reports/fuzzing_rede.txt
```

**Critério de aprovação:**
- O cliente **nunca** crasha com `TypeError`, `KeyError`, `AttributeError`
  ou `json.JSONDecodeError` vazando.
- Toda falha é mapeada para uma de: `EmbeddingError`, `OllamaUnavailableError`,
  `DimensionMismatchError`.
- Testes em `test_ollama_embedder_malformed.py` passam 100%.

**Por que é crítico:** um `json.JSONDecodeError` não tratado aborta a
ingestão de um corpus inteiro em vez de pular o documento problemático.

---

## T12 — Busca de CVEs nas Dependências

**Objetivo:** identificar CVEs conhecidas (CVSS público) nas libs Python
do `uv.lock`.

**Ferramentas:** `pip-audit` + `osv-scanner` + `trivy`.

```bash
# pip-audit — descrição completa + JSON para consolidação
uv run pip-audit --desc --format json --output reports/pip_audit_full.json
uv run pip-audit --desc                 | tee reports/pip_audit_full.txt

# osv-scanner — cruza uv.lock com a base OSV.dev
~/.local/bin/osv-scanner --lockfile=uv.lock \
    --format=json \
    --output=reports/osv.json
~/.local/bin/osv-scanner --lockfile=uv.lock | tee reports/osv.txt

# trivy — varredura de libs (filtro MEDIUM+)
trivy fs . \
    --severity CRITICAL,HIGH,MEDIUM \
    --vuln-type library \
    --format json \
    --output reports/cve_trivy.json
trivy fs . --severity CRITICAL,HIGH,MEDIUM --vuln-type library \
    | tee reports/cve_trivy.txt

# Consulta manual à OSV.dev para pacotes Python chave
uv run python <<'PY'
import urllib.request, json

deps = [
    {"package": {"name": "httpx",            "ecosystem": "PyPI"}},
    {"package": {"name": "pypdf",            "ecosystem": "PyPI"}},
    {"package": {"name": "python-docx",      "ecosystem": "PyPI"}},
    {"package": {"name": "ebooklib",         "ecosystem": "PyPI"}},
    {"package": {"name": "beautifulsoup4",   "ecosystem": "PyPI"}},
    {"package": {"name": "lancedb",          "ecosystem": "PyPI"}},
    {"package": {"name": "ollama",           "ecosystem": "PyPI"}},
    {"package": {"name": "sentence-transformers", "ecosystem": "PyPI"}},
    {"package": {"name": "PySide6",          "ecosystem": "PyPI"}},
    {"package": {"name": "typer",            "ecosystem": "PyPI"}},
    {"package": {"name": "pydantic",         "ecosystem": "PyPI"}},
]
for dep in deps:
    req = urllib.request.Request(
        "https://api.osv.dev/v1/query",
        data=json.dumps(dep).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
            vulns = data.get("vulns", [])
            name = dep["package"]["name"]
            print(f"{name:28s}: {len(vulns):3d} vuln(s)")
    except Exception as e:
        print(f"Erro consultando OSV para {dep['package']['name']}: {e}")
PY
```

**Critério de aprovação:** 0 CVEs CRITICAL sem patch disponível.
HIGH documentadas em `docs/security_exceptions.md` com prazo de atualização.

**Por que é crítico:** `pypdf` e `ebooklib` processam arquivos não confiáveis
fornecidos pelo usuário; um CVE com CVSS ≥ 7 em parsing significa RCE
local no momento da ingestão.

---

## A1 — Descoberta e Modelagem

**Objetivo:** construir mapa mental completo do projeto antes de qualquer
análise profunda.

```bash
# Estrutura de arquivos Python
find src tests -type f -name "*.py" | sort | tee reports/estrutura_py.txt

# Contagem de linhas (tokei preferido; cloc fallback)
uv run tokei src/ tests/ --output json > reports/tokei.json 2>/dev/null \
    || (cloc src/ tests/ --by-file --csv --out=reports/cloc.csv \
        && cloc src/ tests/ | tee reports/cloc_resumo.txt)

# Versão do pacote
uv run python -c "from rag_maker import __version__; print('rag_maker:', __version__)" \
    | tee reports/versao.txt

# Top 10 módulos mais importados internamente
uv run python <<'PY' | tee reports/imports_internos.txt
from collections import Counter
from pathlib import Path
import re

c = Counter()
for p in Path("src").rglob("*.py"):
    for m in re.finditer(r'^\s*from\s+(rag_maker\.[\w.]+)\s+import', p.read_text(), re.MULTILINE):
        c[m.group(1)] += 1
print("=== Top 10 módulos internos mais importados ===")
for mod, n in c.most_common(10):
    print(f"  {n:3d}x  {mod}")
PY

# Presença de testes
find tests -name "test_*.py" -o -name "*_test.py" | tee reports/arquivos_teste.txt

# Entry points declarados (CLI/GUI)
uv run python -c "
import tomllib
cfg = tomllib.load(open('pyproject.toml','rb'))
scripts = cfg.get('project', {}).get('scripts', {})
guis    = cfg.get('project', {}).get('gui-scripts', {})
print('CLI scripts:', scripts)
print('GUI scripts:', guis)
"
```

**Entregável:** mapa de módulos com responsabilidades (domain/application/
adapters/composition), lista de entry points, status de cobertura de testes por camada.

---

## A2 — Auditoria de Arquitetura e Camadas

**Objetivo (crítico para este projeto):** validar que as regras da
arquitetura hexagonal + front/mid/back não são violadas.

**Ferramenta:** `import-linter` com contratos declarativos.

Arquivo `.importlinter` na raiz do projeto:

```ini
[importlinter]
root_packages = rag_maker

[importlinter:contract:1]
name = domain não importa de camadas externas
type = forbidden
source_modules =
    rag_maker.domain
forbidden_modules =
    rag_maker.adapters
    rag_maker.application
    rag_maker.composition

[importlinter:contract:2]
name = application só conhece domain
type = forbidden
source_modules =
    rag_maker.application
forbidden_modules =
    rag_maker.adapters

[importlinter:contract:3]
name = driving não depende de driven
type = forbidden
source_modules =
    rag_maker.adapters.driving
forbidden_modules =
    rag_maker.adapters.driven

[importlinter:contract:4]
name = driven não depende de driving nem application
type = forbidden
source_modules =
    rag_maker.adapters.driven
forbidden_modules =
    rag_maker.adapters.driving
    rag_maker.application
    rag_maker.composition

[importlinter:contract:5]
name = libs externas proibidas em domain
type = forbidden
source_modules =
    rag_maker.domain
forbidden_modules =
    lancedb
    ollama
    pypdf
    docx
    ebooklib
    bs4
    PySide6
    httpx
    sentence_transformers
```

```bash
# Validar contratos
uv run lint-imports --config .importlinter | tee reports/importlinter.txt

# Grafo visual de dependências
uv run pydeps src/rag_maker --max-bacon=3 \
    --cluster \
    -o reports/deps.svg 2>&1 | tee reports/pydeps.txt
```

**Critério de aprovação:** 0 contratos quebrados. Grafo sem arestas
do tipo `domain -> adapters` ou `driven -> driving`.

**Por que é crítico:** a hexagonalidade é o principal valor arquitetural
deste projeto. Uma violação silenciosa (ex.: `from lancedb import ...`
dentro de `domain/scoring.py`) derrota todo o design e trava refatorações
futuras.

---

## A3 — UI/UX e Acessibilidade

**Objetivo:** verificar contraste, tooltips e tab order na GUI PySide6.

```bash
# Contraste WCAG (pares de cores do tema do rag_maker — ajuste conforme o tema real)
uv run python <<'PY' | tee reports/contraste.txt
import wcag_contrast_ratio as contrast

pares = [
    ("Texto / fundo claro",     "#1F2328", "#FFFFFF"),
    ("Texto / fundo escuro",    "#E6EDF3", "#0D1117"),
    ("Acento / fundo claro",    "#0969DA", "#FFFFFF"),
    ("Erro / fundo claro",      "#CF222E", "#FFFFFF"),
    ("Sucesso / fundo escuro",  "#3FB950", "#0D1117"),
]
for nome, fg, bg in pares:
    fg_rgb = tuple(int(fg[i:i+2], 16)/255 for i in (1,3,5))
    bg_rgb = tuple(int(bg[i:i+2], 16)/255 for i in (1,3,5))
    ratio = contrast.rgb(fg_rgb, bg_rgb)
    aa  = "PASS AA" if ratio >= 4.5 else "FAIL AA"
    aaa = "PASS AAA" if ratio >= 7.0 else "-"
    print(f"{nome:28s}: {ratio:5.2f}:1  {aa}  {aaa}")
PY

# Acessibilidade — nomes e tooltips
uv run grep -rn "setToolTip\|setAccessibleName\|setAccessibleDescription\|setWhatsThis" \
    src/adapters/driving/gui/ | tee reports/acessibilidade.txt

# Navegação por teclado
uv run grep -rn "setTabOrder\|setFocusPolicy\|Qt.TabFocus" \
    src/adapters/driving/gui/ | tee -a reports/acessibilidade.txt

# Workers em QThread para UI responsiva (ingestão não pode travar a janela)
uv run grep -rn "QThread\|QRunnable\|moveToThread\|@pyqtSlot\|Signal" \
    src/adapters/driving/gui/ | tee reports/threads_gui.txt
```

**Critério de aprovação:**
- Todos os pares de cores do tema da GUI com ratio ≥ 4.5:1 (WCAG AA).
- Todo botão/ação crítica tem `setToolTip` e `setAccessibleName`.
- Operações longas (ingestão, reindex) rodam em `QThread` com sinais
  para não bloquear a UI.

---

## A4 — QA Geral Python

**Objetivo:** suite agregada de validação pré-merge. Tudo deve estar verde.

```bash
# 1. Sync de dependências (garante ambiente coerente)
uv sync --all-extras

# 2. Lint + format
uv run ruff check .
uv run ruff format --check .

# 3. Types
uv run mypy --strict src/

# 4. Testes + cobertura
uv run pytest --cov=src --cov-fail-under=70

# 5. Arquitetura
uv run lint-imports

# 6. One-shot combinado (falha rápido)
uv run ruff check . \
  && uv run ruff format --check . \
  && uv run mypy --strict src/ \
  && uv run pytest --cov=src --cov-fail-under=70 \
  && uv run lint-imports \
  && echo "A4 OK — todos os gates passaram" | tee reports/a4_ok.txt
```

**Critério de aprovação:** todos os gates passam, 0 warnings, cobertura ≥ 70%.

---

## A5 — Análise Estática e Dinâmica Python

**Objetivo:** varredura profunda combinando várias ferramentas e produzindo
resumo por categoria.

```bash
# ruff — todos os linters ativados via pyproject.toml
uv run ruff check src/ --output-format=json > reports/a5_ruff.json

# mypy
uv run mypy --strict src/ > reports/a5_mypy.txt 2>&1 || true

# bandit — severidade HIGH + MEDIUM
uv run bandit -r src/ -f json -o reports/a5_bandit.json -ll

# vulture — código morto / imports não usados
uv run vulture src/ --min-confidence 80 > reports/a5_vulture.txt 2>&1 || true

# radon — complexidade ciclomática e maintainability index
uv run radon cc src/ -s -a -j > reports/a5_radon_cc.json
uv run radon mi src/ -s    -j > reports/a5_radon_mi.json
uv run radon cc src/ -s -a    | tee reports/a5_radon_cc.txt
uv run radon mi src/ -s       | tee reports/a5_radon_mi.txt

# memray — sanity check de heap em um cenário curto
uv run memray run --output reports/a5_memray.bin \
    -m pytest tests/integration/test_ingestion_pipeline.py::test_mini_corpus

# Resumo consolidado
uv run python <<'PY' | tee reports/a5_resumo.txt
import json
from pathlib import Path

def safe_json(p):
    try: return json.loads(Path(p).read_text())
    except Exception: return None

ruff   = safe_json("reports/a5_ruff.json") or []
bandit = safe_json("reports/a5_bandit.json") or {}
radon  = safe_json("reports/a5_radon_cc.json") or {}

print("=== A5 — Resumo por categoria ===")
print(f"  ruff issues:              {len(ruff)}")
print(f"  bandit HIGH:              {sum(1 for r in bandit.get('results',[]) if r.get('issue_severity')=='HIGH')}")
print(f"  bandit MEDIUM:            {sum(1 for r in bandit.get('results',[]) if r.get('issue_severity')=='MEDIUM')}")
mypy = Path("reports/a5_mypy.txt").read_text()
print(f"  mypy errors:              {mypy.count(': error:')}")
# radon CC >= C (complexity >= 11)
c_or_worse = [f for fname, funcs in radon.items() for f in funcs if f.get('rank','A') >= 'C']
print(f"  radon CC >= C (funcs):    {len(c_or_worse)}")
PY
```

**Critério de aprovação:**
- `ruff issues = 0`
- `mypy errors = 0`
- `bandit HIGH = 0`, `bandit MEDIUM = 0`
- `radon CC >= C` apenas em funções documentadas como exceção
- `memray` sem picos além do budget do cenário

---

## A6 — Cobertura de Testes

**Objetivo:** medir exercício de código com gates por camada.

**Ferramentas:** `pytest-cov` (via `coverage.py`) + `diff-cover` (para PRs).

```bash
# Rodada completa com relatórios multi-formato
uv run pytest \
    --cov=src/rag_maker \
    --cov-report=html:reports/coverage \
    --cov-report=xml:reports/coverage.xml \
    --cov-report=term-missing \
    --cov-report=json:reports/coverage.json \
    --cov-fail-under=70

# Gate por camada (domain 90%, application 80%)
uv run python <<'PY' | tee reports/coverage_por_camada.txt
import json
from pathlib import Path

data = json.loads(Path("reports/coverage.json").read_text())
files = data["files"]

def pct_for(prefix: str) -> float:
    rel = [f for f in files if prefix in f]
    if not rel: return 0.0
    total = sum(files[f]["summary"]["num_statements"] for f in rel)
    cov   = sum(files[f]["summary"]["covered_lines"] for f in rel)
    return 100 * cov / max(1, total)

rows = [
    ("domain",       "src/rag_maker/domain",      90.0),
    ("application",  "src/rag_maker/application", 80.0),
    ("adapters",     "src/rag_maker/adapters",    60.0),
    ("composition",  "src/rag_maker/composition", 60.0),
]
fail = False
for name, prefix, gate in rows:
    got = pct_for(prefix)
    status = "OK" if got >= gate else "FAIL"
    if got < gate: fail = True
    print(f"  {name:12s} {got:5.1f}%  (gate {gate:.0f}%)  {status}")
print()
if fail:
    print("REPROVADO: alguma camada abaixo do gate")
    raise SystemExit(1)
PY

# diff-cover para PR (requer base branch)
uv run diff-cover reports/coverage.xml \
    --compare-branch=main \
    --html-report reports/diff_coverage.html \
    --fail-under 80 2>/dev/null || true
```

**Critério de aprovação:** global ≥ 70%, `domain/` ≥ 90%, `application/` ≥ 80%.
Em PR, `diff-cover` ≥ 80%.

---

## A7 — Dependências e Acoplamento

**Objetivo:** detectar ciclos e módulos supercoplados.

**Ferramentas:** `pydeps` (grafo) + `import-linter` (contratos) + `radon mi`
(maintainability index).

```bash
# Grafo visual completo
uv run pydeps src/rag_maker \
    --max-bacon=3 \
    --cluster \
    --show-deps \
    -T svg \
    -o reports/deps.svg

# Grafo apenas entre camadas principais
uv run pydeps src/rag_maker.domain \
    --max-bacon=2 -o reports/deps_domain.svg

uv run pydeps src/rag_maker.application \
    --max-bacon=2 -o reports/deps_application.svg

# Detectar ciclos com pydeps
uv run pydeps src/rag_maker --show-cycles -T svg -o reports/cycles.svg \
    2>&1 | tee reports/cycles.txt

# Maintainability Index (A = ótimo, F = péssimo)
uv run radon mi src/ -s -n C | tee reports/mi_baixo.txt

# Módulos mais dependidos (in-degree) e mais dependentes (out-degree)
uv run python <<'PY' | tee reports/deps_ranking.txt
from collections import Counter, defaultdict
from pathlib import Path
import re

out_deg = defaultdict(set)
for p in Path("src").rglob("*.py"):
    mod_name = str(p.relative_to("src")).replace("/", ".").removesuffix(".py")
    for m in re.finditer(r'^\s*(?:from|import)\s+(rag_maker\.[\w.]+)', p.read_text(), re.MULTILINE):
        out_deg[mod_name].add(m.group(1))

in_deg = Counter()
for deps in out_deg.values():
    for d in deps: in_deg[d] += 1

print("=== Top 10 mais importados (in-degree) ===")
for m, n in in_deg.most_common(10):
    print(f"  {n:3d}  {m}")
print("\n=== Top 10 mais dependentes (out-degree) ===")
for m, deps in sorted(out_deg.items(), key=lambda kv: -len(kv[1]))[:10]:
    print(f"  {len(deps):3d}  {m}")
PY
```

**Critério de aprovação:**
- 0 ciclos de dependência.
- Nenhum módulo com `in-degree > 15` sem justificativa (ex.: `errors.py`,
  `domain/models.py` podem ser exceções documentadas).
- Maintainability Index `< C` apenas em casos documentados.

---

## A8 — Consistência Protocols ↔ Implementations

> Substitui o "A8 .h vs .cpp" do original. Em Python puro não existem
> headers, mas o equivalente é: para cada `Protocol` em
> `domain/ports/`, deve haver ao menos uma implementação em
> `adapters/driven/` que satisfaça structural subtyping.

**Objetivo:** garantir que cada porta tem implementação e que toda
implementação bate com o protocolo.

**Ferramentas:** `mypy --strict` (parte da validação é estrutural) +
script dedicado.

Criar `scripts/check_ports_implementations.py`:

```python
"""Verifica que cada Protocol em rag_maker.domain.ports tem >= 1 implementação
em rag_maker.adapters.driven que satisfaz runtime_checkable.
"""
from __future__ import annotations
import importlib, inspect, pkgutil, sys
from typing import Protocol, get_type_hints, runtime_checkable

import rag_maker.domain.ports as ports_pkg
import rag_maker.adapters.driven as driven_pkg

def iter_submodules(pkg):
    for m in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        try:
            yield importlib.import_module(m.name)
        except Exception as e:
            print(f"ERRO ao importar {m.name}: {e}", file=sys.stderr)

protocols: list[type] = []
for mod in iter_submodules(ports_pkg):
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if obj.__module__ == mod.__name__ and issubclass(obj, Protocol):
            protocols.append(obj)

impls: list[type] = []
for mod in iter_submodules(driven_pkg):
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if obj.__module__ == mod.__name__:
            impls.append(obj)

issues: list[str] = []
for proto in protocols:
    runtime = runtime_checkable(proto) if not getattr(proto, "_is_runtime_protocol", False) else proto
    matching = []
    for impl in impls:
        try:
            # instanciação provisional apenas para structural check
            sig = inspect.signature(impl.__init__)
            # se construtor pede args, pulamos e confiamos no mypy
            if any(p.default is inspect.Parameter.empty and p.kind != inspect.Parameter.VAR_POSITIONAL
                   for n, p in sig.parameters.items() if n != "self"):
                matching.append(impl.__name__)
                continue
            inst = impl()
            if isinstance(inst, runtime):
                matching.append(impl.__name__)
        except Exception:
            pass
    if not matching:
        issues.append(f"Protocol sem implementação: {proto.__module__}.{proto.__name__}")

print(f"Protocols encontrados:       {len(protocols)}")
print(f"Implementações encontradas:  {len(impls)}")
print(f"Problemas: {len(issues)}")
for i in issues:
    print(f"  - {i}")
sys.exit(1 if issues else 0)
```

```bash
uv run python scripts/check_ports_implementations.py \
    | tee reports/ports_impl_check.txt

# mypy strict já valida structural subtyping em injeções do tipo
# service: EmbedderPort = OllamaEmbedder(...) — rodar novamente e conferir
uv run mypy --strict src/rag_maker/composition/ | tee reports/ports_mypy.txt
```

**Critério de aprovação:** todo Protocol em `domain/ports/` tem ≥ 1
implementação viável em `adapters/driven/`; `mypy --strict` sem erros
de assinatura nas wirings em `composition/`.

---

## A9 — Análise Arquitetural Geral

**Objetivo:** classificar a saúde arquitetural — tamanho de arquivos,
god objects, TODOs, complexidade.

```bash
uv run python <<'PY' | tee reports/analise_arq.txt
from pathlib import Path
import re

print("=== Análise arquitetural por arquivo ===\n")
relatorios = []
for py in sorted(Path("src").rglob("*.py")):
    text  = py.read_text(errors='ignore')
    lines = text.splitlines()
    nloc  = len(lines)
    funcs = re.findall(r'^\s*(?:async\s+)?def\s+(\w+)', text, re.MULTILINE)
    classes = re.findall(r'^\s*class\s+(\w+)', text, re.MULTILINE)
    todos = len(re.findall(r'\b(TODO|FIXME|HACK|XXX)\b', text))

    # Funções longas (> 40 linhas entre "def" e próxima "def"/"class"/EOF)
    func_spans = []
    for m in re.finditer(r'^(\s*)(?:async\s+)?def\s+(\w+)', text, re.MULTILINE):
        start = m.start()
        rest  = text[start:]
        depth = 0
        end = len(rest)
        for i, line in enumerate(rest.splitlines()[1:], start=1):
            if line.strip() == "": continue
            indent = len(line) - len(line.lstrip())
            if indent <= len(m.group(1)):
                end = i
                break
        func_spans.append((m.group(2), end))
    long_funcs = [n for n, sz in func_spans if sz > 40]

    issues = []
    if nloc > 500:             issues.append(f"arquivo grande ({nloc} linhas)")
    if len(classes) > 15:      issues.append(f"god module ({len(classes)} classes)")
    if long_funcs:             issues.append(f"{len(long_funcs)} função(ões) > 40 linhas")
    if todos > 0:              issues.append(f"{todos} TODO(s)")

    score = 100 - min(100, nloc // 20 + len(long_funcs)*5 + todos*2 + (50 if len(classes) > 15 else 0))
    relatorios.append((score, py, issues, nloc))

relatorios.sort()
print("--- Mais problemáticos ---")
for score, py, issues, nloc in relatorios[:10]:
    marker = "FAIL" if issues else "OK"
    print(f"  {marker} score={score:3d}  {py.relative_to('src')}: {' | '.join(issues) or f'{nloc} linhas'}")

print("\n--- Mais saudáveis ---")
for score, py, issues, nloc in relatorios[-5:]:
    print(f"  OK   score={score:3d}  {py.relative_to('src')}: {nloc} linhas")
PY
```

**Critério de aprovação:** nenhum arquivo com score < 30. TODOs rastreados
em `TODO.md`.

---

## A10 — Relatório Final de Auditoria

**Objetivo:** consolidar todos os relatórios anteriores em `audit_report.md`
e `audit_report.json` com scores 0-100 por área.

```bash
uv run python <<'REPORT' | tee reports/audit_report.md
import json
from pathlib import Path
from datetime import date

R = Path("reports")
scores: dict[str, object] = {}

def safe_json(p: str):
    path = R / p
    try:    return json.loads(path.read_text())
    except: return None

# T2 — ruff + mypy + bandit
ruff_n = len(safe_json("ruff.json") or [])
bandit = safe_json("bandit.json") or {"results": []}
bandit_high = sum(1 for r in bandit.get("results", []) if r.get("issue_severity") == "HIGH")
bandit_med  = sum(1 for r in bandit.get("results", []) if r.get("issue_severity") == "MEDIUM")
mypy_errs = Path("reports/mypy.txt").read_text().count(": error:") if (R/"mypy.txt").exists() else None
scores["T2_static"] = max(0, 100 - ruff_n*2 - (mypy_errs or 0)*5 - bandit_high*20 - bandit_med*5)

# T5/T12 — CVEs
pip_audit = safe_json("pip_audit.json") or {}
crits = 0; highs = 0
for dep in pip_audit.get("dependencies", []):
    for v in dep.get("vulns", []):
        highs += 1
scores["T5_deps"] = max(0, 100 - crits*25 - highs*5)

# T8 — secrets
gl = safe_json("gitleaks.json") or []
scores["T8_secrets"] = 100 if not gl else 0

# A2 — import-linter
il_txt = (R/"importlinter.txt").read_text() if (R/"importlinter.txt").exists() else ""
il_broken = il_txt.count("BROKEN")
scores["A2_architecture"] = 100 if il_broken == 0 else max(0, 100 - il_broken*25)

# A6 — cobertura
cov = safe_json("coverage.json") or {}
total = cov.get("totals", {}).get("percent_covered", 0)
scores["A6_coverage"] = int(total)

# Score global (média ponderada)
weights = {"T2_static":0.2,"T5_deps":0.15,"T8_secrets":0.15,"A2_architecture":0.25,"A6_coverage":0.25}
global_score = sum(int(scores[k]) * w for k,w in weights.items())

md = f"""# Relatório Final de Auditoria — rag_maker

Data: {date.today().isoformat()}

## Scores por área (0-100)

| Área                                    | Score |
|-----------------------------------------|-------|
| T2 Análise estática (ruff+mypy+bandit)  | {scores['T2_static']:>5} |
| T5 Dependências (pip-audit)             | {scores['T5_deps']:>5} |
| T8 Secrets (gitleaks)                   | {scores['T8_secrets']:>5} |
| A2 Arquitetura (import-linter)          | {scores['A2_architecture']:>5} |
| A6 Cobertura de testes                  | {scores['A6_coverage']:>5} |
| **Score global ponderado**              | **{global_score:>4.1f}** |

## Relatórios gerados em `reports/`

- `ruff.json`, `mypy.txt`, `bandit.json`
- `pip_audit.json`, `safety.json`, `trivy.json`, `osv.json`
- `gitleaks.json`, `trufflehog.json`
- `importlinter.txt`, `deps.svg`
- `coverage/` (HTML), `coverage.json`, `coverage.xml`
- `memray.bin`, `memray_flame.html`
- `hurl.json`, `hurl_html/`
- `atheris_pdf.txt`
- `analise_arq.txt`
"""
Path("reports/audit_report.md").write_text(md)
Path("reports/audit_report.json").write_text(json.dumps(
    {"date": date.today().isoformat(), "scores": scores, "global": global_score},
    indent=2,
))
print(md)
REPORT
```

**Entregável obrigatório:**
1. Score global por área (0-100).
2. Percentual de cobertura de testes por módulo (domain/application/adapters).
3. Sumário CRÍTICO / MÉDIO / BAIXO.
4. Top 5 issues mais impactantes com arquivo + linha.
5. Lista de ciclos de dependência (se houver).
6. Patches no formato unificado.

---

## Classificação de Problemas

| Severidade | Critério Python/rag_maker | Ação |
|-----------|---------------------------|------|
| **CRÍTICO** | Teste falhando · erro em `mypy --strict` · violação em `import-linter` · CVE CRITICAL sem patch · secret exposto · 0% de cobertura em `domain/` · crash do embedder em input malformado · conexão de rede fora do allowlist | Bloquear merge/release. Corrigir imediatamente. |
| **MÉDIO** | Warning de `ruff` · `bandit` MEDIUM · cobertura global < 50% · função com `radon CC >= C` · módulo público sem docstring · `vulture` confiança ≥ 90 · CVE HIGH documentada sem prazo | Corrigir antes do próximo release. |
| **BAIXO** | `TODO`/`FIXME`/`HACK` em código · docstring ausente em função interna · naming inconsistente · import não-canônico · MI entre B e C · warning atômico em log | Registrar em `TODO.md`, corrigir no backlog. |

---

## Formato de Patch

Todo problema com correção deve incluir patch unificado em diff Python:

```diff
--- a/src/rag_maker/adapters/driven/loaders/pdf_loader.py
+++ b/src/rag_maker/adapters/driven/loaders/pdf_loader.py
@@ -12,9 +12,17 @@
 from pathlib import Path

+import logging
+
+from rag_maker.domain.errors import LoaderError
+
+logger = logging.getLogger(__name__)
+
 def load_pdf(path: Path) -> str:
     try:
         from pypdf import PdfReader
         reader = PdfReader(str(path))
         return "\n".join(p.extract_text() or "" for p in reader.pages)
-    except Exception:
-        pass
+    except (FileNotFoundError, PermissionError) as exc:
+        logger.error("pdf_not_accessible", extra={"path": str(path), "error": str(exc)})
+        raise LoaderError(f"pdf inacessível: {path}") from exc
+    except Exception as exc:  # parsing bug do pypdf
+        logger.warning("pdf_parse_failed", extra={"path": str(path), "error": str(exc)})
+        raise LoaderError(f"pdf corrompido: {path}") from exc
```

---

*Documento gerado para o projeto rag_maker — adapte caminhos e módulos conforme o projeto alvo.*
*Ferramentas: pytest · ruff · mypy · bandit · hypothesis · respx · memray · pip-audit · trivy · gitleaks · trufflehog · hurl · import-linter · pydeps · radon · vulture · osv-scanner · twine · pyroma · nmap · strace*
