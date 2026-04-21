# Sincronização corpus ↔ rag — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer a pasta do rag acompanhar automaticamente a pasta do corpus (sempre `{corpus_dir}/rag`) tanto ao trocar corpus pela aba **Corpus** quanto pela aba **Configurações**, preservando o banco vetorial existente e atualizando as duas abas de forma sincronizada.

**Architecture:** Novo método `Container.rebind_to_corpus(Path) -> bool` concentra a transição (persiste config, cria `rag/`, troca store e use cases). `MainWindow` coordena via signals `corpus_change_requested(str)` emitidos por ambos os panels. `db_dir` na aba Configurações passa a ser read-only, derivado.

**Tech Stack:** PySide6 (GUI), LanceDB (vector store), pydantic-settings (config), pytest + pytest-qt (testes).

**Spec:** [docs/superpowers/specs/2026-04-21-corpus-rag-sync-design.md](../specs/2026-04-21-corpus-rag-sync-design.md)

---

## File Structure

**Files to modify:**

| Arquivo | Responsabilidade após mudança |
|---|---|
| `src/rag_maker/composition/container.py` | Adiciona método `rebind_to_corpus` ao dataclass `Container` |
| `src/rag_maker/adapters/driving/gui/main_window.py` | Orquestra a troca de corpus conectando signals dos dois panels |
| `src/rag_maker/adapters/driving/gui/widgets/corpus_panel.py` | Emite `corpus_change_requested`; expõe `reload_after_rebind` e `is_busy` |
| `src/rag_maker/adapters/driving/gui/widgets/settings_panel.py` | Emite `corpus_change_requested`; `db_dir` read-only; `reload_after_rebind` |
| `TODO.md` | Adiciona fase F8 documentando estas mudanças |

**Files to create:**

| Arquivo | Propósito |
|---|---|
| `tests/unit/test_container_rebind.py` | Cobertura do `rebind_to_corpus` |
| `tests/unit/test_main_window_corpus_change.py` | Cobertura do orquestrador (MainWindow slot) |
| `tests/integration/test_gui_corpus_switch.py` | E2E GUI via pytest-qt |

---

## Convenções do repo (leia antes)

- Testes seguem padrões de `tests/unit/test_container.py`: fakes locais implementando os ports, `pytest.fixture()` para construir container com `build_container(config_path=..., embedder=..., store=..., reranker=...)`.
- Marcadores: `@pytest.mark.unit()`, `@pytest.mark.integration()`, `@pytest.mark.e2e()`.
- Type checking é `mypy strict`. PEP 604 unions (`A | B`), `from __future__ import annotations` no topo de todos os arquivos.
- Linter: `ruff`. Line-length 100. Executar `uv run ruff check --fix` antes de commitar.
- Import linter: adapters nunca importam de outros adapters driving; application nunca importa de adapters. `src/rag_maker/composition/` pode importar de ambos.
- Commits: Conventional Commits (ex: `feat(gui):`, `fix(gui):`, `test:`, `docs:`).
- Rodar testes: `uv run pytest tests/unit/ -v` (rápido) ou `uv run pytest tests/ -v` (tudo).
- GUI usa PySide6. Signals definidos como class attributes: `my_signal = Signal(str)`.

---

## Task 1: `Container.rebind_to_corpus`

**Files:**
- Modify: `src/rag_maker/composition/container.py`
- Test: `tests/unit/test_container_rebind.py` (novo)

### Step 1.1: Criar arquivo de teste com fakes e fixtures

- [ ] **Step 1.1**

Crie `tests/unit/test_container_rebind.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rag_maker.composition.container import Container, build_container
from rag_maker.domain.models import RankedChunk, RetrievedChunk

_DIM = 4


class _FakeEmbedder:
    @property
    def dim(self) -> int:
        return _DIM

    def embed(self, text: str) -> tuple[float, ...]:
        return (0.1, 0.2, 0.3, 0.4)

    def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self.embed(t) for t in texts]


class _FakeStore:
    def __init__(self, db_path: Path | None = None, embedding_dim: int = _DIM) -> None:
        self.db_path = db_path
        self.embedding_dim = embedding_dim

    def upsert(self, chunks: list[Any]) -> None: ...
    def delete_by_source(self, source_path: str) -> None: ...
    def hybrid_search(self, vector: tuple[float, ...], text: str, top_n: int) -> list[RetrievedChunk]:
        return []
    def count(self) -> int:
        return 0
    def stats(self) -> dict[str, Any]:
        return {}
    def list_sources(self) -> dict[str, int]:
        return {}


class _FakeReranker:
    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RankedChunk]:
        return []


@pytest.fixture()
def cfg_file(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    corpus = tmp_path / "corpus_A"
    corpus.mkdir()
    cfg.write_text(f'[paths]\ncorpus_dir = "{corpus}"\ndb_dir = "{corpus / "rag"}"\n')
    return cfg


@pytest.fixture()
def container(cfg_file: Path, monkeypatch: pytest.MonkeyPatch) -> Container:
    # LanceVectorStore real é lento; substitui por FakeStore no build_container e no rebind
    from rag_maker.composition import container as container_mod
    monkeypatch.setattr(container_mod, "LanceVectorStore", _FakeStore)
    c = build_container(
        config_path=cfg_file,
        embedder=_FakeEmbedder(),
        store=_FakeStore(),
        reranker=_FakeReranker(),
    )
    # Garante embedding_dim na config mesmo quando store é injetado
    c.config = c.config.model_copy(update={"embedding_dim": _DIM})
    return c
```

