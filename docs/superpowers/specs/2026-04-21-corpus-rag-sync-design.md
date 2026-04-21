# Sincronização automática corpus ↔ rag na GUI

**Data:** 2026-04-21
**Escopo:** `adapters/driving/gui/*` + `composition/container.py`
**Tipo:** modificação de comportamento (GUI + camada de composição)

## Contexto

Hoje, na GUI, `paths.corpus_dir` e `paths.db_dir` são independentes. O usuário pode trocar o corpus na aba **Corpus** (via botão "Selecionar…" ou drag-and-drop) e, em paralelo, editar `paths.db_dir` à mão na aba **Configurações**. As duas abas não se sincronizam de forma estruturada: existe apenas um `corpus_dir_changed` que dispara a cada tecla digitada no campo, sem rebind do `Container` — ou seja, o `LanceVectorStore` em memória continua apontando para o db_dir antigo mesmo após o usuário trocar a pasta.

A regra pedida é simples: **a pasta do rag é sempre filha direta da pasta do corpus** (`{corpus_dir}/rag`). Trocar o corpus em qualquer uma das abas deve:

1. Criar `{corpus_dir}/rag` se não existir;
2. Reutilizar o banco existente se já existir (não destruir dados);
3. Persistir ambos os paths na config TOML;
4. Fazer o `Container` apontar para o novo store (rebind);
5. Limpar a tabela de obras na aba **Corpus** e re-scannear;
6. Atualizar a aba **Configurações** para refletir os novos paths.

## Decisões tomadas

| Pergunta | Decisão |
|---|---|
| O que acontece com o banco vetorial do rag existente ao trocar de pasta? | **Preservar** (opção *a*). Nada é destruído; só a tabela da GUI é limpa e recarregada pelo scan. |
| Como tratar `db_dir` na aba Configurações? | **Somente-leitura** (opção *b*), sempre derivado como `{corpus_dir}/rag`. |
| Como refletir a mudança no `Container`? | **Rebind parcial** (opção *b*) — troca `store`, `ingest`, `query`; mantém `embedder` e `reranker`. |
| Onde vive a lógica de transição? | **MainWindow coordena** (abordagem *A*). Panels emitem intenção; MainWindow chama `Container.rebind_to_corpus()` e notifica os panels. |

## Arquitetura

### Componente 1 — `Container.rebind_to_corpus(new_corpus_dir: Path)`

Novo método em `src/rag_maker/composition/container.py`. Responsabilidade única: transicionar o Container e a config para apontarem ao novo corpus, de forma atômica.

**Assinatura:**

```python
def rebind_to_corpus(self, new_corpus_dir: Path) -> bool
```

Retorna `True` se a troca foi efetivada, `False` se foi no-op (path igual ao atual).

**Passos, em ordem de execução atômica** — se qualquer passo antes da persistência falhar, config e Container ficam intactos:

1. Normaliza: `new_corpus_dir = new_corpus_dir.expanduser().resolve()`.
2. Se `not new_corpus_dir.is_dir()` → `ValueError("Pasta do corpus não encontrada: {path}")`.
3. Se `self.config.paths.corpus_dir` não é `None` e `self.config.paths.corpus_dir.resolve() == new_corpus_dir` → `return False` (no-op).
4. Calcula `new_db_dir = new_corpus_dir / "rag"`.
5. `new_db_dir.mkdir(parents=True, exist_ok=True)` — pode levantar `PermissionError`, propagado ao chamador.
6. Lê `meta.json` do `new_db_dir` (se existir). Se tem `embedding_dim` e difere do `self.config.embedding_dim` → `ValueError("Banco em {path} usa embedding dim={N}; atual é {M}. Escolha outra pasta ou reconstrua manualmente.")`.
7. Constrói `new_store = LanceVectorStore(db_path=new_db_dir, embedding_dim=self.config.embedding_dim)` — **antes** de tocar a config. Se falhar, config intocada.
8. Só agora persiste: `set_config_value("paths.corpus_dir", str(new_corpus_dir))` e `set_config_value("paths.db_dir", str(new_db_dir))`.
9. `new_config = AppConfig.from_file()` (`embedding_dim` é preservado manualmente: `new_config = new_config.model_copy(update={"embedding_dim": self.config.embedding_dim})`).
10. Constrói novos `IngestUseCase` e `QueryUseCase` com `new_store` + embedder/reranker atuais + `new_config`.
11. Atribui in-place: `self.config = new_config`, `self.store = new_store`, `self.ingest = new_ingest`, `self.query = new_query`.
12. `return True`.

