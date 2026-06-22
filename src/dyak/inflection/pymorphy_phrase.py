"""
Склонение должностей и произвольных фраз через `pymorphy3` (§7.2–7.4).

`PymorphyInflector` склоняет фразу **пословно**: токенизация по пробелам и
дефису (разделители сохраняются), разбор каждого слова, `.inflect({падеж})`,
сборка обратно. Несклонившийся/неразобранный токен остаётся как есть.
Результат кешируется (`lru_cache` по `(text, case)`): на таблице с
повторяющимися должностями повторный разбор не нужен.

Род человека на склонение существительных не влияет («директора» одинаково
для м/ж), поэтому в сигнатуре его нет — отклонение от общего Inflector-
протокола CONCEPT §6 (там `gender` для общности) зафиксировано в ADR.

`Position` — склоняемая должность (`Declinable`): сначала смотрит словарь
ручных форм (`overrides`, §7.3) для своего текста, затем движок. Так
сложные несогласуемые фразы («заместитель генерального директора»)
закрываются вручную с приоритетом над автоматикой.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dyak.domain import CASE_RUS, Case
from dyak.inflection.morph import get_analyzer

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pymorphy3 import MorphAnalyzer

# Токенизация фразы с сохранением разделителей (пробелы и дефис).
_TOKENS = re.compile(r'(\s+|-)')


def inflect_word(word: str, case: Case, analyzer: MorphAnalyzer) -> str:
    """
    Просклонять одно слово к падежу `case`; неразобранное — как есть.

    Общий примитив склонения слова: используется и пословным движком фраз
    (`_decline_phrase`), и движком званий (`inflection/rank.py`).
    """
    parsed = analyzer.parse(word)[0]
    inflected = parsed.inflect({case.value})
    return inflected.word if inflected is not None else word


@functools.lru_cache(maxsize=4096)
def _decline_phrase(text: str, case: Case) -> str:
    """Просклонять фразу пословно к падежу `case` (кешируется)."""
    analyzer = get_analyzer()
    parts: list[str] = []
    for chunk in _TOKENS.split(text):
        if not chunk or chunk.isspace() or chunk == '-':
            parts.append(chunk)
            continue
        parts.append(inflect_word(chunk, case, analyzer))
    return ''.join(parts)


class PymorphyInflector:
    """Пословное склонение фразы через общий `MorphAnalyzer` (с кешем)."""

    def inflect(self, text: str, case: Case) -> str:
        """Просклонять `text` к `case`; именительный = исходный текст."""
        if not text or case is Case.NOMN:
            return text
        return _decline_phrase(text, case)


@dataclass(frozen=True, slots=True)
class Position:
    """Склоняемая должность: ручной override (§7.3) с приоритетом над движком."""

    text: str
    inflector: PymorphyInflector
    # Ручные формы для ЭТОГО текста: русское сокращение падежа → форма.
    overrides: Mapping[str, str] = field(default_factory=dict)

    def inflect(self, case: Case) -> str:
        """Форма должности в падеже `case`: override → движок."""
        override = self.overrides.get(CASE_RUS[case])
        if override is not None:
            return override
        return self.inflector.inflect(self.text, case)

    def __str__(self) -> str:
        return self.text