- [ ] **Step 1.2: Escrever primeiro teste (troca válida retorna True)**

Adicione ao mesmo arquivo:

```python
@pytest.mark.unit()
def test_rebind_to_new_dir_returns_true_and_creates_rag(
    container: Container, tmp_path: Path
) -> None:
    new_corpus = tmp_path / "corpus_B"
    new_corpus.mkdir()

    changed = container.rebind_to_corpus(new_corpus)

    assert changed is True
    assert (new_corpus / "rag").is_dir()
```

- [ ] **Step 1.3: Rodar teste e confirmar que falha**

Execute:
```bash
uv run pytest tests/unit/test_container_rebind.py::test_rebind_to_new_dir_returns_true_and_creates_rag -v
```
Esperado: `AttributeError: 'Container' object has no attribute 'rebind_to_corpus'`.

- [ ] **Step 1.4: Implementar `rebind_to_corpus` no Container**

Abra `src/rag_maker/composition/container.py`. No topo do arquivo, adicione o import se ainda não existir:

```python
from rag_maker.adapters.driven.config.toml_loader import load_toml, save_toml
```
(já existe — confirme; apenas não duplique).

Logo após a definição do dataclass `Container` (depois do `query: QueryUseCase`), adicione o método:

```python
    def rebind_to_corpus(self, new_corpus_dir: Path) -> bool:
        """Aponta o container para um novo corpus.

        Cria `{new_corpus_dir}/rag` se não existir, reaproveita o banco
        existente se compatível, persiste os novos paths no TOML e substitui
        store + use cases. Embedder e reranker permanecem.

        Returns:
            True  se a troca foi efetivada.
            False se `new_corpus_dir` é igual ao corpus atual (no-op).

        Raises:
            ValueError: pasta não existe ou dim do banco existente é incompatível.
            PermissionError / OSError: falha ao criar `rag/`.
        """
        new_corpus_dir = new_corpus_dir.expanduser().resolve()
        if not new_corpus_dir.is_dir():
            raise ValueError(f"Pasta do corpus nao encontrada: {new_corpus_dir}")

        current = self.config.paths.corpus_dir
        if current is not None and current.expanduser().resolve() == new_corpus_dir:
            return False

        new_db_dir = new_corpus_dir / "rag"
        new_db_dir.mkdir(parents=True, exist_ok=True)

        current_dim = self.config.embedding_dim
        meta = _load_meta(new_db_dir)
        meta_dim = meta.get("embedding_dim")
        if meta_dim is not None and current_dim is not None and meta_dim != current_dim:
            raise ValueError(
                f"Banco em {new_db_dir} usa embedding dim={meta_dim}; "
                f"atual e {current_dim}. Escolha outra pasta ou reconstrua manualmente."
            )

        dim_for_store = current_dim or meta_dim
        if dim_for_store is None:
            raise ValueError(
                "Nenhuma embedding_dim conhecida; ingestao precisa ocorrer pelo menos uma vez."
            )

        new_store = LanceVectorStore(db_path=new_db_dir, embedding_dim=dim_for_store)

        set_config_value("paths.corpus_dir", str(new_corpus_dir))
        set_config_value("paths.db_dir", str(new_db_dir))

        new_config = AppConfig.from_file().model_copy(
            update={"embedding_dim": dim_for_store}
        )

        new_ingest = IngestUseCase(
            embedder=self.embedder,
            store=new_store,
            loader_for=_loader_for,
            config=new_config,
        )
        new_query = QueryUseCase(
            embedder=self.embedder,
            store=new_store,
            reranker=self.reranker,
            config=new_config,
        )

        self.config = new_config
        self.store = new_store
        self.ingest = new_ingest
        self.query = new_query
        return True
```

Observação: `set_config_value`, `_load_meta`, `LanceVectorStore`, `AppConfig`, `IngestUseCase`, `QueryUseCase` e `_loader_for` já estão importados no arquivo.

- [ ] **Step 1.5: Rodar teste e verificar que passa**

```bash
uv run pytest tests/unit/test_container_rebind.py::test_rebind_to_new_dir_returns_true_and_creates_rag -v
```
Esperado: PASS.

- [ ] **Step 1.6: Adicionar teste de no-op (path igual retorna False)**

Adicione ao arquivo de teste:

```python
@pytest.mark.unit()
def test_rebind_to_same_dir_returns_false(container: Container) -> None:
    current = container.config.paths.corpus_dir
    assert current is not None

    changed = container.rebind_to_corpus(current)

    assert changed is False
```

Rode:
```bash
uv run pytest tests/unit/test_container_rebind.py::test_rebind_to_same_dir_returns_false -v
```
Esperado: PASS.

- [ ] **Step 1.7: Adicionar teste de path inválido (ValueError)**

