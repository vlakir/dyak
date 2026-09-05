"""
Доменные исключения «Дьяка» — то, что не уехало в `chancellery` (T033).

Иерархия ошибок движка (`TableError`, `TemplateError`, `ReverseError` и
прочие) живёт теперь в библиотеке и наследует `ChancelleryError`.
Здесь остаются ошибки самого приложения, и их корень `DyakError`
подвешен под библиотечный — тогда один `except ChancelleryError` в CLI
ловит оба слоя: и сбой движка, и сбой приложения.
"""

from __future__ import annotations

from chancellery import ChancelleryError


class DyakError(ChancelleryError):
    """Базовое исключение приложения «Дьяк» (PDF, scaffold, CLI)."""


class PdfExportError(DyakError):
    """Ошибка экспорта в PDF (LibreOffice не найден или конвертация упала)."""
