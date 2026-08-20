#!/usr/bin/env bash
# Espelha o pipeline .github/workflows/ci.yml (pendente de porte) localmente.
# Rode antes de `git push` para evitar ciclo push-wait-fail.
# Ver TESTES.md T15.1 para variante container-level.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== ruff check =="
uv run ruff check src/ tests/

echo "== ruff format check =="
uv run ruff format --check src/ tests/

echo "== mypy strict =="
uv run mypy src/

echo "== import-linter (hexagonal) =="
uv run lint-imports

echo "== bandit (medium+) =="
uv run bandit -r src/ -c bandit.yaml --severity-level medium

echo "== pip-audit (SCA) =="
# Mantenha esta lista IDÊNTICA à do .github/workflows/ci.yml (pendente de porte) (ver comentário
# lá para a tabela pacote/CVE/data/justificativa). Ao bumpar uma dependência,
# remova o --ignore-vuln correspondente nos DOIS arquivos no mesmo commit.
uv run pip-audit --skip-editable \
  --ignore-vuln PYSEC-2026-3447 \
  --ignore-vuln CVE-2025-3000

echo "== pytest unit + integration (coverage gate) =="
# F12.31 / AUD (onda CRÍTICA): CUDA_VISIBLE_DEVICES="" + `-k "not reranker"`
# só neste run LOCAL. Nesta máquina o cache HuggingFace já tem
# BAAI/bge-reranker-v2-m3 (~2.3GB fp32) baixado, então os testes de
# TestCrossEncoderReranker (tests/integration/test_reranker.py) tentariam
# carregar o modelo de verdade -- na GPU de 4GB já ocupada isso arrisca OOM.
# No CI o cache não existe, então esses mesmos testes já fazem skipif
# (ver comentário em ci.yml "Unit + integration tests") -- não precisa do
# mesmo guard lá. Deselecionar por `-k` em vez de rodar sem cobertura: o
# gate --cov-fail-under=70 continua validado (medido em 73.30% sem esses
# testes -- ver preci.sh histórico / relatório F12.31).
CUDA_VISIBLE_DEVICES="" QT_QPA_PLATFORM=offscreen uv run pytest \
  -m "unit or integration" -k "not reranker" -q \
  --cov=src/rag_maker --cov-report=term-missing --cov-fail-under=70

echo "== pytest e2e (CLI via subprocess) =="
QT_QPA_PLATFORM=offscreen uv run pytest -m e2e -q --no-cov

echo "== build wheel + sdist =="
uv build

echo
echo "ALL GREEN — pode dar push."