```python
@pytest.mark.unit()
def test_rebind_to_nonexistent_raises_value_error(
    container: Container, tmp_path: Path
) -> None:
    missing = tmp_path / "does_not_exist"

    with pytest.raises(ValueError, match="nao encontrada"):
        container.rebind_to_corpus(missing)
```

Rode:
```bash
uv run pytest tests/unit/test_container_rebind.py::test_rebind_to_nonexistent_raises_value_error -v
```
Esperado: PASS.

- [ ] **Step 1.8: Adicionar teste de dim incompatível**

```python
@pytest.mark.unit()
def test_rebind_with_incompatible_dim_raises(
    container: Container, tmp_path: Path
) -> None:
    new_corpus = tmp_path / "corpus_C"
    rag = new_corpus / "rag"
    rag.mkdir(parents=True)
    (rag / "meta.json").write_text(json.dumps({"embedding_dim": 9999}))

    original_store = container.store
    original_corpus = container.config.paths.corpus_dir

    with pytest.raises(ValueError, match="embedding dim"):
        container.rebind_to_corpus(new_corpus)

    # Estado do container permanece intacto
    assert container.store is original_store
    assert container.config.paths.corpus_dir == original_corpus
```

Rode:
```bash
uv run pytest tests/unit/test_container_rebind.py::test_rebind_with_incompatible_dim_raises -v
```
Esperado: PASS.

- [ ] **Step 1.9: Adicionar teste de preservação de embedding_dim**

```python
@pytest.mark.unit()
def test_rebind_preserves_embedding_dim(
    container: Container, tmp_path: Path
) -> None:
    new_corpus = tmp_path / "corpus_D"
    new_corpus.mkdir()

    container.rebind_to_corpus(new_corpus)

    assert container.config.embedding_dim == _DIM
```

Rode:
```bash
uv run pytest tests/unit/test_container_rebind.py::test_rebind_preserves_embedding_dim -v
```
Esperado: PASS.

- [ ] **Step 1.10: Adicionar teste de troca de store/ingest/query**

```python
@pytest.mark.unit()
def test_rebind_swaps_store_ingest_query(
    container: Container, tmp_path: Path
) -> None:
    old_store = container.store
    old_ingest = container.ingest
    old_query = container.query

    new_corpus = tmp_path / "corpus_E"
    new_corpus.mkdir()
    container.rebind_to_corpus(new_corpus)

    assert container.store is not old_store
    assert container.ingest is not old_ingest
    assert container.query is not old_query
    # Embedder e reranker permanecem (rebind parcial)
    assert container.ingest._embedder is container.embedder
    assert container.query._reranker is container.reranker
```

Rode:
```bash
uv run pytest tests/unit/test_container_rebind.py -v
```
Esperado: todos os 5 testes PASS.

- [ ] **Step 1.11: Quality gates**

```bash
uv run ruff check --fix src/rag_maker/composition/container.py tests/unit/test_container_rebind.py
uv run mypy src/rag_maker/composition/container.py
uv run lint-imports
```
Esperado: todos verdes.

- [ ] **Step 1.12: Commit**

```bash
git add src/rag_maker/composition/container.py tests/unit/test_container_rebind.py
git commit -m "feat(composition): Container.rebind_to_corpus troca corpus em runtime

Método idempotente que valida o novo path, cria rag/ se necessário,
checa compatibilidade de embedding_dim via meta.json, persiste os
paths no TOML e substitui store + use cases. Embedder e reranker
são preservados (rebind parcial)."
```

---

## Task 2: `CorpusPanel` — signal, `is_busy`, `reload_after_rebind`, editingFinished

**Files:**
- Modify: `src/rag_maker/adapters/driving/gui/widgets/corpus_panel.py`

Esta task não tem testes unitários isolados (é widget Qt; a cobertura vem via integration test na Task 5). Cada edit é pequeno e verificável visualmente na diff.

- [ ] **Step 2.1: Substituir signal `corpus_dir_changed` por `corpus_change_requested`**

Em `corpus_panel.py`, na classe `CorpusPanel` (linha ~75):

Substitua:
```python
    ingest_done            = Signal(object)   # IngestReport
    corpus_dir_changed     = Signal(str)      # novo caminho do corpus
    notification_requested = Signal(str, str) # title, message
```

Por:
```python
    ingest_done             = Signal(object)   # IngestReport
    corpus_change_requested = Signal(str)      # usuario selecionou novo corpus
    notification_requested  = Signal(str, str) # title, message
```

- [ ] **Step 2.2: Atualizar `_browse` para emitir intenção**

Em `_browse` (linha ~256), substitua:
```python
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta do corpus", start_dir)
        if folder:
            self._path_edit.setText(folder)
            set_config_value("paths.corpus_dir", folder)
            self._trigger_scan()
```

Por:
```python
        folder = QFileDialog.getExistingDirectory(self, "Selecionar pasta do corpus", start_dir)
        if folder:
            self.corpus_change_requested.emit(folder)
```

- [ ] **Step 2.3: Atualizar `_on_folder_dropped` para emitir intenção**

Em `_on_folder_dropped` (linha ~272), substitua:
```python
    def _on_folder_dropped(self, folder: str) -> None:
        set_config_value("paths.corpus_dir", folder)
        self._trigger_scan()
```

Por:
```python
    def _on_folder_dropped(self, folder: str) -> None:
        self.corpus_change_requested.emit(folder)
```

