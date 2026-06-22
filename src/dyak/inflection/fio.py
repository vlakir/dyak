"""
Склоняемые доменные объекты ФИО (§6 «Fio», §8.2).

`NamePart` — одна часть (фамилия/имя/отчество): склоняется и в шаблоне
рендерится именительной формой (`__str__`). `Fio` — агрегат трёх частей:
склоняет всё ФИО разом и отдаёт инициалы в трёх формах. `Initials` —
склоняемое представление инициалов: фамилия склоняется, имя/отчество
сворачиваются в букву с точкой, поэтому `{{ ФИО.инициалы | рд }}` даёт
«Иванова П. С.».

Все три реализуют порт `Declinable` (`.inflect(case)`), поэтому падежные
фильтры работают с ними единообразно.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from dyak.domain import Case, Gender

if TYPE_CHECKING:
    from dyak.inflection.petrovich_fio import PetrovichInflector

# Вид части ФИО — выбирает метод склонения в `PetrovichInflector`.
NameKind = Literal['surname', 'name', 'patronymic']

# Имя атрибута инициалов в шаблоне → (порядок «фамилия/инициалы», слитно ли).
_INITIALS_FORMS: dict[str, tuple[Literal['after', 'before'], bool]] = {
    'инициалы': ('after', False),  # Иванов П. С.
    'инициалы_впереди': ('before', False),  # П. С. Иванов
    'инициалы_слитно': ('after', True),  # Иванов П.С.
}


@dataclass(frozen=True, slots=True)
class NamePart:
    """Часть ФИО: текст + пол + вид. `__str__` — именительная форма."""

    text: str
    kind: NameKind
    gender: Gender
    inflector: PetrovichInflector

    def inflect(self, case: Case) -> str:
        """Вернуть часть в падеже `case` (пустая часть → пустая строка)."""
        return self.inflector.inflect(self.text, self.kind, case, self.gender)

    def __str__(self) -> str:
        return self.text

    def __bool__(self) -> bool:
        # Пустая часть (нет отчества) — falsy, чтобы Jinja `select` отбрасывал
        # её в дефолтном имени файла (без хвостовых подчёркиваний).
        return bool(self.text)


@dataclass(frozen=True, slots=True)
class Fio:
    """Полное ФИО из трёх частей: склоняется целиком, даёт инициалы."""

    surname: NamePart
    name: NamePart
    patronymic: NamePart

    def inflect(self, case: Case) -> str:
        """Склонённое полное ФИО; пустые части (нет отчества) опускаются."""
        parts = (
            self.surname.inflect(case),
            self.name.inflect(case),
            self.patronymic.inflect(case),
        )
        return ' '.join(part for part in parts if part)

    def __str__(self) -> str:
        return self.inflect(Case.NOMN)

    @property
    def gender(self) -> Gender:
        """Пол ФИО (общий для всех частей) — нужен фильтру согласования `согл`."""
        return self.surname.gender

    def __getattr__(self, name: str) -> Initials:
        """
        Доступ к инициалам по русским именам из шаблона (`{{ ФИО.инициалы }}`).

        Кириллические имена живут в DSL шаблона, а не в Python-коде:
        `инициалы` → «Иванов П. С.», `инициалы_впереди` → «П. С. Иванов»,
        `инициалы_слитно` → «Иванов П.С.» (для имён файлов). Прочие имена —
        обычный `AttributeError` (важно для dataclass/copy/pickle).
        """
        spec = _INITIALS_FORMS.get(name)
        if spec is None:
            msg = f'{type(self).__name__!r} object has no attribute {name!r}'
            raise AttributeError(msg)
        order, joined = spec
        return Initials(fio=self, order=order, joined=joined)


@dataclass(frozen=True, slots=True)
class Initials:
    """Инициалы: фамилия склоняется, имя/отчество → буква с точкой."""

    fio: Fio
    order: Literal['after', 'before']
    joined: bool

    def inflect(self, case: Case) -> str:
        """Собрать инициалы в падеже `case`."""
        surname = self.fio.surname.inflect(case)
        letters = [
            f'{part.text[0].upper()}.'
            for part in (self.fio.name, self.fio.patronymic)
            if part.text
        ]
        separator = '' if self.joined else ' '
        initials = separator.join(letters)
        if not surname:
            return initials
        if not initials:
            return surname
        if self.order == 'before':
            return f'{initials} {surname}'
        return f'{surname} {initials}'

    def __str__(self) -> str:
        return self.inflect(Case.NOMN)
