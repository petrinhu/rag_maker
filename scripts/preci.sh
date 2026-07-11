#!/usr/bin/env bash
# Espelha o pipeline .forgejo/workflows/ci.yml localmente.
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
# Mantenha esta lista IDÊNTICA à do .forgejo/workflows/ci.yml (ver comentário
# lá para a tabela pacote/CVE/data/justificativa). Ao bumpar uma dependência,
# remova o --ignore-vuln correspondente nos DOIS arquivos no mesmo commit.
uv run pip-audit --skip-editable \
  --ignore-vuln GHSA-537c-gmf6-5ccf \
  --ignore-vuln PYSEC-2026-215 \
  --ignore-vuln CVE-2026-44843 \
  --ignore-vuln CVE-2026-45134 \
  --ignore-vuln GHSA-f4xh-w4cj-qxq8 \
  --ignore-vuln GHSA-6v7p-g79w-8964 \
  --ignore-vuln PYSEC-2026-196 \
  --ignore-vuln CVE-2026-3219 \
  --ignore-vuln CVE-2026-6357 \
  --ignore-vuln GHSA-4xgf-cpjx-pc3j \
  --ignore-vuln CVE-2026-48156 \
  --ignore-vuln CVE-2026-48155 \
  --ignore-vuln CVE-2026-48735 \
  --ignore-vuln CVE-2026-49461 \
  --ignore-vuln CVE-2026-49460 \
  --ignore-vuln CVE-2026-54531 \
  --ignore-vuln CVE-2026-54530 \
  --ignore-vuln GHSA-jm82-fx9c-mx94 \
  --ignore-vuln CVE-2026-54651 \
  --ignore-vuln CVE-2026-49477 \
  --ignore-vuln CVE-2026-49476 \
  --ignore-vuln CVE-2025-3000 \
  --ignore-vuln PYSEC-2026-142 \
  --ignore-vuln PYSEC-2026-141

echo "== pytest unit + integration (coverage gate) =="
QT_QPA_PLATFORM=offscreen uv run pytest -m "unit or integration" -q \
  --cov=src/rag_maker --cov-report=term-missing --cov-fail-under=70

echo "== pytest e2e (CLI via subprocess) =="
QT_QPA_PLATFORM=offscreen uv run pytest -m e2e -q --no-cov

echo "== build wheel + sdist =="
uv build

echo
echo "ALL GREEN — pode dar push."
