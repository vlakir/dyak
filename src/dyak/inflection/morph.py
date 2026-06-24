"""
Общий `MorphAnalyzer` (pymorphy3) для всей подсистемы склонения.

`MorphAnalyzer` дорог в создании (грузит словарь в мегабайты), поэтому
экземпляр один на процесс и общий для всех потребителей: автоопределение
пола (`gender.py`) и склонение фраз (`phrase.py`). Создаётся
лениво при первом обращении (`functools.cache`); импорт `pymorphy3` — в
шапке модуля (правило импортов), отложена лишь инстанциация.
"""

from __future__ import annotations

import functools

import pymorphy3


@functools.cache
def get_analyzer() -> pymorphy3.MorphAnalyzer:
    """Единственный на процесс `MorphAnalyzer` (создаётся при первом вызове)."""
    return pymorphy3.MorphAnalyzer()
