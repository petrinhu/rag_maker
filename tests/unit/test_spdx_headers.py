# SPDX-License-Identifier: AGPL-3.0-or-later
"""Testes de `scripts/spdx_headers.py` (F12.34).

`scripts/` não é um pacote instalável, então a lógica é carregada via
`importlib.util.spec_from_file_location` para exercitar `_insertion_line`,
`_has_header`, `_with_header_inserted`, `check()` e `fix()` diretamente.
Os modos de CLI (`--check`/`--fix`, exit codes) são exercitados via
`subprocess` com `sys.executable`, conforme o script realmente é invocado
em produção (gate de CI / pre-commit).

Nenhum caso toca `src/` real: todos os arquivos-alvo são sintéticos,
criados em `tmp_path`.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "spdx_headers.py"


def _load_spdx_headers_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("spdx_headers", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spdx_headers = _load_spdx_headers_module()
HEADER = spdx_headers.HEADER


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.unit
class TestFutureImportPlacement:
    """Header nunca pode quebrar `from __future__ import annotations`."""

    def test_header_inserted_before_future_import(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("from __future__ import annotations\n\nx = 1\n", encoding="utf-8")

        changed = spdx_headers.fix([target])

        assert changed == [target]
        result = target.read_text(encoding="utf-8")
        lines = result.splitlines()
        assert lines[0] == HEADER
        assert lines[1] == "from __future__ import annotations"

    def test_future_import_remains_first_functional_statement(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("from __future__ import annotations\n\nx = 1\n", encoding="utf-8")

        spdx_headers.fix([target])
        result = target.read_text(encoding="utf-8")

        # Compila sem SyntaxError: comentário antes do future import é
        # permitido pela gramática; se o header tivesse virado código real
        # (ou o future import tivesse sido deslocado para depois de outro
        # statement), compile() levantaria SyntaxError aqui.
        compile(result, str(target), "exec")
        import ast

        tree = ast.parse(result)
        assert isinstance(tree.body[0], ast.ImportFrom)
        assert tree.body[0].module == "__future__"


@pytest.mark.unit
class TestModuleDocstringPlacement:
    """Header entra depois do docstring de módulo, sem quebrá-lo."""

    def test_header_inserted_after_docstring_without_breaking_it(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text('"""Module doc."""\n\nx = 1\n', encoding="utf-8")

        spdx_headers.fix([target])
        result = target.read_text(encoding="utf-8")
        lines = result.splitlines()

        assert lines[0] == '"""Module doc."""'
        assert HEADER in lines
        assert lines.index(HEADER) > lines.index('"""Module doc."""')

        import ast

        tree = ast.parse(result)
        assert ast.get_docstring(tree) == "Module doc."


@pytest.mark.unit
class TestShebangAndDocstringPlacement:
    """Shebang fica na linha 1; header entra depois dele (e do docstring)."""

    def test_shebang_stays_on_line_one(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text('#!/usr/bin/env python3\n"""Module doc."""\n\nx = 1\n', encoding="utf-8")

        spdx_headers.fix([target])
        result = target.read_text(encoding="utf-8")
        lines = result.splitlines()

        assert lines[0] == "#!/usr/bin/env python3"
        assert lines[1] == '"""Module doc."""'
        assert lines[2] == HEADER

        import ast

        tree = ast.parse(result)
        assert ast.get_docstring(tree) == "Module doc."

    def test_shebang_without_docstring_still_stays_on_line_one(self, tmp_path: Path) -> None:
        """Pin regression: sem docstring, só o guard de shebang protege a
        linha 1 (o guard do docstring, quando presente, mascararia esse bug
        — ver TestShebangAndDocstringPlacement.test_shebang_stays_on_line_one,
        que sozinho não pegaria a regressão de `_insertion_line` ignorar
        shebang)."""
        target = tmp_path / "mod.py"
        target.write_text("#!/usr/bin/env python3\nx = 1\n", encoding="utf-8")

        spdx_headers.fix([target])
        result = target.read_text(encoding="utf-8")
        lines = result.splitlines()

        assert lines[0] == "#!/usr/bin/env python3"
        assert lines[1] == HEADER
        assert lines[2] == "x = 1"


@pytest.mark.unit
class TestEmptyFile:
    """Arquivo vazio não pode derrubar o script."""

    def test_fix_does_not_crash_on_empty_file(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.py"
        target.write_text("", encoding="utf-8")

        changed = spdx_headers.fix([target])

        assert changed == [target]
        assert target.read_text(encoding="utf-8") == HEADER + "\n"

    def test_check_reports_empty_file_as_missing_header(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.py"
        target.write_text("", encoding="utf-8")

        missing = spdx_headers.check([target])

        assert missing == [target]


@pytest.mark.unit
class TestIdempotency:
    """Rodar --fix 2x não duplica o header."""

    def test_fix_twice_does_not_duplicate_header(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("from __future__ import annotations\n\nx = 1\n", encoding="utf-8")

        spdx_headers.fix([target])
        first_pass = target.read_text(encoding="utf-8")

        changed_second_pass = spdx_headers.fix([target])
        second_pass = target.read_text(encoding="utf-8")

        assert changed_second_pass == []
        assert second_pass == first_pass
        assert first_pass.count(HEADER) == 1

    def test_fix_via_cli_twice_does_not_duplicate_header(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("from __future__ import annotations\n\nx = 1\n", encoding="utf-8")

        first = _run_cli("--fix", str(target))
        first_pass = target.read_text(encoding="utf-8")

        second = _run_cli("--fix", str(target))
        second_pass = target.read_text(encoding="utf-8")

        assert first.returncode == 0
        assert second.returncode == 0
        assert second_pass == first_pass
        assert first_pass.count(HEADER) == 1


@pytest.mark.unit
class TestCheckExitCode:
    """`--check` é o gate de CI: exit code precisa ser confiável."""

    def test_check_exits_1_when_header_missing(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text("x = 1\n", encoding="utf-8")

        result = _run_cli("--check", str(target))

        assert result.returncode == 1
        assert "sem SPDX header" in result.stdout

    def test_check_exits_0_when_header_present(self, tmp_path: Path) -> None:
        target = tmp_path / "mod.py"
        target.write_text(f"{HEADER}\n\nx = 1\n", encoding="utf-8")

        result = _run_cli("--check", str(target))

        assert result.returncode == 0
        assert "OK" in result.stdout
