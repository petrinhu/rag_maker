from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rag_maker.application.config import AppConfig
from rag_maker.composition.container import detect_ollama_url, get_config_path, set_config_value


class SettingsPanel(QWidget):
    corpus_change_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fields: dict[str, QLineEdit | QSpinBox] = {}
        try:
            self._config = AppConfig.from_file()
        except Exception:
            self._config = AppConfig()
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)

        def _add_str(label: str, key: str, placeholder: str = "") -> None:
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            self._fields[key] = edit
            form.addRow(label, edit)

        def _add_int(label: str, key: str, min_v: int, max_v: int) -> None:
            spin = QSpinBox()
            spin.setRange(min_v, max_v)
            self._fields[key] = spin
            form.addRow(label, spin)

        form.addRow(QLabel("<b>Paths</b>"))
        _add_str("Corpus dir", "paths.corpus_dir", "/caminho/para/corpus")
        _add_str("DB dir", "paths.db_dir", "~/.local/share/rag_maker/db")
        db_widget = self._fields["paths.db_dir"]
        if isinstance(db_widget, QLineEdit):
            db_widget.setReadOnly(True)
            db_widget.setToolTip(
                "Derivado automaticamente de {corpus_dir}/rag. "
                "Para trocar, altere a pasta do corpus."
            )
            db_widget.setStyleSheet("QLineEdit { background-color: palette(alternate-base); }")

        form.addRow(QLabel("<b>Ollama</b>"))
        # URL com botão de auto-detecção
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("http://127.0.0.1:11434")
        self._fields["ollama.url"] = url_edit
        detect_btn = QPushButton("Detectar")
        detect_btn.setFixedWidth(80)
        detect_btn.clicked.connect(self._detect_url)
        url_row = QHBoxLayout()
        url_row.addWidget(url_edit)
        url_row.addWidget(detect_btn)
        form.addRow("URL", url_row)

        _add_str("Modelo de embedding", "ollama.embedding_model", "bge-m3:latest")
        _add_int("Timeout (s)", "ollama.timeout_seconds", 10, 600)

        form.addRow(QLabel("<b>Chunking</b>"))
        _add_int("Tamanho do chunk", "chunking.size", 100, 5000)
        _add_int("Overlap", "chunking.overlap", 0, 500)

        form.addRow(QLabel("<b>Retrieval</b>"))
        _add_int("Coarse top-N", "retrieval.coarse_top_n", 10, 500)
        _add_int("Rerank top-K", "retrieval.rerank_top_k", 1, 50)

        form.addRow(QLabel("<b>Reranker</b>"))
        _add_str("Modelo", "reranker.model", "BAAI/bge-reranker-v2-m3")
        _add_str("Device", "reranker.device", "auto")

        scroll.setWidget(content)
        outer.addWidget(scroll)

        save_btn = QPushButton("Salvar configurações")
        save_btn.clicked.connect(self._save)
        outer.addWidget(save_btn)

        cfg_path_label = QLabel(f"Config: {get_config_path()}")
        cfg_path_label.setWordWrap(True)
        outer.addWidget(cfg_path_label)

    def _populate(self) -> None:
        cfg = self._config
        str_map: dict[str, str] = {
            "paths.corpus_dir": str(cfg.paths.corpus_dir) if cfg.paths.corpus_dir else "",
            "paths.db_dir": str(cfg.paths.resolved_db_dir()),
            "ollama.url": detect_ollama_url(),
            "ollama.embedding_model": cfg.ollama.embedding_model,
            "reranker.model": cfg.reranker.model,
            "reranker.device": cfg.reranker.device,
        }
        int_map: dict[str, int] = {
            "ollama.timeout_seconds": cfg.ollama.timeout_seconds,
            "chunking.size": cfg.chunking.size,
            "chunking.overlap": cfg.chunking.overlap,
            "retrieval.coarse_top_n": cfg.retrieval.coarse_top_n,
            "retrieval.rerank_top_k": cfg.retrieval.rerank_top_k,
        }
        for key, str_val in str_map.items():
            widget = self._fields.get(key)
            if isinstance(widget, QLineEdit):
                widget.setText(str_val)
        for key, int_val in int_map.items():
            widget = self._fields.get(key)
            if isinstance(widget, QSpinBox):
                widget.setValue(int_val)

    def _detect_url(self) -> None:
        url = detect_ollama_url()
        widget = self._fields.get("ollama.url")
        if isinstance(widget, QLineEdit):
            widget.setText(url)

    def set_corpus_dir(self, path: str) -> None:
        widget = self._fields.get("paths.corpus_dir")
        if isinstance(widget, QLineEdit) and path:
            widget.setText(path)

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

    def reload_after_rebind(self) -> None:
        """Chamado pelo MainWindow após troca de corpus: recarrega config do
        disco e repopula todos os campos (inclusive db_dir derivado).
        """
        try:
            self._config = AppConfig.from_file()
        except Exception:
            self._config = AppConfig()
        self._populate()
