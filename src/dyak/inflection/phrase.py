"""
Универсальный фраз-движок склонения (T024, модель «склонение по умолчанию»).

`PhraseInflector` склоняет ЛЮБУЮ текстовую фразу (должность, подразделение,
произвольную колонку) в целевой падеж, разбирая её морфологически через
`pymorphy3`. Это ядро новой модели: склоняется всё, роли лишь уточняют
специализации (ФИО — petrovich+пол; звание — `RankInflector`; коды/даты —
литерал). Развитие наивного пословного движка T003, закрывает T022 и снимает
band-aid T020 (см. ADR в `DECISIONS.md`).

Алгоритм одного сегмента `[модификаторы] ГОЛОВА [родительный хвост]`:

1. **Родительный хвост** ищется СПРАВА: слово замораживается, если его верхний
   разбор — родительный падеж И у него нет именительного ЕДИНСТВЕННОГО разбора
   («связи», «охраны», «штаба», «медицинской службы» — морозятся; «батальон»,
   «техник» — нет, хотя у них есть омонимичный родительный множественного).
2. **Голова + согласованные модификаторы** (прилагательные, числительные,
   само существительное-голова) склоняются в целевой падеж. Для винительного
   модификаторам передаётся ОДУШЕВЛЁННОСТЬ головы, поэтому «танковый батальон»
   (неодуш.) → вин. = им. («танковый батальон», не «танкового»).

Составные должности (T024, разные разделители — кадровик пишет как попало):

- **Разделитель-с-пробелами** (` - `, ` – `, ` — ` и пр.) — ДВЕ параллельных
  должности: каждый сегмент склоняется отдельно, разделитель сохраняется
  символ-в-символ.
- **Тесный дефис** без пробелов («стрелок-радист», «генерал-майор») —
  неоднозначно: если pymorphy знает ВЕСЬ токен (известная лексема —
  «генерал-майор») → склоняем как одно слово (меняется только хвост); иначе →
  аппозитивный компаунд, склоняем КАЖДУЮ часть («стрелку-радисту»).

`Phrase` — склоняемая фраза (`Declinable`): ручной `overrides` для своего
текста имеет приоритет над движком (несогласуемые редкие фразы закрываются
вручную).
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
    from pymorphy3.analyzer import Parse

# Все виды чёрточек: дефис-минус, неразрывный дефис, en/em/figure dash, минус.
_DASHES = '-‐‑‒–—―−'
# Разделитель-с-пробелами → две параллельные должности (сохраняем как есть).
_PARALLEL_SEP = re.compile(rf'(\s+[{_DASHES}]\s+)')
# Разбиение тесного дефисного компаунда с сохранением разделителей.
_HYPHEN_SPLIT = re.compile(rf'([{_DASHES}])')
# Части речи, которые склоняем (прочее — служебное/неизвестное — как есть).
_DECLINABLE_POS = frozenset({'NOUN', 'ADJF', 'NUMR'})


def inflect_word(word: str, case: Case, analyzer: MorphAnalyzer) -> str:
    """
    Просклонять одно слово к падежу `case`; неразобранное — как есть.

    Простой примитив (верхний разбор): используется движком званий
    (`inflection/rank.py`), где голова уже вычленена отдельно.
    """
    parsed = analyzer.parse(word)[0]
    inflected = parsed.inflect({case.value})
    return inflected.word if inflected is not None else word


def _primary_parse(word: str, analyzer: MorphAnalyzer) -> Parse:
    """Разбор склоняемого слова: предпочесть именительный (фраза — в им.)."""
    parses = analyzer.parse(word)
    for parse in parses:
        if parse.tag.POS in _DECLINABLE_POS and parse.tag.case == 'nomn':
            return parse
    return parses[0]


def _is_frozen_tail(word: str, analyzer: MorphAnalyzer) -> bool:
    """
    Определить, является ли слово замороженным родительным хвостом фразы.

    Да, если верхний разбор — родительный И нет именительного ЕДИНСТВЕННОГО
    разбора. Так настоящий комплемент («связи», «охраны», «штаба») морозится, а
    голова-омоним с родительным множественного («батальон», «техник») — нет.
    """
    parses = analyzer.parse(word)
    if parses[0].tag.case != 'gent':
        return False
    return not any(
        p.tag.POS == 'NOUN' and p.tag.case == 'nomn' and p.tag.number == 'sing'
        for p in parses
    )


def _inflect_token(
    word: str, case: Case, analyzer: MorphAnalyzer, anim: str | None
) -> str:
    """Просклонять токен (со связью по одушевлённости); тесный дефис — особо."""
    if any(d in word for d in _DASHES):
        return _inflect_hyphen_compound(word, case, analyzer, anim)
    parse = _primary_parse(word, analyzer)
    if parse.tag.POS not in _DECLINABLE_POS:
        return word  # служебное/неизвестное/цифра — не трогаем
    grammemes = {case.value} if anim is None else {case.value, anim}
    inflected = parse.inflect(grammemes) or parse.inflect({case.value})
    return inflected.word if inflected is not None else word


def _inflect_hyphen_compound(
    word: str, case: Case, analyzer: MorphAnalyzer, anim: str | None
) -> str:
    """Тесный дефис: известную лексему — целиком, иначе — каждую часть."""
    if analyzer.word_is_known(word.lower()):
        # «генерал-майор» → меняется только хвост (склоняем весь токен).
        parse = _primary_parse(word, analyzer)
        grammemes = {case.value} if anim is None else {case.value, anim}
        inflected = parse.inflect(grammemes) or parse.inflect({case.value})
        return inflected.word if inflected is not None else word
    # Аппозитивный компаунд («стрелок-радист») → склоняем каждую часть.
    parts = _HYPHEN_SPLIT.split(word)
    return ''.join(
        part
        if part in _DASHES or not part
        else _inflect_token(part, case, analyzer, anim)
        for part in parts
    )


def _inflect_segment(segment: str, case: Case, analyzer: MorphAnalyzer) -> str:
    """Просклонять один сегмент: голова+согласование, родительный хвост — замёрз."""
    words = segment.split(' ')
    split = len(words)
    while split > 0 and _is_frozen_tail(words[split - 1], analyzer):
        split -= 1
    split = max(split, 1)  # хотя бы голова остаётся склоняемой
    head_words, tail = words[:split], words[split:]

    head_anim: str | None = None
    head_idx = len(head_words) - 1
    for i, word in enumerate(head_words):
        if _primary_parse(word, analyzer).tag.POS == 'NOUN':
            head_anim = _primary_parse(word, analyzer).tag.animacy
            head_idx = i  # голова — последнее существительное головной части
    declined = [
        _inflect_token(word, case, analyzer, None if i == head_idx else head_anim)
        for i, word in enumerate(head_words)
    ]
    return ' '.join(declined + tail)


@functools.lru_cache(maxsize=4096)
def _inflect_phrase(text: str, case: Case) -> str:
    """Просклонять фразу к падежу `case` (кешируется)."""
    analyzer = get_analyzer()
    return ''.join(
        chunk
        if _PARALLEL_SEP.fullmatch(chunk)
        else _inflect_segment(chunk, case, analyzer)
        for chunk in _PARALLEL_SEP.split(text)
    )


class PhraseInflector:
    """Склонение произвольной фразы: голова+согласование+замороженный хвост."""

    def inflect(self, text: str, case: Case) -> str:
        """Просклонять `text` к `case`; именительный = исходный текст."""
        if not text or case is Case.NOMN:
            return text
        return _inflect_phrase(text, case)


@dataclass(frozen=True, slots=True)
class Phrase:
    """Склоняемая текстовая фраза: ручной override с приоритетом над движком."""

    text: str
    inflector: PhraseInflector
    # Ручные формы для ЭТОГО текста: русское сокращение падежа → форма.
    overrides: Mapping[str, str] = field(default_factory=dict)

    def inflect(self, case: Case) -> str:
        """Форма фразы в падеже `case`: override → движок."""
        override = self.overrides.get(CASE_RUS[case])
        if override is not None:
            return override
        return self.inflector.inflect(self.text, case)

    def __str__(self) -> str:
        return self.text
