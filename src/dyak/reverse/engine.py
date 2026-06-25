"""
Оркестратор обратной генерации шаблона (`dyak reverse`, T007).

Читает образец-docx, по каждому параграфу (включая таблицы) ищет вхождения
форм значений строки и переписывает run'ы, вставляя теги `{{ Заголовок }}`
(фаза 1) и теги с падежными фильтрами `{{ Фамилия | дт }}` (фаза 2,
decline-and-match). Собирает отчёт: что заменено уверенно (`replaced`), что
заменено с неоднозначным падежом (`ambiguous`), какие значения строки не
нашлись (`not_found`), какие фрагменты документа похожи на данные, но пары в
строке не имеют (`unmatched_text`).

Фаза 3 добавляет **round-trip verify**: собранный шаблон прогоняется
forward-рендером (`generate`) на той же строке, и результат сверяется с
исходным документом. Это проверка верности, не полноты (Analyze W2):
сопоставленные склоняемые формы воспроизводятся всегда (matcher и forward
зовут один и тот же `inflect(case)`), поэтому сверка молчит на корректном
шаблоне, но ловит места, где образец содержит постороннюю jinja-разметку
(`{% raw %}`-шпаргалка, забытый тег) или где рендер вовсе не удался —
`roundtrip_mismatch`.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import docx
from docx.opc.exceptions import PackageNotFoundError

from dyak.errors import DyakError, ReverseError
from dyak.render.context import build_context
from dyak.render.engine import iter_paragraphs, render_to_document
from dyak.reverse.candidates import build_candidates
from dyak.reverse.docx_rewrite import flatten_runs, rewrite_paragraph
from dyak.reverse.matcher import find_spans
from dyak.reverse.report import FindingKind, ReverseReport

if TYPE_CHECKING:
    from docx.document import Document

    from dyak.config import CaseForms
    from dyak.domain import Gender, Person
    from dyak.inflection import PetrovichInflector, PhraseInflector, RankInflector
    from dyak.reverse.candidates import Candidate
    from dyak.reverse.matcher import Match

# Фрагменты, «похожие на данные»: дата ДД.ММ.ГГГГ и просто число (2+ цифр).
# Дата приоритетнее голого числа, чтобы год не дублировал свою же дату.
_DATE = re.compile(r'\d{1,2}\.\d{1,2}\.\d{2,4}')
_NUMBER = re.compile(r'\d{2,}')
# Любая пробельная последовательность → один пробел при сверке round-trip.
_WHITESPACE = re.compile(r'\s+')
# До скольки символов ужимать фрагмент в сообщении о расхождении.
_CLIP_LEN = 80


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


def _normalize_ws(text: str) -> str:
    """Схлопнуть любые пробелы к одному и обрезать края (для сверки текста)."""
    return _WHITESPACE.sub(' ', text).strip()


def _clip(text: str) -> str:
    """Ужать длинный фрагмент для читаемого сообщения о расхождении."""
    return text if len(text) <= _CLIP_LEN else f'{text[:_CLIP_LEN]}…'


def build_template(
    doc_path: Path,
    person: Person,
    *,
    fullname_source: str | None = None,
    roles: dict[str, str] | None = None,
    inflector: PetrovichInflector | None = None,
    gender_overrides: dict[str, Gender] | None = None,
    decline_surnames: set[str] | None = None,
    position_inflector: PhraseInflector | None = None,
    position_overrides: dict[str, CaseForms] | None = None,
    rank_inflector: RankInflector | None = None,
    rank_overrides: dict[str, CaseForms] | None = None,
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
        decline_surnames=decline_surnames,
        position_inflector=position_inflector,
        position_overrides=position_overrides,
        rank_inflector=rank_inflector,
        rank_overrides=rank_overrides,
    )
    matches_all: list[Match] = []
    unmatched: list[str] = []
    originals: list[str] = []

    for paragraph in iter_paragraphs(document):
        full, bounds = flatten_runs(paragraph)
        originals.append(_normalize_ws(full))  # снимок ДО переписывания run'ов
        if not full:
            continue
        matches = find_spans(full, candidates)
        if matches:
            rewrite_paragraph(paragraph, full, bounds, matches)
            matches_all.extend(matches)
        unmatched.extend(_collect_unmatched(full, matches))

    report = _build_report(candidates, matches_all, unmatched)
    _verify_roundtrip(
        document,
        originals,
        report,
        person,
        fullname_source=fullname_source,
        roles=roles,
        inflector=inflector,
        gender_overrides=gender_overrides,
        decline_surnames=decline_surnames,
        position_inflector=position_inflector,
        position_overrides=position_overrides,
        rank_inflector=rank_inflector,
        rank_overrides=rank_overrides,
    )
    return document, report


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
    _add_signature_risk(report, candidates, matches)
    for token in dict.fromkeys(unmatched):  # уникальные, порядок сохраняем
        report.add(
            FindingKind.UNMATCHED_TEXT,
            f'«{token}» — похоже на данные, но нет в строке',
        )
    return report


def _add_signature_risk(
    report: ReverseReport,
    candidates: list[Candidate],
    matches: list[Match],
) -> None:
    """
    Предупредить, если имя субъекта заменено в нескольких местах (T018).

    Подпись и блок исполнителя содержат фамилию/инициалы, и при совпадении с
    субъектом строки они тоже получают тег — а там лицо обычно постоянное.
    Reverse не знает, какое вхождение «настоящее», поэтому лишь сигналит.
    Тело + инициалы-в-подписи дают по матчу на разных кандидатов, поэтому
    считаем по всей семье ФИО (`name_part`), а не по одному кандидату.
    """
    name_keys = {c.key for c in candidates if c.name_part}
    places = sum(1 for match in matches if match.candidate.key in name_keys)
    if places > 1:
        report.add(
            FindingKind.SIGNATURE_RISK,
            f'имя субъекта заменено тегами в {places} местах — проверьте, нет ли '
            f'среди них подписи или блока исполнителя (там фамилия обычно '
            f'постоянная; уберите тег, оставив текст)',
        )


def _render_forward(document: Document, context: dict[str, object]) -> Document:
    """Сохранить собранный шаблон во временный docx и прогнать forward-рендер."""
    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = Path(tmpdir) / 'roundtrip.docx'
        document.save(str(template_path))
        return render_to_document(template_path, context)


def _verify_roundtrip(
    document: Document,
    originals: list[str],
    report: ReverseReport,
    person: Person,
    *,
    fullname_source: str | None,
    roles: dict[str, str] | None,
    inflector: PetrovichInflector | None,
    gender_overrides: dict[str, Gender] | None,
    decline_surnames: set[str] | None,
    position_inflector: PhraseInflector | None,
    position_overrides: dict[str, CaseForms] | None,
    rank_inflector: RankInflector | None,
    rank_overrides: dict[str, CaseForms] | None,
) -> None:
    """
    Сверить, что шаблон, прогнанный forward-рендером на той же строке,
    воспроизводит исходный документ; расхождения → `roundtrip_mismatch`.

    Контекст строится тем же `build_context`, что у `generate`, — сверка
    честна к реальному пути генерации. Рендер изолирован: его падение
    (best-effort инструмент) не должно ронять уже собранный шаблон, поэтому
    `DyakError` превращается в находку, а не исключение.
    """
    context = build_context(
        person,
        fullname_source=fullname_source,
        roles=roles or {},
        inflector=inflector,
        gender_overrides=gender_overrides,
        decline_surnames=decline_surnames,
        position_inflector=position_inflector,
        position_overrides=position_overrides,
        rank_inflector=rank_inflector,
        rank_overrides=rank_overrides,
    )
    try:
        rendered = _render_forward(document, context)
    except DyakError as exc:
        report.add(
            FindingKind.ROUNDTRIP_MISMATCH,
            f'обратная сверка не выполнена (рендер шаблона не удался): {exc}',
        )
        return

    rendered_count = 0
    for index, paragraph in enumerate(iter_paragraphs(rendered)):
        rendered_count += 1
        actual = _normalize_ws(flatten_runs(paragraph)[0])
        original = originals[index] if index < len(originals) else ''
        if actual != original:
            report.add(
                FindingKind.ROUNDTRIP_MISMATCH,
                f'ожидалось «{_clip(original)}», получено «{_clip(actual)}»',
            )

    # Рендер выдал меньше параграфов, чем в образце (управляющая разметка
    # `{%p … %}` в образце удалила параграфы) — хвост циклом не покрыт.
    # Пустые исчезнувшие параграфы не считаем потерей данных.
    for original in originals[rendered_count:]:
        if original:
            report.add(
                FindingKind.ROUNDTRIP_MISMATCH,
                f'ожидалось «{_clip(original)}», получено «»',
            )