**Por quê pré-validar `embedding_dim`:** se o destino já foi criado com outro modelo de embedding (outra dim), instanciar `LanceVectorStore` com dim errada levaria a crashes em leitura/escrita. Falhar cedo com mensagem clara é mais seguro.

**Por quê preservar `embedding_dim` manualmente no passo 9:** `AppConfig.from_file` relê do TOML, que não armazena `embedding_dim` (é derivado em runtime). Sem o `model_copy`, perderíamos a dim após o rebind.

### Componente 2 — `MainWindow` como orquestrador

Em `src/rag_maker/adapters/driving/gui/main_window.py`:

- Remove `self._corpus_panel.corpus_dir_changed.connect(self._settings_panel.set_corpus_dir)` (não existe mais).
- Conecta `corpus_change_requested` de **ambos** os panels ao slot `_on_corpus_change_requested(new_path: str)`.

**Slot `_on_corpus_change_requested(new_path: str)`:**

```
1. Se self._corpus_panel.is_busy() → QMessageBox.information("Aguarde a operação em andamento terminar antes de trocar de corpus.") e retorna
2. try:
       changed = self._container.rebind_to_corpus(Path(new_path))
   except (ValueError, PermissionError, OSError) as exc:
       QMessageBox.critical(str(exc))
       # garante que a UI volte ao path real (desfaz texto inválido digitado):
       self._corpus_panel.reload_after_rebind()
       self._settings_panel.reload_after_rebind()
       retorna
3. Se changed:
       self._corpus_panel.reload_after_rebind()
       self._settings_panel.reload_after_rebind()
       self._refresh_status()
```

O `Container.rebind_to_corpus` é a fonte de verdade: ele valida (`is_dir`, dim compatível), detecta no-op e retorna `False` nesse caso. O MainWindow só faz o check de busy (que é estado da UI, fora do Container) e orquestra os reloads. Em caso de erro, também chama `reload_after_rebind` para restaurar os campos ao valor real da config (que não foi alterada).

### Componente 3 — `SettingsPanel`

Em `src/rag_maker/adapters/driving/gui/widgets/settings_panel.py`:

- Novo Signal: `corpus_change_requested = Signal(str)`.
- Campo `paths.db_dir`: `setReadOnly(True)`, tooltip `"Derivado automaticamente de {corpus_dir}/rag"`, e estilo (propriedade Qt) indicando não-editável.
- `_save()` modificado:
  - Lê `new_corpus = self._fields["paths.corpus_dir"].text().strip()`.
  - Salva **todos os outros campos** via `set_config_value` como hoje, **exceto** `paths.corpus_dir` e `paths.db_dir` (esses passam pelo orquestrador).
  - Exibe `QMessageBox.information("Salvo com sucesso.")` (mensagem cobre os campos salvos localmente).
  - Se `new_corpus` difere de `str(self._config.paths.corpus_dir or "")`:
    - Emite `self.corpus_change_requested.emit(new_corpus)`.
    - Eventual erro na troca é mostrado pelo MainWindow como um segundo diálogo (crítico), sobre o diálogo de sucesso já fechado.
- Novo método `reload_after_rebind()`:
  - `self._config = AppConfig.from_file()`.
  - `self._populate()` (já existe — repopula todos os campos).

### Componente 4 — `CorpusPanel`

Em `src/rag_maker/adapters/driving/gui/widgets/corpus_panel.py`:

