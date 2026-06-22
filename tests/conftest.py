"""Общие фикстуры тестов dyak.

GUI-тесты (T008) гоняют Qt без дисплея: платформа `offscreen` ставится до
создания `QApplication`. Фикстура `qapp` даёт единственный экземпляр
приложения на сессию (Qt не допускает второй).
"""

from __future__ import annotations

import os

import pytest
from PySide6.QtWidgets import QApplication

# Платформа Qt без дисплея — ставится до СОЗДАНИЯ QApplication (в фикстуре),
# а не до импорта: плагин платформы грузится при инстанцировании, не при import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
