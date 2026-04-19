from __future__ import annotations

import sys
import types

from PySide6.QtWidgets import QApplication, QMessageBox

from rag_maker.adapters.driving.gui.main_window import MainWindow
from rag_maker.composition.container import build_container


def _global_except_hook(
    exc_type: type,
    exc_value: BaseException,
    exc_tb: types.TracebackType | None,
) -> None:
    import traceback
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    QMessageBox.critical(None, "Erro inesperado", msg)
    sys.exit(1)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("rag-maker")
    app.setApplicationVersion("0.1.0")

    sys.excepthook = _global_except_hook

    try:
        container = build_container()
    except Exception as exc:
        QMessageBox.critical(None, "Erro de inicialização", str(exc))
        sys.exit(1)

    window = MainWindow(container)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
