"""Точка входа GUI dyak: создание `QApplication` и главного окна."""

from __future__ import annotations

import sys
from importlib import resources

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from dyak.gui.main_window import MainWindow


def load_app_icon() -> QIcon:
    """Иконка приложения из package-data (работает из исходников и бандла T010)."""
    data = resources.files('dyak.gui').joinpath('assets', 'icon.png').read_bytes()
    pixmap = QPixmap()
    pixmap.loadFromData(data)
    return QIcon(pixmap)


def main() -> int:
    """Запустить оконное приложение dyak; вернуть код возврата Qt event-loop."""
    app = QApplication(sys.argv)
    app.setApplicationName('Дьяк')
    app.setWindowIcon(load_app_icon())
    window = MainWindow()
    window.show()
    return app.exec()
