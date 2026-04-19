from __future__ import annotations

from pathlib import Path

import pytest
import tomli_w

from rag_maker.adapters.driven.config.toml_loader import load_toml, save_toml


@pytest.mark.integration
class TestTomlLoader:
    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        assert load_toml(tmp_path / "nope.toml") == {}

    def test_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.toml"
        data = {"chunking": {"size": 500}, "key": "value"}
        save_toml(path, data)
        assert load_toml(path) == data

    def test_atomic_creates_parent_dir(self, tmp_path: Path) -> None:
        path = tmp_path / "sub" / "nested" / "cfg.toml"
        save_toml(path, {"x": 1})
        assert path.exists()

    def test_load_existing_toml(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.toml"
        path.write_text('[section]\nkey = "val"\n', encoding="utf-8")
        result = load_toml(path)
        assert result["section"]["key"] == "val"

    def test_overwrite_is_idempotent(self, tmp_path: Path) -> None:
        path = tmp_path / "cfg.toml"
        save_toml(path, {"v": 1})
        save_toml(path, {"v": 2})
        assert load_toml(path) == {"v": 2}
