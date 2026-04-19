from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rag_maker.composition.container import get_config_path, set_config_value


class SettingsPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fields: dict[str, QLineEdit | QSpinBox] = {}
        self._build_ui()

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

        form.addRow(QLabel("<b>Ollama</b>"))
        _add_str("URL", "ollama.url", "http://127.0.0.1:11434")
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

    def _save(self) -> None:
        try:
            for key, widget in self._fields.items():
                value = str(widget.value()) if isinstance(widget, QSpinBox) else widget.text().strip()
                if value:
                    set_config_value(key, value)
            QMessageBox.information(self, "Configurações", "Salvo com sucesso.")
        except Exception as exc:
            QMessageBox.critical(self, "Erro", str(exc))
