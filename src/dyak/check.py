"""
Сухой прогон `dyak check` (T004, §8.6, §10, §13).

Рендерит каждую строку таблицы в память (без записи файлов) и собирает
отчёт о потенциальных проблемах ДО генерации сотни документов:

- **undefined** — неизвестная переменная шаблона (`StrictUndefined`);
  фатально (опечатка в теге сломает и `generate`).
- **not_declined** — склоняемое значение (часть ФИО или должность), которое
  ни в одном косвенном падеже не меняется: кандидат на `override` либо
  легитимно несклоняемое (иностранная фамилия) — решает кадровик.
- **gender_ambiguous** — пол не определился (взят мужской по умолчанию).
- **gender_mismatch** — ручной `genders` расходится с уверенным
  авто-определением по отчеству/имени.

Отчёт человекочитаемый; `not_declined`/`gender_*` — предупреждения (код 0),
`undefined` и ошибки чтения таблицы — фатальны (код 1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from dyak.domain import Case
from dyak.errors import TemplateError, UndefinedVariableError
from dyak.inflection import (
    GenderSource,
    NamePart,
    PetrovichInflector,
    Position,
    PymorphyInflector,
)
from dyak.render.context import KEY_FULLNAME, build_context, resolve_row_gender
from dyak.render.engine import render_to_document

if TYPE_CHECKING:
    from pathlib import Path

    from dyak.config import CaseForms
    from dyak.domain import Gender, Person, Table

# Косвенные падежи (именительный не склоняется по определению).
_OBLIQUE = (Case.GENT, Case.DATV, Case.ACCS, Case.ABLT, Case.LOCT)


class IssueKind(StrEnum):
    """Вид находки отчёта."""

    UNDEFINED = 'undefined'  # неизвестная переменная шаблона
    TEMPLATE = 'template'  # прочая ошибка шаблона (напр. `согл` не на ФИО)
    NOT_DECLINED = 'not_declined'
    GENDER_AMBIGUOUS = 'gender_ambiguous'
    GENDER_MISMATCH = 'gender_mismatch'


@dataclass(frozen=True, slots=True)
class Issue:
    """Одна находка: номер строки, вид, человекочитаемое сообщение."""

    row: int
    kind: IssueKind
    message: str


@dataclass(frozen=True, slots=True)
class CheckReport:
    """Результат сухого прогона: находки + число проверенных строк."""

    issues: list[Issue]
    rows: int

    @property
    def ok(self) -> bool:
        """Нет ни одной находки."""
        return not self.issues

    @property
    def fatal(self) -> bool:
        """Есть фатальная проблема (шаблон не рендерится)."""
        fatal_kinds = {IssueKind.UNDEFINED, IssueKind.TEMPLATE}
        return any(issue.kind in fatal_kinds for issue in self.issues)


def _declines(value: NamePart | Position) -> bool:
    """Меняется ли значение хоть в одном косвенном падеже."""
    base = value.text
    return any(value.inflect(case) != base for case in _OBLIQUE)


def _check_declension(row: int, context: dict[str, object]) -> list[Issue]:
    """Найти склоняемые «листья» (части ФИО, должность), которые не склоняются."""
    issues: list[Issue] = []
    for value in context.values():
        if not isinstance(value, (NamePart, Position)):
            continue
        if not value.text or _declines(value):
            continue
        kind = 'должность' if isinstance(value, Position) else 'часть ФИО'
        message = (
            f'не склоняется ({kind}): «{value.text}» — добавьте override, '
            f'если это не иностранное/несклоняемое слово'
        )
        issues.append(Issue(row, IssueKind.NOT_DECLINED, message))
    return issues


def _check_gender(
    row: int,
    person: Person,
    table: Table,
    gender_overrides: dict[str, Gender],
) -> list[Issue]:
    """Проверить уверенность определения пола и расхождение с ручным."""
    actual = resolve_row_gender(
        person,
        roles=table.roles,
        fullname_source=table.fullname_source,
        gender_overrides=gender_overrides,
    )
    if actual.source is GenderSource.DEFAULT:
        return [
            Issue(row, IssueKind.GENDER_AMBIGUOUS, 'пол не определён — взят мужской')
        ]
    if actual.source is GenderSource.OVERRIDE:
        auto = resolve_row_gender(
            person,
            roles=table.roles,
            fullname_source=table.fullname_source,
            gender_overrides={},
        )
        if auto.is_confident and auto.gender is not actual.gender:
            return [
                Issue(
                    row,
                    IssueKind.GENDER_MISMATCH,
                    f'ручной пол ({actual.gender}) расходится с определённым '
                    f'по {auto.source} ({auto.gender})',
                )
            ]
    return []


def check_table(
    table: Table,
    template_path: Path,
    *,
    gender_overrides: dict[str, Gender],
    position_overrides: dict[str, CaseForms],
) -> CheckReport:
    """Сухой прогон: рендер каждой строки в память + сбор отчёта."""
    inflector = PetrovichInflector()
    position_inflector = PymorphyInflector()
    issues: list[Issue] = []
    for row, person in enumerate(table.people, start=1):
        issues.extend(_check_gender(row, person, table, gender_overrides))
        context = build_context(
            person,
            fullname_source=table.fullname_source,
            roles=table.roles,
            inflector=inflector,
            gender_overrides=gender_overrides,
            position_inflector=position_inflector,
            position_overrides=position_overrides,
        )
        try:
            render_to_document(template_path, context)
        except UndefinedVariableError as exc:
            label = str(context.get(KEY_FULLNAME, '')) or f'строка {row}'
            issues.append(Issue(row, IssueKind.UNDEFINED, f'{label}: {exc}'))
            continue
        except TemplateError as exc:
            label = str(context.get(KEY_FULLNAME, '')) or f'строка {row}'
            issues.append(Issue(row, IssueKind.TEMPLATE, f'{label}: {exc}'))
            continue
        issues.extend(_check_declension(row, context))
    return CheckReport(issues=issues, rows=len(table.people))


def format_report(report: CheckReport) -> str:
    """Человекочитаемый отчёт сухого прогона."""
    if report.ok:
        return f'Проверено строк: {report.rows}. Проблем не найдено.'
    header = f'Проверено строк: {report.rows}. Найдено замечаний: {len(report.issues)}.'
    lines = [header]
    lines.extend(f'  [строка {issue.row}] {issue.message}' for issue in report.issues)
    return '\n'.join(lines)
