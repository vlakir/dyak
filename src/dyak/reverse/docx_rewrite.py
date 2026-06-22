"""
Пере-запись run'ов параграфа: вставка тегов в склеенный текст (T007).

Зеркало проблемы forward-рендера: Word дробит текст по `run`'ам произвольно,
поэтому искомое значение («01.07.2026») может быть разрезано на несколько
run'ов. Чтобы `generate`/docxtpl увидел тег `{{ Дата_начала }}` целым, мы
кладём его **целиком в один run** (тот, что владеет началом спана), а
промежуточные run'ы спана очищаем.

Алгоритм (инверсия склейки docxtpl), на параграф:
1. Склеить тексты run'ов → плоская строка + карта границ `[start, end)` на
   каждый run (`flatten_runs`).
2. На плоской строке matcher уже нашёл непересекающиеся спаны замены.
3. Пройти слева направо: литеральный текст вне спанов раскладывается обратно
   по своим run'ам (сохраняя форматирование), а каждый тег целиком ложится в
   run начала спана. Внутренность спана пропускается → её run'ы пустеют.

Работает на одном параграфе; обход всех параграфов (включая таблицы) —
`render.engine.iter_paragraphs`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from docx.text.paragraph import Paragraph

    from dyak.reverse.matcher import Match

# Границы каждого run'а в координатах склеенного текста параграфа.
RunBounds = list[tuple[int, int]]


def flatten_runs(paragraph: Paragraph) -> tuple[str, RunBounds]:
    """Склеить тексты run'ов → плоская строка + границы `[start, end)` каждого."""
    parts: list[str] = []
    bounds: RunBounds = []
    cursor = 0
    for run in paragraph.runs:
        text = run.text
        bounds.append((cursor, cursor + len(text)))
        parts.append(text)
        cursor += len(text)
    return ''.join(parts), bounds


def _run_of(bounds: RunBounds, offset: int) -> int:
    """Индекс run'а, владеющего глобальным смещением (`start <= offset < end`)."""
    for index, (start, end) in enumerate(bounds):
        if start <= offset < end:
            return index
    # Недостижимо для валидных смещений (вызывается только при offset < len).
    return len(bounds) - 1


def rewrite_paragraph(
    paragraph: Paragraph,
    full: str,
    bounds: RunBounds,
    matches: list[Match],
) -> None:
    """
    Заменить найденные спаны на теги, переписав тексты run'ов параграфа.

    `matches` — непересекающиеся, отсортированы по началу (контракт matcher).
    Литеральный текст вне спанов сохраняется на своих run'ах (форматирование
    не теряется), тег целиком кладётся в run начала спана.
    """
    runs = paragraph.runs
    new_texts = [''] * len(runs)

    def copy_literal(start: int, stop: int) -> None:
        """Разложить литеральный текст `full[start:stop]` обратно по run'ам."""
        cursor = start
        while cursor < stop:
            index = _run_of(bounds, cursor)
            chunk_end = min(stop, bounds[index][1])
            new_texts[index] += full[cursor:chunk_end]
            cursor = chunk_end

    cursor = 0
    for match in matches:
        copy_literal(cursor, match.start)
        new_texts[_run_of(bounds, match.start)] += match.candidate.tag
        cursor = match.end
    copy_literal(cursor, len(full))

    for run, text in zip(runs, new_texts, strict=True):
        run.text = text