- [ ] **Step 2.4: Trocar `textChanged` por `editingFinished` no `_path_edit`**

Em `_build_ui` (linha ~113), remova:
```python
        self._path_edit.textChanged.connect(self.corpus_dir_changed)
```

Adicione no mesmo lugar:
```python
        self._path_edit.editingFinished.connect(
            lambda: self.corpus_change_requested.emit(self._path_edit.text().strip())
        )
```

- [ ] **Step 2.5: Adicionar `is_busy()`**

Adicione ao final da classe (antes do último método auxiliar):

```python
    def is_busy(self) -> bool:
        """True se há worker de ingest ou scan em execução."""
        ingest_running = self._ingest_worker is not None and self._ingest_worker.isRunning()
        scan_running = self._scan_worker is not None and self._scan_worker.isRunning()
        return ingest_running or scan_running
```

- [ ] **Step 2.6: Adicionar `reload_after_rebind()`**

Adicione logo após `is_busy`:

```python
    def reload_after_rebind(self) -> None:
        """Chamado pelo MainWindow após troca de corpus: atualiza campo,
        limpa tabela e re-scaneia.
        """
        new_path = str(self._container.config.paths.corpus_dir or "")
        self._path_edit.blockSignals(True)
        self._path_edit.setText(new_path)
        self._path_edit.blockSignals(False)
        self._file_table.setRowCount(0)
        self._summary_label.setText("—")
        self._log_append(f"Corpus trocado para: {new_path}")
        if new_path:
            self._trigger_scan()
```

- [ ] **Step 2.7: Remover import agora não usado**

Em `corpus_panel.py` topo (linha ~30):
```python
from rag_maker.composition.container import Container, set_config_value
```

`set_config_value` não é mais chamado diretamente aqui. Troque por:
```python
from rag_maker.composition.container import Container
```

Verifique que `set_config_value` não aparece mais em outro lugar do arquivo (ainda é usado em `_on_recursive_changed` — se sim, mantenha o import).

**Atenção**: se `set_config_value` ainda é usado em `_on_recursive_changed`, mantenha o import. Rodar:
```bash
grep -n set_config_value src/rag_maker/adapters/driving/gui/widgets/corpus_panel.py
```

- [ ] **Step 2.8: Verificar que o arquivo compila e testes existentes continuam passando**

```bash
uv run ruff check --fix src/rag_maker/adapters/driving/gui/widgets/corpus_panel.py
uv run mypy src/rag_maker/adapters/driving/gui/widgets/corpus_panel.py
uv run pytest tests/unit/ -v
```
Esperado: todos verdes. Testes unitários atuais passam.

- [ ] **Step 2.9: Commit**

```bash
git add src/rag_maker/adapters/driving/gui/widgets/corpus_panel.py
git commit -m "feat(gui): CorpusPanel emite corpus_change_requested

Substitui corpus_dir_changed (disparado a cada tecla) por
corpus_change_requested, emitido só no Enter/blur (editingFinished)
ou após seleção por dialog/drop. Adiciona is_busy() e
reload_after_rebind() para integração com o orquestrador."
```

---

## Task 3: `SettingsPanel` — signal, `db_dir` read-only, `_save` modificado, `reload_after_rebind`

**Files:**
- Modify: `src/rag_maker/adapters/driving/gui/widgets/settings_panel.py`

- [ ] **Step 3.1: Adicionar signal `corpus_change_requested`**

Em `settings_panel.py`, topo dos imports, garanta que `Signal` é importado:

Substitua:
```python
from PySide6.QtWidgets import (
    QFormLayout,
    ...
)
```

Adicione import do `Signal`:
```python
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    ...
)
```

Dentro da classe `SettingsPanel`, logo após `class SettingsPanel(QWidget):`, antes do `__init__`:

```python
    corpus_change_requested = Signal(str)
```

- [ ] **Step 3.2: Tornar `db_dir` read-only**

Em `_build_ui`, após `_add_str("DB dir", "paths.db_dir", ...)` (linha ~52):

Substitua o trecho:
```python
        _add_str("DB dir", "paths.db_dir", "~/.local/share/rag_maker/db")
```

Por:
```python
        _add_str("DB dir", "paths.db_dir", "~/.local/share/rag_maker/db")
        db_widget = self._fields["paths.db_dir"]
        if isinstance(db_widget, QLineEdit):
            db_widget.setReadOnly(True)
            db_widget.setToolTip(
                "Derivado automaticamente de {corpus_dir}/rag. "
                "Para trocar, altere a pasta do corpus."
            )
            db_widget.setStyleSheet("QLineEdit { background-color: palette(alternate-base); }")
```

- [ ] **Step 3.3: Modificar `_save` para emitir intenção em vez de salvar corpus_dir/db_dir**

Substitua o método `_save` completo (linha ~130) por:

