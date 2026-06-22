"""Доменные исключения dyak."""

from __future__ import annotations


class DyakError(Exception):
    """Базовое исключение dyak — все ожидаемые ошибки наследуют его."""


class ConfigError(DyakError):
    """Ошибка конфигурации (`dyak.yaml`)."""


class TableError(DyakError):
    """Ошибка чтения/валидации входной таблицы."""


class TemplateError(DyakError):
    """Ошибка рендера шаблона (базовая): напр. неприменимый фильтр."""


class UndefinedVariableError(TemplateError):
    """Шаблон ссылается на неизвестную переменную (`StrictUndefined`)."""


class PdfExportError(DyakError):
    """Ошибка экспорта в PDF (LibreOffice не найден или конвертация упала)."""


class ReverseError(DyakError):
    """Ошибка обратной генерации шаблона (`dyak reverse`): образец не читается."""
