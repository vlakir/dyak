"""Доменные исключения dyak."""

from __future__ import annotations


class DyakError(Exception):
    """Базовое исключение dyak — все ожидаемые ошибки наследуют его."""


class ConfigError(DyakError):
    """Ошибка конфигурации (`dyak.yaml`)."""


class TableError(DyakError):
    """Ошибка чтения/валидации входной таблицы."""
