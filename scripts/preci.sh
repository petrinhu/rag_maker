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

echo "== pytest unit =="
QT_QPA_PLATFORM=offscreen uv run pytest -m unit -q --no-cov

echo "== build wheel + sdist =="
uv build

echo
echo "ALL GREEN — pode dar push."
