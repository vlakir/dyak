"""
Оркестратор обратной генерации шаблона (`dyak reverse`, T007 фаза 1).

Читает образец-docx, по каждому параграфу (включая таблицы) ищет точные
вхождения значений строки и переписывает run'ы, вставляя теги
`{{ Заголовок }}`. Собирает отчёт: что заменено (`replaced`), какие значения
строки не нашлись (`not_found`), какие фрагменты документа похожи на данные,
но пары в строке не имеют (`unmatched_text`).

Фаза 1 — только точные (именительные) совпадения; склонение по падежам —
фаза 2, round-trip verify — фаза 3.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import docx
from docx.opc.exceptions import PackageNotFoundError

from dyak.errors import ReverseError
from dyak.render.engine import iter_paragraphs
from dyak.reverse.candidates import build_candidates
from dyak.reverse.docx_rewrite import flatten_runs, rewrite_paragraph
from dyak.reverse.matcher import find_spans
from dyak.reverse.report import FindingKind, ReverseReport

if TYPE_CHECKING:
    from pathlib import Path

    from docx.document import Document

    from dyak.domain import Person
    from dyak.reverse.candidates import Candidate
    from dyak.reverse.matcher import Match

# Фрагменты, «похожие на данные»: дата ДД.ММ.ГГГГ и просто число (2+ цифр).
# Дата приоритетнее голого числа, чтобы год не дублировал свою же дату.
_DATE = re.compile(r'\d{1,2}\.\d{1,2}\.\d{2,4}')
_NUMBER = re.compile(r'\d{2,}')


def _load(doc_path: Path) -> Document:
    """Открыть образец-docx; обернуть ошибку чтения в `ReverseError`."""
    try:
        return docx.Document(str(doc_path))
    except PackageNotFoundError as exc:
        msg = f'Не удалось прочитать образец-документ: {doc_path}'
        raise ReverseError(msg) from exc


def _data_like_spans(text: str) -> list[tuple[int, int, str]]:
    """Найти фрагменты «похоже на данные» (даты, затем числа вне дат)."""
    spans = [(m.start(), m.end(), m.group()) for m in _DATE.finditer(text)]
    for m in _NUMBER.finditer(text):
        if any(s <= m.start() < e for s, e, _ in spans):
            continue  # число внутри уже найденной даты — не дублируем
        spans.append((m.start(), m.end(), m.group()))
    return spans


def _collect_unmatched(text: str, matches: list[Match]) -> list[str]:
    """Фрагменты-данные параграфа, не покрытые ни одним совпавшим спаном."""
    unmatched: list[str] = []
    for start, end, token in _data_like_spans(text):
        covered = any(m.start < end and start < m.end for m in matches)
        if not covered:
            unmatched.append(token)
    return unmatched


def build_template(doc_path: Path, person: Person) -> tuple[Document, ReverseReport]:
    """
    Построить docx-шаблон из образца и строки данных (фаза 1).

    Возвращает переписанный `Document` (теги вместо значений) и отчёт.
    Образец мутируется на месте — это и есть будущий шаблон.
    """
    document = _load(doc_path)
    candidates = build_candidates(person)
    counts: dict[str, int] = {}
    unmatched: list[str] = []

    for paragraph in iter_paragraphs(document):
        full, bounds = flatten_runs(paragraph)
        if not full:
            continue
        matches = find_spans(full, candidates)
        if matches:
            rewrite_paragraph(paragraph, full, bounds, matches)
            for match in matches:
                counts[match.candidate.key] = counts.get(match.candidate.key, 0) + 1
        unmatched.extend(_collect_unmatched(full, matches))

    return document, _build_report(candidates, counts, unmatched)


def _build_report(
    candidates: list[Candidate],
    counts: dict[str, int],
    unmatched: list[str],
) -> ReverseReport:
    """Свести замены/ненайденные/несопоставленные фрагменты в отчёт."""
    report = ReverseReport()
    for candidate in candidates:
        value = candidate.forms[0]
        count = counts.get(candidate.key, 0)
        if count:
            suffix = f' (×{count})' if count > 1 else ''
            report.add(
                FindingKind.REPLACED,
                f'{candidate.key}: «{value}» → {candidate.tag}{suffix}',
            )
        else:
            report.add(
                FindingKind.NOT_FOUND,
                f'{candidate.key}: «{value}» не найдено в документе',
            )
    for token in dict.fromkeys(unmatched):  # уникальные, порядок сохраняем
        report.add(
            FindingKind.UNMATCHED_TEXT,
            f'«{token}» — похоже на данные, но нет в строке',
        )
    return report
