#!/usr/bin/env python3
"""Insere/valida o header SPDX-License-Identifier em arquivos Python.

Uso:
    python scripts/spdx_headers.py --fix   <arquivo_ou_glob> [...]
    python scripts/spdx_headers.py --check <arquivo_ou_glob> [...]

--fix   insere o header onde falta (idempotente: já presente => não altera).
--check não altera nada; sai com código 1 e lista os arquivos sem header
        (uso pretendido: gate de CI).

Regra de posicionamento: o header entra ANTES de qualquer código, mas
DEPOIS de um eventual shebang (`#!...`) na linha 1 e DEPOIS de um eventual
docstring de módulo (primeira statement do arquivo). Em particular, nunca
quebra `from __future__ import annotations` — na maioria dos módulos deste
projeto, que começam direto em `from __future__ import annotations`, o
header vira a linha 1 e o `from __future__` desce para a linha 2.

Este script é standalone: não depende de nada do pacote rag_maker.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

HEADER = "# SPDX-License-Identifier: AGPL-3.0-or-later"


def _insertion_line(source: str) -> int:
    """Retorna o número de linha (1-indexed) após o qual o header deve ir.

    0 significa "no topo do arquivo" (antes de qualquer linha existente).
    """
    lines = source.splitlines()
    insertion = 0

    if lines and lines[0].startswith("#!"):
        insertion = 1

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Arquivo com erro de sintaxe: não sabemos onde fica o docstring,
        # mas o shebang (se houver) ainda é respeitado.
        return insertion

    body = tree.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        docstring_end = body[0].end_lineno
        if docstring_end is not None:
            insertion = max(insertion, docstring_end)

    return insertion


def _has_header(source: str) -> bool:
    return any(line.strip() == HEADER for line in source.splitlines())


def _with_header_inserted(source: str) -> str:
    if not source:
        return HEADER + "\n"

    lines = source.splitlines()
    insertion = _insertion_line(source)
    lines.insert(insertion, HEADER)

    result = "\n".join(lines)
    if source.endswith("\n"):
        result += "\n"
    return result


def check(paths: list[Path]) -> list[Path]:
    """Retorna a lista de arquivos que ainda não têm o header."""
    missing = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        if not _has_header(source):
            missing.append(path)
    return missing


def fix(paths: list[Path]) -> list[Path]:
    """Insere o header onde falta. Retorna a lista de arquivos alterados."""
    changed = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        if _has_header(source):
            continue
        new_source = _with_header_inserted(source)
        path.write_text(new_source, encoding="utf-8")
        changed.append(path)
    return changed


def _resolve_paths(patterns: list[str]) -> list[Path]:
    resolved: list[Path] = []
    for pattern in patterns:
        path = Path(pattern)
        if path.is_dir():
            resolved.extend(sorted(path.rglob("*.py")))
        elif path.is_file():
            resolved.append(path)
        elif path.is_absolute():
            # Caminho absoluto que não existe: não é um glob válido
            # (Path.glob não aceita padrões absolutos) — apenas ignora.
            print(f"aviso: caminho não encontrado, ignorado: {pattern}", file=sys.stderr)
        else:
            matches = sorted(Path().glob(pattern))
            if not matches:
                print(f"aviso: nenhum arquivo casou com o padrão: {pattern}", file=sys.stderr)
            resolved.extend(matches)
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fix", action="store_true", help="insere o header onde falta")
    mode.add_argument(
        "--check",
        action="store_true",
        help="não altera nada; sai 1 se algum arquivo não tiver o header",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="arquivos, diretórios (recursivo) ou globs de arquivos .py",
    )
    args = parser.parse_args(argv)

    paths = _resolve_paths(args.paths)
    if not paths:
        print("Nenhum arquivo .py encontrado para os caminhos informados.", file=sys.stderr)
        return 1

    if args.check:
        missing = check(paths)
        if missing:
            print("Arquivos sem SPDX header:")
            for path in missing:
                print(f"  {path}")
            return 1
        print(f"OK: {len(paths)} arquivo(s) com SPDX header.")
        return 0

    changed = fix(paths)
    if changed:
        print(f"Header inserido em {len(changed)} arquivo(s):")
        for path in changed:
            print(f"  {path}")
    else:
        print(f"OK: {len(paths)} arquivo(s) já tinham o SPDX header.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
