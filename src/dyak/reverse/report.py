"""
Отчёт обратной генерации (`dyak reverse`, T007) — по образцу `check.py`.

`reverse` — best-effort инструмент-черновик: он не претендует на 100%
точность, а честно показывает, что заменено уверенно, а что осталось
статикой. Эта честность и живёт в отчёте: каждая находка — отдельная
строка с категорией.

Категории фазы 1 (точные совпадения):

- **replaced** — значение строки уверенно найдено в документе и заменено
  на тег `{{ Заголовок }}`.
- **not_found** — значение строки не встретилось в документе (пустая
  ячейка / иной формат / склонённая форма, которую фаза 1 ещё не ищет).
- **unmatched_text** — фрагмент документа, похожий на данные (дата, номер),
  которому не нашлось пары в строке: либо отсебятина кадровика, либо
  значение в формате, не совпавшем с ячейкой.

Категории `ambiguous`/`roundtrip_mismatch` заведены задельно (фазы 2–3),
в фазе 1 не порождаются.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FindingKind(StrEnum):
    """Вид находки отчёта reverse."""

    REPLACED = 'replaced'
    NOT_FOUND = 'not_found'
    UNMATCHED_TEXT = 'unmatched_text'
    AMBIGUOUS = 'ambiguous'  # задел на фазу 2 (омонимия падежа)
    ROUNDTRIP_MISMATCH = 'roundtrip_mismatch'  # задел на фазу 3


@dataclass(frozen=True, slots=True)
class Finding:
    """Одна находка: вид + человекочитаемое сообщение."""

    kind: FindingKind
    message: str


@dataclass(slots=True)
class ReverseReport:
    """Результат обратной генерации: находки по категориям."""

    findings: list[Finding] = field(default_factory=list)

    def add(self, kind: FindingKind, message: str) -> None:
        """Добавить находку."""
        self.findings.append(Finding(kind, message))

    def of_kind(self, kind: FindingKind) -> list[Finding]:
        """Все находки заданного вида (для тестов/подсчётов)."""
        return [f for f in self.findings if f.kind is kind]

    @property
    def replaced_count(self) -> int:
        """Сколько значений заменено уверенно."""
        return len(self.of_kind(FindingKind.REPLACED))


# Человекочитаемые заголовки секций отчёта (в порядке вывода).
_SECTIONS: tuple[tuple[FindingKind, str], ...] = (
    (FindingKind.REPLACED, 'Заменено'),
    (FindingKind.AMBIGUOUS, 'Под сомнением'),
    (FindingKind.NOT_FOUND, 'Не найдено в документе'),
    (FindingKind.UNMATCHED_TEXT, 'Похоже на данные без пары в строке'),
    (FindingKind.ROUNDTRIP_MISMATCH, 'Расхождение при обратной сверке'),
)


def format_report(report: ReverseReport) -> str:
    """Человекочитаемый отчёт обратной генерации (секциями по категориям)."""
    replaced = report.replaced_count
    other = len(report.findings) - replaced
    header = f'Заменено значений: {replaced}. Прочих замечаний: {other}.'
    lines = [header]
    for kind, title in _SECTIONS:
        section = report.of_kind(kind)
        if not section:
            continue
        lines.append(f'{title}:')
        lines.extend(f'  {finding.message}' for finding in section)
    return '\n'.join(lines)