```python
    def _save(self) -> None:
        try:
            new_corpus = self._fields["paths.corpus_dir"].text().strip() \
                if isinstance(self._fields.get("paths.corpus_dir"), QLineEdit) else ""
            for key, widget in self._fields.items():
                if key in ("paths.corpus_dir", "paths.db_dir"):
                    continue  # corpus_dir vai pelo orquestrador; db_dir e derivado
                value = (
                    str(widget.value()) if isinstance(widget, QSpinBox)
                    else widget.text().strip()
                )
                if value:
                    set_config_value(key, value)
            QMessageBox.information(self, "Configurações", "Salvo com sucesso.")

            current = str(self._config.paths.corpus_dir or "")
            if new_corpus and new_corpus != current:
                self.corpus_change_requested.emit(new_corpus)
        except Exception as exc:
            QMessageBox.critical(self, "Erro", str(exc))
```

- [ ] **Step 3.4: Adicionar `reload_after_rebind`**

Adicione ao final da classe, após `_save`:

```python
    def reload_after_rebind(self) -> None:
        """Chamado pelo MainWindow após troca de corpus: recarrega config do
        disco e repopula todos os campos (inclusive db_dir derivado).
        """
        try:
            self._config = AppConfig.from_file()
        except Exception:
            self._config = AppConfig()
        self._populate()
```

- [ ] **Step 3.5: Quality gates**

```bash
uv run ruff check --fix src/rag_maker/adapters/driving/gui/widgets/settings_panel.py
uv run mypy src/rag_maker/adapters/driving/gui/widgets/settings_panel.py
uv run pytest tests/unit/ -v
```
Esperado: verdes.

- [ ] **Step 3.6: Commit**

```bash
git add src/rag_maker/adapters/driving/gui/widgets/settings_panel.py
git commit -m "feat(gui): SettingsPanel com db_dir read-only e sinal de troca

Campo paths.db_dir agora e somente-leitura (sempre derivado como
corpus_dir/rag). _save ignora corpus_dir/db_dir e emite
corpus_change_requested quando o usuario muda o corpus, delegando
a transicao ao MainWindow. reload_after_rebind repopula os campos
apos a troca ser confirmada."
```

---

## Task 4: `MainWindow` — slot orquestrador + rewiring dos signals

**Files:**
- Modify: `src/rag_maker/adapters/driving/gui/main_window.py`
- Test: `tests/unit/test_main_window_corpus_change.py` (novo)

### Step 4.1: Teste primeiro — troca válida

- [ ] **Step 4.1**

Crie `tests/unit/test_main_window_corpus_change.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QWidget

from rag_maker.adapters.driving.gui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app  # type: ignore[return-value]


class _StubCorpusPanel(QWidget):
    """Stub que expõe os signals e métodos do CorpusPanel real sem lógica."""
    corpus_change_requested = Signal(str)
    ingest_done = Signal(object)
    notification_requested = Signal(str, str)

    def __init__(self, *_a: object, **_kw: object) -> None:
        super().__init__()
        self.reload_after_rebind = MagicMock()
        self._busy = False

    def is_busy(self) -> bool:
        return self._busy


class _StubSettingsPanel(QWidget):
    corpus_change_requested = Signal(str)

    def __init__(self, *_a: object, **_kw: object) -> None:
        super().__init__()
        self.reload_after_rebind = MagicMock()


class _StubQueryPanel(QWidget):
    def __init__(self, *_a: object, **_kw: object) -> None:
        super().__init__()


@pytest.fixture()
def container_mock(tmp_path: Path) -> MagicMock:
    c = MagicMock()
    c.config.paths.corpus_dir = tmp_path / "corpus"
    (tmp_path / "corpus").mkdir()
    c.config.paths.resolved_db_dir.return_value = tmp_path / "corpus" / "rag"
    c.config.ollama.url = "http://127.0.0.1:11434"
    return c


@pytest.fixture()
def window(
    qapp: QApplication,
    container_mock: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> MainWindow:
    # Substitui as classes dos panels antes de construir MainWindow
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.CorpusPanel", _StubCorpusPanel
    )
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.SettingsPanel", _StubSettingsPanel
    )
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.QueryPanel", _StubQueryPanel
    )
    # Evita I/O real no statusbar
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.get_store_stats",
        lambda _cfg: MagicMock(chunk_count=0, initialized=False, embedding_dim=None),
    )
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.ollama_is_running",
        lambda _cfg: False,
    )
    return MainWindow(container_mock)


@pytest.mark.unit()
def test_valid_change_calls_rebind_and_reloads(
    window: MainWindow, container_mock: MagicMock, tmp_path: Path
) -> None:
    new_corpus = tmp_path / "new_corpus"
    new_corpus.mkdir()
    container_mock.rebind_to_corpus.return_value = True

    window._on_corpus_change_requested(str(new_corpus))

    container_mock.rebind_to_corpus.assert_called_once_with(Path(str(new_corpus)))
    window._corpus_panel.reload_after_rebind.assert_called_once()  # type: ignore[attr-defined]
    window._settings_panel.reload_after_rebind.assert_called_once()  # type: ignore[attr-defined]
```

- [ ] **Step 4.2: Rodar — esperado FAIL (MainWindow não tem o slot)**

```bash
uv run pytest tests/unit/test_main_window_corpus_change.py::test_valid_change_calls_rebind_and_reloads -v
```
Esperado: AttributeError ou falha de construção.

- [ ] **Step 4.3: Implementar slot no MainWindow**

Em `src/rag_maker/adapters/driving/gui/main_window.py`, adicione o import no topo:

