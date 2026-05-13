from __future__ import annotations

from pathlib import Path

import pytest
import tomli_w

from rag_maker.application.config import AppConfig


@pytest.mark.unit
class TestAppConfigDefaults:
    def test_default_ollama_model(self) -> None:
        cfg = AppConfig()
        assert cfg.ollama.embedding_model == "bge-m3:latest"

    def test_default_chunk_size(self) -> None:
        cfg = AppConfig()
        assert cfg.chunking.size == 1000
        assert cfg.chunking.overlap == 200

    def test_default_retrieval(self) -> None:
        cfg = AppConfig()
        assert cfg.retrieval.rerank_top_k == 8
        assert 0.0 <= cfg.retrieval.alpha <= 1.0

    def test_embedding_dim_none_by_default(self) -> None:
        cfg = AppConfig()
        assert cfg.embedding_dim is None

    def test_ignored_paths_empty_by_default(self) -> None:
        cfg = AppConfig()
        assert cfg.ignored.paths == []


@pytest.mark.unit
class TestAppConfigFromFile:
    def test_loads_toml(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "config.toml"
        data = {
            "chunking": {"size": 500, "overlap": 100},
            "ollama": {"embedding_model": "custom:latest"},
        }
        toml_path.write_bytes(tomli_w.dumps(data).encode())
        cfg = AppConfig.from_file(toml_path)
        assert cfg.chunking.size == 500
        assert cfg.ollama.embedding_model == "custom:latest"

    def test_nonexistent_file_returns_defaults(self, tmp_path: Path) -> None:
        cfg = AppConfig.from_file(tmp_path / "no_such.toml")
        assert cfg.chunking.size == 1000

    def test_partial_toml_keeps_other_defaults(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "config.toml"
        toml_path.write_bytes(tomli_w.dumps({"chunking": {"size": 300}}).encode())
        cfg = AppConfig.from_file(toml_path)
        assert cfg.chunking.size == 300
        assert cfg.chunking.overlap == 200


@pytest.mark.unit
class TestAppConfigEnvOverride:
    def test_env_overrides_nested_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_MAKER_CHUNKING__SIZE", "42")
        cfg = AppConfig()
        assert cfg.chunking.size == 42

    def test_env_overrides_ollama_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAG_MAKER_OLLAMA__EMBEDDING_MODEL", "my-model:v1")
        cfg = AppConfig()
        assert cfg.ollama.embedding_model == "my-model:v1"

    def test_env_overrides_toml_when_both_present(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        toml_path = tmp_path / "config.toml"
        toml_path.write_bytes(tomli_w.dumps({"paths": {"db_dir": "/from/toml"}}).encode())
        monkeypatch.setenv("RAG_MAKER_PATHS__DB_DIR", "/from/env")
        cfg = AppConfig.from_file(toml_path)
        assert str(cfg.paths.db_dir) == "/from/env"


@pytest.mark.unit
class TestDeepMerge:
    def test_override_replaces_scalar(self) -> None:
        from rag_maker.application.config import _deep_merge

        out = _deep_merge({"a": 1}, {"a": 2})
        assert out == {"a": 2}

    def test_override_adds_new_key(self) -> None:
        from rag_maker.application.config import _deep_merge

        out = _deep_merge({"a": 1}, {"b": 2})
        assert out == {"a": 1, "b": 2}

    def test_nested_merge_keeps_base_keys(self) -> None:
        from rag_maker.application.config import _deep_merge

        out = _deep_merge({"x": {"a": 1, "b": 2}}, {"x": {"b": 99}})
        assert out == {"x": {"a": 1, "b": 99}}

    def test_override_dict_replaces_scalar_in_base(self) -> None:
        from rag_maker.application.config import _deep_merge

        out = _deep_merge({"x": 1}, {"x": {"y": 2}})
        assert out == {"x": {"y": 2}}

    def test_does_not_mutate_inputs(self) -> None:
        from rag_maker.application.config import _deep_merge

        base = {"x": {"a": 1}}
        override = {"x": {"b": 2}}
        _deep_merge(base, override)
        assert base == {"x": {"a": 1}}
        assert override == {"x": {"b": 2}}
