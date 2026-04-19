from __future__ import annotations

import os
import sys
import types

from PySide6.QtWidgets import QApplication, QMessageBox

from rag_maker.adapters.driving.gui.main_window import MainWindow
from rag_maker.composition.container import build_container


def _ensure_platform_theme() -> None:
    """Define QT_QPA_PLATFORMTHEME se não estiver no ambiente (binário instalado)."""
    if "QT_QPA_PLATFORMTHEME" in os.environ:
        return
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "KDE" in desktop:
        os.environ["QT_QPA_PLATFORMTHEME"] = "kde"
    elif any(d in desktop for d in ("GNOME", "UNITY", "BUDGIE", "CINNAMON")):
        os.environ["QT_QPA_PLATFORMTHEME"] = "gnome"


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
    _ensure_platform_theme()
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
