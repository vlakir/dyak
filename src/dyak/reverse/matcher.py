"""
Поиск форм кандидатов в тексте параграфа и разрешение перекрытий (T007).

Матчер ищет вхождение **любой формы** кандидата (`SearchForm.text`) в
склеенный текст параграфа со **словной границей** — чтобы «Анна» не совпала
внутри «Жанна», а «5» — внутри «2025». Сами формы готовят кандидаты:
в фазе 1 это только текст ячейки (именительный), в фазе 2 — ещё и
просклонённые по 6 падежам формы ФИО/должностей (decline-and-match), поэтому
«Иванову» совпадёт с дательным падежом фамилии и получит тег `{{ Фамилия | дт }}`.

Перекрытия (часть ФИО внутри более длинного значения, дата внутри номера и
т.п.) разрешаются жадно: длинные кандидаты раньше коротких, занятые позиции
повторно не используются (Analyze W4). Возвращаются непересекающиеся спаны,
отсортированные по позиции.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dyak.reverse.candidates import Candidate, SearchForm


@dataclass(frozen=True, slots=True)
class Match:
    """Выбранный непересекающийся спан замены в тексте параграфа."""

    start: int
    end: int
    candidate: Candidate
    form: SearchForm

    @property
    def length(self) -> int:
        """Длина занятого спана (для приоритета длинных при перекрытии)."""
        return self.end - self.start


def _is_word_char(char: str) -> bool:
    """Буква/цифра/подчёркивание (Unicode-aware, включая кириллицу)."""
    return char.isalnum() or char == '_'


def _has_word_boundary(text: str, start: int, end: int) -> bool:
    """Не примыкает ли спан `[start, end)` к буквенно-цифровому соседу."""
    before_ok = start == 0 or not _is_word_char(text[start - 1])
    after_ok = end == len(text) or not _is_word_char(text[end])
    return before_ok and after_ok


def _occurrences(text: str, needle: str) -> list[tuple[int, int]]:
    """Все вхождения `needle` в `text` со словной границей (без перекрытий)."""
    spans: list[tuple[int, int]] = []
    pos = text.find(needle)
    while pos != -1:
        end = pos + len(needle)
        if _has_word_boundary(text, pos, end):
            spans.append((pos, end))
        pos = text.find(needle, pos + 1)
    return spans


def find_spans(text: str, candidates: list[Candidate]) -> list[Match]:
    """
    Найти непересекающиеся спаны замены в склеенном тексте параграфа.

    Все вхождения всех форм кандидатов собираются, сортируются по длине
    (длинные раньше) и жадно занимают свободные позиции. Возврат —
    отсортирован по началу спана (для пере-записи run'ов слева направо).
    """
    found: list[Match] = []
    for candidate in candidates:
        for form in candidate.forms:
            if not form.text:
                continue
            for start, end in _occurrences(text, form.text):
                found.append(Match(start, end, candidate, form))

    found.sort(key=lambda m: (-m.length, m.start))
    occupied = [False] * len(text)
    selected: list[Match] = []
    for match in found:
        if any(occupied[match.start : match.end]):
            continue
        for i in range(match.start, match.end):
            occupied[i] = True
        selected.append(match)

    selected.sort(key=lambda m: m.start)
    return selected