```python
from pathlib import Path

from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    ...
)
```
(adicione `QMessageBox` se não estiver lá e `from pathlib import Path`).

Na classe `MainWindow`, substitua o bloco `_build_ui` (trecho que conecta sinais) — localize:
```python
        self._corpus_panel.corpus_dir_changed.connect(self._settings_panel.set_corpus_dir)
```

Substitua por:
```python
        self._corpus_panel.corpus_change_requested.connect(self._on_corpus_change_requested)
        self._settings_panel.corpus_change_requested.connect(self._on_corpus_change_requested)
```

Adicione o método slot ao final da classe:

```python
    def _on_corpus_change_requested(self, new_path: str) -> None:
        """Orquestra a troca de corpus: valida busy, delega ao container,
        atualiza ambos os panels.
        """
        if self._corpus_panel.is_busy():
            QMessageBox.information(
                self,
                "Aguarde",
                "Aguarde a operação em andamento terminar antes de trocar de corpus.",
            )
            return

        try:
            changed = self._container.rebind_to_corpus(Path(new_path))
        except (ValueError, PermissionError, OSError) as exc:
            QMessageBox.critical(self, "Erro ao trocar corpus", str(exc))
            # Restaura campos para o valor real da config
            self._corpus_panel.reload_after_rebind()
            self._settings_panel.reload_after_rebind()
            return

        if changed:
            self._corpus_panel.reload_after_rebind()
            self._settings_panel.reload_after_rebind()
            self._refresh_status()
```

- [ ] **Step 4.4: Rodar teste — deve passar**

```bash
uv run pytest tests/unit/test_main_window_corpus_change.py::test_valid_change_calls_rebind_and_reloads -v
```
Esperado: PASS.

- [ ] **Step 4.5: Adicionar teste de no-op (rebind retorna False)**

Adicione ao arquivo de teste:

```python
@pytest.mark.unit()
def test_noop_change_skips_reloads(
    window: MainWindow, container_mock: MagicMock, tmp_path: Path
) -> None:
    same_corpus = tmp_path / "same"
    same_corpus.mkdir()
    container_mock.rebind_to_corpus.return_value = False

    window._on_corpus_change_requested(str(same_corpus))

    container_mock.rebind_to_corpus.assert_called_once()
    window._corpus_panel.reload_after_rebind.assert_not_called()  # type: ignore[attr-defined]
    window._settings_panel.reload_after_rebind.assert_not_called()  # type: ignore[attr-defined]
```

Rode:
```bash
uv run pytest tests/unit/test_main_window_corpus_change.py::test_noop_change_skips_reloads -v
```
Esperado: PASS.

- [ ] **Step 4.6: Adicionar teste de busy**

```python
@pytest.mark.unit()
def test_busy_blocks_rebind(
    window: MainWindow, container_mock: MagicMock, tmp_path: Path
) -> None:
    window._corpus_panel.is_busy.return_value = True
    target = tmp_path / "busy_target"
    target.mkdir()

    window._on_corpus_change_requested(str(target))

    container_mock.rebind_to_corpus.assert_not_called()
    window._corpus_panel.reload_after_rebind.assert_not_called()
```

Observação: `QMessageBox.information` abre um dialog modal. Em teste, isso pode bloquear. Use monkeypatch:

```python
@pytest.mark.unit()
def test_busy_blocks_rebind(
    window: MainWindow, container_mock: MagicMock, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.QMessageBox.information",
        lambda *a, **k: None,
    )
    window._corpus_panel._busy = True  # type: ignore[attr-defined]
    target = tmp_path / "busy_target"
    target.mkdir()

    window._on_corpus_change_requested(str(target))

    container_mock.rebind_to_corpus.assert_not_called()
    window._corpus_panel.reload_after_rebind.assert_not_called()  # type: ignore[attr-defined]
```

Rode:
```bash
uv run pytest tests/unit/test_main_window_corpus_change.py::test_busy_blocks_rebind -v
```
Esperado: PASS.

- [ ] **Step 4.7: Adicionar teste de erro (ValueError)**

```python
@pytest.mark.unit()
def test_value_error_shows_critical_and_restores(
    window: MainWindow, container_mock: MagicMock, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "rag_maker.adapters.driving.gui.main_window.QMessageBox.critical",
        lambda *a, **k: None,
    )
    container_mock.rebind_to_corpus.side_effect = ValueError("dim mismatch")

    window._on_corpus_change_requested(str(tmp_path / "x"))

    # reload_after_rebind foi chamado (restaurar campos), mas status nao
    window._corpus_panel.reload_after_rebind.assert_called_once()  # type: ignore[attr-defined]
    window._settings_panel.reload_after_rebind.assert_called_once()  # type: ignore[attr-defined]
```

Rode:
```bash
uv run pytest tests/unit/test_main_window_corpus_change.py -v
```
Esperado: todos os 4 testes PASS.

- [ ] **Step 4.8: Quality gates**

```bash
uv run ruff check --fix src/rag_maker/adapters/driving/gui/main_window.py tests/unit/test_main_window_corpus_change.py
uv run mypy src/rag_maker/adapters/driving/gui/main_window.py
uv run lint-imports
uv run pytest tests/unit/ -v
```
Esperado: verdes.