- Novo Signal: `corpus_change_requested = Signal(str)`.
- Remove Signal `corpus_dir_changed` (deixa de ser usado; a `MainWindow` não o ouve mais).
- `_browse()`: trocar
  ```python
  self._path_edit.setText(folder)
  set_config_value("paths.corpus_dir", folder)
  self._trigger_scan()
  ```
  por:
  ```python
  self.corpus_change_requested.emit(folder)
  ```
  (A atualização do campo e o scan vêm via `reload_after_rebind()`.)
- `_on_folder_dropped(folder)`: igual — apenas emite `corpus_change_requested.emit(folder)`.
- Conexão do campo de texto: remove `self._path_edit.textChanged.connect(self.corpus_dir_changed)` (fire por tecla); adiciona `self._path_edit.editingFinished.connect(lambda: self.corpus_change_requested.emit(self._path_edit.text().strip()))` (fire só no Enter/blur).
- Novo método `reload_after_rebind()`:
  ```python
  new_path = str(self._container.config.paths.corpus_dir or "")
  self._path_edit.blockSignals(True)
  self._path_edit.setText(new_path)
  self._path_edit.blockSignals(False)
  self._file_table.setRowCount(0)
  self._summary_label.setText("—")
  self._trigger_scan()
  ```
- Novo método `is_busy() -> bool`:
  ```python
  return (
      (self._ingest_worker is not None and self._ingest_worker.isRunning())
      or (self._scan_worker is not None and self._scan_worker.isRunning())
  )
  ```

## Fluxos

### Fluxo 1 — Usuário troca corpus pela aba **Corpus** (botão Selecionar)

```
Usuário clica "Selecionar…"
 → QFileDialog devolve /novo/corpus
 → CorpusPanel emite corpus_change_requested("/novo/corpus")
 → MainWindow._on_corpus_change_requested:
     - checa is_busy() → False
     - checa is_dir() → True
     - Container.rebind_to_corpus(Path("/novo/corpus")):
         - cria /novo/corpus/rag (se não existe)
         - pré-checa meta.json (dim ok)
         - cria novo LanceVectorStore
         - grava paths.corpus_dir e paths.db_dir no TOML
         - recarrega AppConfig
         - substitui self.store, self.ingest, self.query
     - CorpusPanel.reload_after_rebind():
         - atualiza _path_edit (signals bloqueados)
         - limpa tabela
         - dispara scan
     - SettingsPanel.reload_after_rebind():
         - recarrega AppConfig
         - repopula campos (corpus_dir e db_dir atualizados)
     - MainWindow._refresh_status():
         - atualiza contador de chunks no statusbar a partir do novo store
```

### Fluxo 2 — Usuário troca corpus pela aba **Configurações**

```
Usuário edita campo "Corpus dir" → clica "Salvar configurações"
 → SettingsPanel._save():
     - salva chunking/retrieval/ollama/reranker normalmente
     - detecta mudança em corpus_dir
     - emite corpus_change_requested(new_value)
     - exibe "Salvo com sucesso"
 → MainWindow._on_corpus_change_requested: (mesmo fluxo acima)
 → CorpusPanel.reload_after_rebind() → aba Corpus agora mostra a nova pasta e scaneia
```

### Fluxo 3 — Usuário arrasta pasta para o campo da aba Corpus

```
Drop em _DroppableLineEdit
 → _on_folder_dropped(folder)
 → CorpusPanel emite corpus_change_requested(folder)
 → (resto idêntico ao fluxo 1)
```

## Casos de borda

