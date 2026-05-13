from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "unit: testes unitários puros (sem I/O)")
    config.addinivalue_line(
        "markers", "integration: testes com I/O real ou mocks de serviços externos"
    )
    config.addinivalue_line("markers", "e2e: testes de ponta a ponta via subprocess")


@pytest.fixture()
def tmp_config_dir(tmp_path: pytest.TempPathFactory) -> object:
    config_dir = tmp_path / "rag_maker"
    config_dir.mkdir()
    return config_dir