- [ ] **Step 4.9: Commit**

```bash
git add src/rag_maker/adapters/driving/gui/main_window.py tests/unit/test_main_window_corpus_change.py
git commit -m "feat(gui): MainWindow orquestra troca de corpus

Novo slot _on_corpus_change_requested e reescuta corpus_change_requested
dos dois panels. Checa busy, delega ao Container.rebind_to_corpus,
atualiza os panels so quando a troca foi efetivada. Em erro, mostra
dialog critico e restaura campos via reload_after_rebind."
```

---

## Task 5: Integration test (pytest-qt) — GUI completo

**Files:**
- Test: `tests/integration/test_gui_corpus_switch.py` (novo)

- [ ] **Step 5.1: Criar teste integrado**

Crie `tests/integration/test_gui_corpus_switch.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtWidgets import QApplication

from rag_maker.adapters.driving.gui.main_window import MainWindow
from rag_maker.composition.container import build_container
from rag_maker.domain.models import RankedChunk, RetrievedChunk

_DIM = 4


class _FakeEmbedder:
    @property
    def dim(self) -> int:
        return _DIM

    def embed(self, text: str) -> tuple[float, ...]:
        return (0.1, 0.2, 0.3, 0.4)

    def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self.embed(t) for t in texts]


class _FakeStore:
    def __init__(self, db_path: Path | None = None, embedding_dim: int = _DIM) -> None:
        self.db_path = db_path
        self.embedding_dim = embedding_dim

    def upsert(self, chunks: list[Any]) -> None: ...
    def delete_by_source(self, source_path: str) -> None: ...
    def hybrid_search(self, vector: tuple[float, ...], text: str, top_n: int) -> list[RetrievedChunk]:
        return []
    def count(self) -> int:
        return 0
    def stats(self) -> dict[str, Any]:
        return {}
    def list_sources(self) -> dict[str, int]:
        return {}


class _FakeReranker:
    def rerank(self, query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RankedChunk]:
        return []


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app  # type: ignore[return-value]


@pytest.mark.integration()
def test_corpus_switch_updates_config_and_panels(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rag_maker.composition import container as container_mod

    monkeypatch.setattr(container_mod, "LanceVectorStore", _FakeStore)

    corpus_a = tmp_path / "corpus_a"
    corpus_a.mkdir()
    corpus_b = tmp_path / "corpus_b"
    corpus_b.mkdir()

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[paths]\ncorpus_dir = "{corpus_a}"\n')

    # Aponta o XDG do TOML loader para o arquivo de teste
    monkeypatch.setattr(
        container_mod, "get_config_path", lambda *_: cfg_file
    )
    monkeypatch.setattr(
        "rag_maker.application.config._xdg_config_file", lambda: cfg_file
    )

    container = build_container(
        config_path=cfg_file,
        embedder=_FakeEmbedder(),
        store=_FakeStore(),
        reranker=_FakeReranker(),
    )
    container.config = container.config.model_copy(update={"embedding_dim": _DIM})

    window = MainWindow(container)

    # Dispara a troca pelo CorpusPanel
    window._corpus_panel.corpus_change_requested.emit(str(corpus_b))

    # Verifica que config foi persistida
    import tomllib
    with open(cfg_file, "rb") as f:
        data = tomllib.load(f)
    assert data["paths"]["corpus_dir"] == str(corpus_b.resolve())
    assert data["paths"]["db_dir"] == str((corpus_b / "rag").resolve())

    # Verifica que a pasta rag foi criada
    assert (corpus_b / "rag").is_dir()

    # Verifica que o container trocou
    assert container.config.paths.corpus_dir == corpus_b.resolve()

    # Verifica que o CorpusPanel refletiu a mudanca
    assert str(corpus_b) in window._corpus_panel._path_edit.text()
```

- [ ] **Step 5.2: Rodar o teste**

```bash
uv run pytest tests/integration/test_gui_corpus_switch.py -v
```
Esperado: PASS. Se falhar por causa de `QSystemTrayIcon` em CI headless, adicione no início do teste:
```python
from PySide6.QtCore import QCoreApplication
QCoreApplication.setAttribute(...)
```
Ou pule com `pytest.mark.skipif(not qt_platform_supports_tray, ...)`. Verifique a mensagem real antes de prescrever a correção.

- [ ] **Step 5.3: Quality gates**

```bash
uv run ruff check --fix tests/integration/test_gui_corpus_switch.py
uv run mypy tests/integration/test_gui_corpus_switch.py
```
Esperado: verde.

- [ ] **Step 5.4: Commit**

```bash
git add tests/integration/test_gui_corpus_switch.py
git commit -m "test(integration): troca de corpus atualiza TOML, rag/ e panels

Constroi MainWindow com container real (mas LanceVectorStore fakeado),
dispara corpus_change_requested e verifica que o TOML, a pasta rag/
e o texto do CorpusPanel foram todos atualizados."
```

---

## Task 6: Smoke test manual na GUI real

**Files:** nenhum (teste manual). Documentado aqui para o executor seguir.

- [ ] **Step 6.1: Rodar a GUI**

```bash
uv run rag-gui
```

