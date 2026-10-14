"""Application bootstrap for Atari 8-bit Scene Editor."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    """Run the Atari 8-bit Scene Editor desktop application."""
    if argv is None:
        argv = sys.argv

    if any(arg in ("--help", "-h") for arg in argv[1:]):
        print(
            "Usage: atari-scene-editor [scene_file.json]\n"
            "   or: python atari-scene-editor/main.py [scene_file.json]\n\n"
            "Atari 8-bit Scene Editor (PySide6)\n"
            "Desktop application for designing 160x96 pixel platformer screens."
        )
        return 0

    # Ensure consistent styling across platforms
    app = QApplication.instance()
    if app is None:
        app = QApplication(argv)

    app.setApplicationName("atari-scene-editor")
    app.setApplicationDisplayName("Atari 8-bit Scene Editor")
    app.setOrganizationName("Atari Retro Studio")

    # Dark theme stylesheet for professional retro pixel tooling
    dark_stylesheet = """
    QMainWindow {
        background-color: #1e1e24;
    }
    QWidget {
        color: #e0e0e0;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-size: 12px;
    }
    QDockWidget {
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
        background-color: #24242c;
    }
    QDockWidget::title {
        background-color: #2b2b35;
        padding: 6px;
        font-weight: bold;
    }
    QGroupBox {
        border: 1px solid #3d3d4d;
        border-radius: 4px;
        margin-top: 12px;
        padding-top: 12px;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 4px;
        color: #79a8d9;
    }
    QToolBar {
        background-color: #24242c;
        border-bottom: 1px solid #363644;
        spacing: 4px;
        padding: 2px;
    }
    QMenuBar {
        background-color: #24242c;
        border-bottom: 1px solid #363644;
    }
    QMenuBar::item:selected {
        background-color: #3d3d4d;
    }
    QMenu {
        background-color: #24242c;
        border: 1px solid #3d3d4d;
    }
    QMenu::item:selected {
        background-color: #0e70a0;
    }
    QListWidget {
        background-color: #16161b;
        border: 1px solid #363644;
        border-radius: 4px;
    }
    QListWidget::item:selected {
        background-color: #0e70a0;
        color: white;
    }
    QListWidget::item:hover {
        background-color: #2a2a38;
    }
    QLineEdit, QSpinBox {
        background-color: #16161b;
        border: 1px solid #3d3d4d;
        border-radius: 3px;
        padding: 4px;
        color: white;
    }
    QLineEdit:focus, QSpinBox:focus {
        border: 1px solid #0e70a0;
    }
    QPushButton {
        background-color: #363644;
        border: 1px solid #4a4a5d;
        border-radius: 3px;
        padding: 4px 8px;
        color: #eee;
    }
    QPushButton:hover {
        background-color: #444458;
    }
    QPushButton:pressed {
        background-color: #24242c;
    }
    QStatusBar {
        background-color: #18181f;
        border-top: 1px solid #2e2e3a;
        color: #888;
    }
    QScrollBar:vertical, QScrollBar:horizontal {
        background-color: #16161b;
        border: none;
    }
    QScrollBar::handle {
        background-color: #3d3d4d;
        border-radius: 3px;
    }
    QScrollBar::handle:hover {
        background-color: #55556b;
    }
    """
    app.setStyleSheet(dark_stylesheet)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