| Situação | Tratamento |
|---|---|
| Pasta nova não existe / não é diretório | `Container.rebind_to_corpus` levanta `ValueError` → MainWindow: `QMessageBox.critical`, nada é alterado |
| Pasta igual à atual | `Container.rebind_to_corpus` retorna `False` → MainWindow pula reloads |
| `mkdir(new/rag)` falha (permissão) | `PermissionError` propaga → MainWindow: `QMessageBox.critical`, config intocada |
| Worker de ingest ou scan em execução | MainWindow detecta via `is_busy()`: bloqueia com `QMessageBox.information` |
| `meta.json` do novo rag tem `embedding_dim` diferente | `ValueError` claro; config e store atual intocados |
| Nenhum corpus configurado → primeira definição | `self.config.paths.corpus_dir is None` → step 3 não entra no no-op → transição normal |
| `meta.json` ausente e rag vazio | Usa `embedding_dim` atual; LanceDB cria tabela no primeiro upsert |
| Usuário digita caminho e aperta Tab/Enter | `editingFinished` dispara uma vez — transição normal |
| Usuário digita caminho parcial inválido e troca foco | `editingFinished` dispara; `rebind_to_corpus` levanta `ValueError`; MainWindow mostra dialog crítico **e** chama `reload_after_rebind` para restaurar o campo ao valor real da config |

## Testes

### Unit (mockando Container)

- `tests/unit/test_main_window_corpus_change.py`:
  - Troca válida (`rebind_to_corpus` retorna `True`): MainWindow invoca `reload_after_rebind` em ambos os panels e `_refresh_status`.
  - Troca no-op (`rebind_to_corpus` retorna `False`): MainWindow **não** invoca `reload_after_rebind`.
  - Busy: `corpus_panel.is_busy() == True` → MainWindow não chama `rebind_to_corpus`.
  - `rebind_to_corpus` levanta `ValueError` / `PermissionError` / `OSError`: MainWindow mostra dialog crítico e não chama `reload_after_rebind`.

- `tests/unit/test_container_rebind.py`:
  - Rebind para novo path retorna `True`, cria `rag/`, atualiza config, substitui store/ingest/query.
  - Rebind para path igual ao atual retorna `False`; config e atributos intactos.
  - Rebind para path inválido → `ValueError`; config intacta.
  - Rebind com `meta.json` de dim incompatível → `ValueError`; config intacta; `self.store` antigo intacto.
  - Rebind preserva `embedding_dim` na nova config (não é zerada pelo reload do TOML).

### Integration

- `tests/integration/test_gui_corpus_switch.py` (pytest-qt):
  - Constrói MainWindow com container real (com fakes de embedder/reranker via `build_container` overrides).
  - Dispara `corpus_change_requested` via CorpusPanel.
  - Verifica: TOML foi atualizado; `rag/` foi criado; tabela da CorpusPanel foi limpa; SettingsPanel reflete novos paths; statusbar atualizado.

## Fora do escopo

- Migração automática de dados entre rag antigos com dims diferentes (usuário faz manualmente).
- Suporte a múltiplos corpus simultâneos (um só por vez, como hoje).
- Opção "confirmar antes de trocar" — troca é imediata; usuário pode voltar escolhendo a pasta antiga.
- CLI não muda nesta spec (ela já carrega config fresca a cada execução).

## Arquivos a modificar

| Arquivo | Alteração |
|---|---|
| `src/rag_maker/composition/container.py` | Adicionar método `rebind_to_corpus` |
| `src/rag_maker/adapters/driving/gui/main_window.py` | Slot `_on_corpus_change_requested`; reconexão de sinais |
| `src/rag_maker/adapters/driving/gui/widgets/corpus_panel.py` | Signal `corpus_change_requested`; remoção de `corpus_dir_changed`; métodos `reload_after_rebind` e `is_busy`; `editingFinished` no lugar de `textChanged` |
| `src/rag_maker/adapters/driving/gui/widgets/settings_panel.py` | Signal `corpus_change_requested`; `db_dir` read-only; `_save` modificado; método `reload_after_rebind` |

## Arquivos a criar

| Arquivo | Propósito |
|---|---|
| `tests/unit/test_container_rebind.py` | Cobertura do método `rebind_to_corpus` |
| `tests/unit/test_main_window_corpus_change.py` | Cobertura do orquestrador |
| `tests/integration/test_gui_corpus_switch.py` | E2E na GUI com container real |

## Pendências no TODO.md

Esta mudança é pós-F7.7 (v0.1.0 já tag-ada). Adicionar nova fase F8 no `TODO.md` com estas tarefas antes da execução.
