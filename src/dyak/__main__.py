"""Точка входа модуля: `python -m dyak`."""

from __future__ import annotations

from dyak.cli import app, configure_stdio

if __name__ == '__main__':
    configure_stdio()  # UTF-8 stdout при запуске ядра из GUI (T023)
    app()
