from __future__ import annotations

import os
import sys
import types

import darkdetect
from PySide6.QtGui import QColor, QPalette
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


def _apply_fusion_dark(app: QApplication) -> None:
    """Paleta Fusion escura — fallback quando o plugin de tema do sistema não carrega."""
    app.setStyle("Fusion")
    c = QColor
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Window, c(53, 53, 53))
    dark.setColor(QPalette.ColorRole.WindowText, c(255, 255, 255))
    dark.setColor(QPalette.ColorRole.Base, c(35, 35, 35))
    dark.setColor(QPalette.ColorRole.AlternateBase, c(53, 53, 53))
    dark.setColor(QPalette.ColorRole.ToolTipBase, c(25, 25, 25))
    dark.setColor(QPalette.ColorRole.ToolTipText, c(255, 255, 255))
    dark.setColor(QPalette.ColorRole.Text, c(255, 255, 255))
    dark.setColor(QPalette.ColorRole.Button, c(53, 53, 53))
    dark.setColor(QPalette.ColorRole.ButtonText, c(255, 255, 255))
    dark.setColor(QPalette.ColorRole.BrightText, c(255, 0, 0))
    dark.setColor(QPalette.ColorRole.Link, c(42, 130, 218))
    dark.setColor(QPalette.ColorRole.Highlight, c(42, 130, 218))
    dark.setColor(QPalette.ColorRole.HighlightedText, c(35, 35, 35))
    for role in (
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
    ):
        dark.setColor(QPalette.ColorGroup.Disabled, role, c(128, 128, 128))
    app.setPalette(dark)


def _fix_dark_mode_if_needed(app: QApplication) -> None:
    """Aplica Fusion dark se o sistema quer dark mas o Qt carregou tema claro."""
    if not darkdetect.isDark():
        return
    bg = app.palette().color(QPalette.ColorRole.Window)
    luminance = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
    if luminance >= 128:
        _apply_fusion_dark(app)


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
    import logging

    logging.getLogger("pypdf").setLevel(logging.ERROR)

    _ensure_platform_theme()
    app = QApplication(sys.argv)
    app.setApplicationName("rag-maker")
    app.setApplicationVersion("0.1.0")
    _fix_dark_mode_if_needed(app)

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
