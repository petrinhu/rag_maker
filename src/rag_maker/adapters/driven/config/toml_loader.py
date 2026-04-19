from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

import tomli_w


def load_toml(path: Path) -> dict[str, Any]:
    """Carrega um arquivo TOML. Retorna dict vazio se o arquivo não existir."""
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def save_toml(path: Path, data: dict[str, Any]) -> None:
    """Escreve data como TOML em path de forma atômica (write-then-rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = tomli_w.dumps(data).encode()
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".cfg_tmp_")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