- [ ] **Step 6.2: Verificar fluxo 1 (troca pela aba Corpus)**

1. Na aba **Corpus**, clique em "Selecionar…" e escolha uma pasta nova (`/tmp/test_corpus_a` — crie antes com `mkdir /tmp/test_corpus_a`).
2. Confirme que `/tmp/test_corpus_a/rag` foi criado automaticamente.
3. Vá para a aba **Configurações**: o campo "Corpus dir" deve mostrar `/tmp/test_corpus_a`; "DB dir" deve mostrar `/tmp/test_corpus_a/rag` em cinza (read-only).
4. Volte para **Corpus**: tabela de obras está limpa (ou vazia para pasta nova).
5. Crie outra pasta `/tmp/test_corpus_b`, selecione pela aba Corpus.
6. Confirme que tudo mudou (Configurações também).

- [ ] **Step 6.3: Verificar fluxo 2 (troca pela aba Configurações)**

1. Na aba **Configurações**, digite `/tmp/test_corpus_a` em "Corpus dir" e clique "Salvar configurações".
2. Confirme dialog "Salvo com sucesso".
3. Vá para **Corpus**: o campo deve refletir `/tmp/test_corpus_a`; a tabela foi limpa e re-scaneada.

- [ ] **Step 6.4: Verificar caso de erro (pasta inexistente)**

1. Em **Configurações**, digite `/nao/existe` em "Corpus dir" e salve.
2. Confirme: primeiro dialog "Salvo com sucesso" (campos normais salvos); segundo dialog crítico "Pasta do corpus nao encontrada".
3. Volte para **Corpus**: campo continua mostrando o corpus anterior válido.

- [ ] **Step 6.5: Verificar caso busy**

1. Em **Corpus**, selecione uma pasta com alguns PDFs.
2. Clique "Ingerir mudanças".
3. Durante a ingestão, tente trocar para outra pasta.
4. Deve aparecer dialog "Aguarde a operação em andamento terminar antes de trocar de corpus".

---

## Task 7: Atualizar `TODO.md` com fase F8

**Files:**
- Modify: `TODO.md`

- [ ] **Step 7.1: Adicionar linha da fase F8 na tabela resumo**

Em `TODO.md`, edit a tabela "Resumo por fase" para incluir uma linha F8 antes da linha "Total":

```
| F7 | Polimento + Distribuição | neutro | 7 | Média |
| F8 | Sincronização corpus↔rag GUI | Front/Mid | 7 | Média |
| **Total** | | | **93** | |
```

- [ ] **Step 7.2: Adicionar linhas na tabela de pendências**

Ao final da tabela de pendências, adicione:

```
| F8.1 | GUI/Composition | `Container.rebind_to_corpus(Path) -> bool` com testes unitários cobrindo no-op, path inválido, dim incompatível, preservação de embedding_dim | Alta | F7.7 | Média | ✅ Concluído | ✓ |
| F8.2 | GUI | `CorpusPanel`: signal `corpus_change_requested`, métodos `is_busy()` e `reload_after_rebind()`, `editingFinished` no lugar de `textChanged` | Alta | F8.1 | Média | ✅ Concluído | ✓ |
| F8.3 | GUI | `SettingsPanel`: signal `corpus_change_requested`, `db_dir` read-only, `_save` não grava corpus_dir/db_dir, `reload_after_rebind` | Alta | F8.1 | Média | ✅ Concluído | ✓ |
| F8.4 | GUI | `MainWindow._on_corpus_change_requested` orquestra via busy-check, rebind, reloads condicionais, error dialog com restore | Alta | F8.2, F8.3 | Média | ✅ Concluído | ✓ |
| F8.5 | Tests/Integration | `tests/integration/test_gui_corpus_switch.py` via pytest-qt: troca dispara update de TOML, criação de rag/, sync dos panels | Média | F8.4 | Média | ✅ Concluído | ✓ |
| F8.6 | QA | Smoke test manual dos 3 fluxos (Corpus, Configurações, erro) + busy-block | Média | F8.5 | Baixa | ✅ Concluído | ✓ |
| F8.7 | Docs | Atualizar `TODO.md` (esta fase) e garantir que `docs/superpowers/specs/` e `/plans/` estão commitados | Baixa | F8.6 | Baixa | ✅ Concluído | ✓ |
```

Observação: os status `✅ Concluído` só devem ser marcados após cada task completa. Durante a execução, mantenha `⏳ Em andamento` ou `⬜ Pendente`. Ajuste conforme progresso.

- [ ] **Step 7.3: Commit**

```bash
git add TODO.md
git commit -m "docs(todo): adiciona fase F8 (sincronizacao corpus<->rag na GUI)"
```

---

## Validação final

- [ ] **Step F.1: Rodar todos os testes**

```bash
uv run pytest tests/ -v
```
Esperado: todos passam.

- [ ] **Step F.2: Rodar todos os quality gates**

```bash
uv run ruff check
uv run mypy src/
uv run lint-imports
uv run bandit -r src/
uv run pytest --cov
```
Esperado: todos verdes, coverage ≥ 70%.

- [ ] **Step F.3: Verificar histórico limpo**

```bash
git log --oneline -10
```
Esperado: sequência clara de commits Conventional Commits, um por Task.
