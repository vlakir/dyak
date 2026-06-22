"""
Оркестратор обратной генерации шаблона (`dyak reverse`, T007 фаза 1).

Читает образец-docx, по каждому параграфу (включая таблицы) ищет вхождения
форм значений строки и переписывает run'ы, вставляя теги `{{ Заголовок }}`
(фаза 1) и теги с падежными фильтрами `{{ Фамилия | дт }}` (фаза 2,
decline-and-match). Собирает отчёт: что заменено уверенно (`replaced`), что
заменено с неоднозначным падежом (`ambiguous`), какие значения строки не
нашлись (`not_found`), какие фрагменты документа похожи на данные, но пары в
строке не имеют (`unmatched_text`).

Round-trip verify (`roundtrip_mismatch`) — фаза 3.
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

    from dyak.config import CaseForms
    from dyak.domain import Gender, Person
    from dyak.inflection import PetrovichInflector, PymorphyInflector
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


def build_template(
    doc_path: Path,
    person: Person,
    *,
    fullname_source: str | None = None,
    roles: dict[str, str] | None = None,
    inflector: PetrovichInflector | None = None,
    gender_overrides: dict[str, Gender] | None = None,
    position_inflector: PymorphyInflector | None = None,
    position_overrides: dict[str, CaseForms] | None = None,
) -> tuple[Document, ReverseReport]:
    """
    Построить docx-шаблон из образца и строки данных.

    С движками склонения подставляются падежные теги (фаза 2), без них —
    только точные именительные совпадения (фаза 1). Возвращает переписанный
    `Document` (теги вместо значений) и отчёт; образец мутируется на месте.
    """
    document = _load(doc_path)
    candidates = build_candidates(
        person,
        fullname_source=fullname_source,
        roles=roles,
        inflector=inflector,
        gender_overrides=gender_overrides,
        position_inflector=position_inflector,
        position_overrides=position_overrides,
    )
    matches_all: list[Match] = []
    unmatched: list[str] = []

    for paragraph in iter_paragraphs(document):
        full, bounds = flatten_runs(paragraph)
        if not full:
            continue
        matches = find_spans(full, candidates)
        if matches:
            rewrite_paragraph(paragraph, full, bounds, matches)
            matches_all.extend(matches)
        unmatched.extend(_collect_unmatched(full, matches))

    return document, _build_report(candidates, matches_all, unmatched)


def _build_report(
    candidates: list[Candidate],
    matches: list[Match],
    unmatched: list[str],
) -> ReverseReport:
    """Свести замены/неоднозначности/ненайденные/несопоставленные в отчёт."""
    report = ReverseReport()
    matched_keys: set[str] = set()
    counts: dict[tuple[str, str, bool], int] = {}
    order: list[tuple[str, str, bool]] = []
    for match in matches:
        matched_keys.add(match.candidate.key)
        signature = (match.candidate.key, match.form.tag, match.form.ambiguous)
        if signature not in counts:
            order.append(signature)
        counts[signature] = counts.get(signature, 0) + 1

    display = {candidate.key: candidate.display for candidate in candidates}
    for key, tag, ambiguous in order:
        count = counts[key, tag, ambiguous]
        suffix = f' (×{count})' if count > 1 else ''
        value = display.get(key, '')
        if ambiguous:
            report.add(
                FindingKind.AMBIGUOUS,
                f'{key}: «{value}» → {tag} (падеж под вопросом){suffix}',
            )
        else:
            report.add(FindingKind.REPLACED, f'{key}: «{value}» → {tag}{suffix}')

    for candidate in candidates:
        if candidate.primary and candidate.key not in matched_keys:
            report.add(
                FindingKind.NOT_FOUND,
                f'{candidate.key}: «{candidate.display}» не найдено в документе',
            )
    for token in dict.fromkeys(unmatched):  # уникальные, порядок сохраняем
        report.add(
            FindingKind.UNMATCHED_TEXT,
            f'«{token}» — похоже на данные, но нет в строке',
        )
    return report
