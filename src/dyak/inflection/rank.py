"""
Склонение воинских/служебных званий (T016, фаза B).

Звание остаётся отдельной спец-веткой от общего фраз-движка
(`PhraseInflector`, T024): тот для тесного дефиса склоняет ЛИБО весь токен
(известная лексема), ЛИБО каждую часть — и регрессировал бы «контр-адмирал»
(нужен только последний сегмент). Звание устроено иначе, чем должность: голова
(плюс согласованные прилагательные «старший»/«младший») склоняется, а хвост
после маркера («медицинской службы», «N ранга», «юстиции», «Российской
Федерации») стоит в родительном и должен **замереть**.

`RankInflector` (гибрид, решение Разработчика 2026-06-22):
1. **Пословно** склоняет голову — токены до генитивного хвоста (так
   «старший лейтенант» → «старшему лейтенанту»).
2. **Замораживает хвост** — всё от маркера: числовой токен (`3 ранга`),
   слово с заглавной (имя собственное `Российской Федерации`) или
   курируемый маркер-существительное (`службы`/`юстиции`/`ранга`/…), с
   откатом назад через согласованное прилагательное («медицинской службы»).
3. **Дефис** — склоняет только последний сегмент токена («контр-адмиралу»,
   «генерал-майору»), служебную приставку не трогает.

`Rank` — склоняемое звание (`Declinable`): сначала ручной `overrides.rank`
для своего текста, затем движок. Несогласуемые редкие звания закрываются
вручную с приоритетом над эвристикой.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from dyak.domain import CASE_RUS, Case
from dyak.inflection.morph import get_analyzer
from dyak.inflection.phrase import inflect_word

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pymorphy3 import MorphAnalyzer

# Маркер-существительные (в родительном) — начало несогласованного хвоста
# звания: «медицинской СЛУЖБЫ», «3 РАНГА», «юстиции 1 КЛАССА», «майор ПОЛИЦИИ».
# Пополняется по мере находок (ADR); неполнота → хвост просклоняется как
# обычное слово (мягкая деградация, как у должностей до T016).
_TAIL_MARKERS = frozenset({
    'службы', 'юстиции', 'полиции', 'милиции', 'безопасности',
    'флота', 'флотилии', 'ранга', 'класса', 'армии', 'гвардии',
    'авиации', 'войск', 'разряда',
})  # fmt: skip

# Токен начинается с цифры (порядок звания: «3 ранга», «1 класса»).
_STARTS_DIGIT = re.compile(r'^\d')


def _is_adjf(word: str, analyzer: MorphAnalyzer) -> bool:
    """Является ли слово прилагательным (согласованное определение головы)."""
    return analyzer.parse(word)[0].tag.POS == 'ADJF'


def _freeze_index(tokens: list[str], analyzer: MorphAnalyzer) -> int:
    """Индекс, с которого начинается замороженный генитивный хвост звания."""
    for i in range(1, len(tokens)):
        token = tokens[i]
        if _STARTS_DIGIT.match(token) or token[:1].isupper():
            return i
        if token.lower() in _TAIL_MARKERS:
            # Откатываемся назад через согласованное прилагательное хвоста
            # («медицинской службы» — заморозить и «медицинской»).
            start = i
            while start - 1 >= 1 and _is_adjf(tokens[start - 1], analyzer):
                start -= 1
            return start
    return len(tokens)


def _decline_token(token: str, case: Case, analyzer: MorphAnalyzer) -> str:
    """Просклонять токен; для дефисного — только последний сегмент."""
    if '-' in token:
        segments = token.split('-')
        segments[-1] = inflect_word(segments[-1], case, analyzer)
        return '-'.join(segments)
    return inflect_word(token, case, analyzer)


@functools.lru_cache(maxsize=4096)
def _decline_rank(text: str, case: Case) -> str:
    """Просклонять звание к падежу `case`: голова склоняется, хвост замирает."""
    analyzer = get_analyzer()
    tokens = text.split()
    if len(tokens) == 1:
        return _decline_token(tokens[0], case, analyzer)
    freeze = _freeze_index(tokens, analyzer)
    head = [_decline_token(token, case, analyzer) for token in tokens[:freeze]]
    return ' '.join(head + tokens[freeze:])


class RankInflector:
    """Склонение звания: голова + замороженный генитивный хвост (с кешем)."""

    def inflect(self, text: str, case: Case) -> str:
        """Просклонять `text` к `case`; именительный = исходный текст."""
        if not text or case is Case.NOMN:
            return text
        return _decline_rank(text, case)


@dataclass(frozen=True, slots=True)
class Rank:
    """Склоняемое звание: ручной `overrides.rank` с приоритетом над движком."""

    text: str
    inflector: RankInflector
    # Ручные формы для ЭТОГО текста: русское сокращение падежа → форма.
    overrides: Mapping[str, str] = field(default_factory=dict)

    def inflect(self, case: Case) -> str:
        """Форма звания в падеже `case`: override → движок."""
        override = self.overrides.get(CASE_RUS[case])
        if override is not None:
            return override
        return self.inflector.inflect(self.text, case)

    def __str__(self) -> str:
        return self.text
