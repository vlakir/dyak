"""
Распознавание ролей колонок таблицы (T006 + контентная эвристика T016).

Контекст шаблона строится напрямую по заголовкам колонок: заголовок
нормализуется (пробелы → `_`) и становится ключом Jinja-переменной.
Стандартные кадровые колонки (фамилия/имя/отчество/должность/звание/личный
номер) дополнительно получают «роль» — это фундамент маршрутизации склонения
(T002–T003). Источники роли по приоритету:

1. **`aliases`** из `dyak.yaml` — ручной override, абсолютный верх.
2. **Заголовок-синоним** — статический словарь `_SYNONYMS`.
3. **Содержимое ячеек (T016)** — когда заголовок незнаком, роль определяется
   по образцам (грамемы `Surn`/`Name`/`Patr` из `pymorphy3`, словарь маркеров
   званий, парсинг дат/кодов). Уверенный контент может **перебить**
   заголовок-синоним при единогласном расхождении (ловит ошибку разметки),
   иначе заголовок главнее.

Контент-распознавание — **fallback**: без образцов (`samples` пуст) поведение
ровно как в T006 (только заголовок), поэтому существующие таблицы не
регрессируют.

Отдельный случай — **одна колонка «ФИО»**: она распознаётся как `fullname` и
разбирается на фамилию/имя/отчество (`split_fullname`). Тогда в контексте
доступны и целое `{{ ФИО }}`, и производные `{{ Фамилия }}`/`{{ Имя }}`/
`{{ Отчество }}`.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dyak.inflection.morph import get_analyzer

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pymorphy3 import MorphAnalyzer

logger = logging.getLogger(__name__)

# Роли склоняемых/служебных кадровых колонок (совпадают с `Role` в config.py).
SURNAME = 'surname'
NAME = 'name'
PATRONYMIC = 'patronymic'
POSITION = 'position'
FULLNAME = 'fullname'
RANK = 'rank'  # воинское/служебное звание (склоняемое, движок — фаза B)
PERSONAL_NUMBER = 'personal_number'  # личный номер — несклоняемый, буквально

# Внутренний маркер «колонка похожа на даты» — ролью склонения не становится,
# но защищает дату от ложного зачисления в текстовую роль (должность).
_DATE = 'date'

# Канонические ключи контекста для частей ФИО, разобранных из одной колонки.
KEY_SURNAME = 'Фамилия'
KEY_NAME = 'Имя'
KEY_PATRONYMIC = 'Отчество'

# Синонимы заголовков → роль (нормализованный заголовок в нижнем регистре).
_SYNONYMS = {
    'фамилия': SURNAME,
    'имя': NAME,
    'отчество': PATRONYMIC,
    'должность': POSITION,
    'позиция': POSITION,
    'звание': RANK,
    'воинское_звание': RANK,
    'личный_номер': PERSONAL_NUMBER,
    'фио': FULLNAME,
    'ф.и.о.': FULLNAME,
    'ф.и.о': FULLNAME,
    'фамилия_имя_отчество': FULLNAME,
}

# Роли, которые покрывает разбор одной колонки «ФИО».
_FIO_PARTS = frozenset({SURNAME, NAME, PATRONYMIC})

# Вершинные слова воинских/служебных званий (нижний регистр). Полное звание —
# «майор медицинской службы», «капитан 3 ранга», «контр-адмирал» — опознаётся,
# если ЛЮБОЕ слово (или дефисная часть) ячейки попало сюда.
_RANK_MARKERS = frozenset({
    'рядовой', 'ефрейтор', 'матрос', 'солдат', 'курсант', 'юнкер',
    'сержант', 'старшина', 'старший', 'младший',
    'прапорщик', 'мичман',
    'лейтенант', 'капитан', 'майор', 'подполковник', 'полковник',
    'генерал', 'адмирал', 'маршал',
    'комиссар', 'комдив', 'комбриг',
})  # fmt: skip

_WHITESPACE = re.compile(r'\s+')
_WORD_SPLIT = re.compile(r'[\s\-]+')

# Маска «личного номера»: код из цифр/букв (минимум одна цифра), без пробелов
# в середине: «1234567», «АА-123456», «П-045678».
_PERSONAL_NUMBER_RE = re.compile(r'^[A-ZА-Я]{0,4}[-/]?\d[\dA-ZА-Я\-/]*$', re.IGNORECASE)

# Маска даты: «12.05.2020», «2020-05-12», «12/05/20», «12.05» — чтобы не зачислить
# колонку дат в текстовую роль (должность). Точность парсинга не важна — важно,
# что колонка «датоподобна».
_DATE_RE = re.compile(r'^\d{1,2}[.\-/]\d{1,2}([.\-/]\d{2,4})?$|^\d{4}-\d{1,2}-\d{1,2}$')

# Диапазон числа слов, при котором ячейка может быть целым ФИО.
_FIO_MIN_WORDS = 2
_FIO_MAX_WORDS = 4

# Минимальный score разбора pymorphy с name-грамемой, чтобы доверять роли.
_NAME_SCORE_MIN = 0.3
# Доля согласных образцов, при которой контентная роль считается уверенной.
_CONTENT_MIN_RATIO = 0.6
# Минимум образцов, чтобы единогласный контент мог перебить заголовок-синоним.
_MIN_OVERRIDE_SAMPLES = 3


@dataclass(frozen=True, slots=True)
class Recognition:
    """
    Результат распознавания колонок.

    `roles` — `роль → ключ контекста` (физический заголовок или, для разбора
    ФИО, канонический `Фамилия`/`Имя`/`Отчество`). `fullname_source` — ключ
    колонки «ФИО», которую надо разбирать построчно, либо `None`.
    """

    roles: dict[str, str]
    fullname_source: str | None


@dataclass(frozen=True, slots=True)
class ContentGuess:
    """Догадка о роли колонки по содержимому: роль, единогласие, уверенность."""

    role: str | None  # лучшая роль склонения (None — дата/нет образцов)
    unanimous: bool  # все классифицированные образцы дали одну метку
    confident: bool  # доля победителя ≥ `_CONTENT_MIN_RATIO`
    n: int  # сколько непустых образцов классифицировано


def normalize_header(raw: str) -> str:
    """Привести заголовок к Jinja-идентификатору: пробелы → подчёркивание."""
    return _WHITESPACE.sub('_', raw.strip())


def split_fullname(value: str) -> tuple[str, str, str]:
    """
    Разобрать ячейку «ФИО» на (фамилия, имя, отчество).

    Три слова → полное ФИО; два → без отчества (пустое); одно → только
    фамилия. Лишние слова (4-е и далее) приклеиваются к отчеству.
    """
    surname, *rest = value.split() or ['']
    name = rest[0] if rest else ''
    patronymic = ' '.join(rest[1:])
    return surname, name, patronymic


def _is_rank(text: str) -> bool:
    """Похоже ли значение на звание (любое слово/дефисная часть — маркер)."""
    return any(
        part.lower() in _RANK_MARKERS for part in _WORD_SPLIT.split(text) if part
    )


def _is_date(text: str) -> bool:
    """Похоже ли значение на дату (по маске разделителей)."""
    return _DATE_RE.match(text) is not None


def _name_role(word: str, morph: MorphAnalyzer) -> str | None:
    """
    Роль одиночного слова по name-грамемам pymorphy (`Surn`/`Name`/`Patr`).

    Берём максимальный score разбора с каждой грамемой и выбираем сильнейшую;
    если он ниже порога (слово — обычное существительное) — `None`.
    """
    best: dict[str, float] = {}
    for parsed in morph.parse(word):
        for grammeme, role in (('Surn', SURNAME), ('Name', NAME), ('Patr', PATRONYMIC)):
            if grammeme in parsed.tag:
                best[role] = max(best.get(role, 0.0), parsed.score)
    if not best:
        return None
    role = max(best, key=lambda key: best[key])
    return role if best[role] >= _NAME_SCORE_MIN else None


def _cell_name_role(words: list[str], morph: MorphAnalyzer) -> str | None:
    """Роль по name-грамемам: целое ФИО (Surn+Name) или одиночная часть."""
    if (
        _FIO_MIN_WORDS <= len(words) <= _FIO_MAX_WORDS
        and _name_role(words[0], morph) == SURNAME
        and _name_role(words[1], morph) == NAME
    ):
        return FULLNAME
    if len(words) == 1:
        return _name_role(words[0], morph)
    return None


def _classify_cell(value: str, morph: MorphAnalyzer) -> str | None:
    """Классифицировать одну ячейку в роль-кандидат (или `None` для пустой)."""
    text = value.strip()
    if not text:
        return None
    if _is_rank(text):
        return RANK
    if _is_date(text):
        return _DATE
    role = _cell_name_role(text.split(), morph)
    if role is not None:
        return role
    if _PERSONAL_NUMBER_RE.match(text):
        return PERSONAL_NUMBER
    return POSITION  # текст без name-грамем — кандидат на должность


def infer_role(samples: list[str], morph: MorphAnalyzer) -> ContentGuess:
    """
    Определить роль колонки по образцам ячеек (мажоритарным голосованием).

    Возвращает `ContentGuess` с лучшей ролью, флагом единогласия и
    уверенности. Победитель `date` → `role=None` (дата ролью не становится).
    """
    classified = [c for c in (_classify_cell(s, morph) for s in samples) if c]
    if not classified:
        return ContentGuess(role=None, unanimous=False, confident=False, n=0)
    votes = Counter(classified)
    winner, count = votes.most_common(1)[0]
    n = len(classified)
    return ContentGuess(
        role=None if winner == _DATE else winner,
        unanimous=len(votes) == 1,
        confident=count / n >= _CONTENT_MIN_RATIO,
        n=n,
    )


def _decide_role(
    header: str,
    alias_role: str | None,
    header_role: str | None,
    guess: ContentGuess | None,
) -> str | None:
    """Выбрать роль колонки по приоритету alias > заголовок/контент."""
    if alias_role is not None:
        return alias_role
    if header_role is not None:
        if (
            guess is not None
            and guess.role is not None
            and guess.role != header_role
            and guess.unanimous
            and guess.n >= _MIN_OVERRIDE_SAMPLES
        ):
            logger.warning(
                'Заголовок «%s» указывает на роль «%s», но содержимое единогласно '
                '(%d образцов) — на «%s»; беру содержимое',
                header,
                header_role,
                guess.n,
                guess.role,
            )
            return guess.role
        return header_role
    if guess is None or guess.role is None:
        return None  # незнакомый заголовок без образцов/сигнала — обычная строка
    if not guess.confident:
        logger.warning(
            'Роль колонки «%s» определена по содержимому неуверенно — беру лучшую '
            'догадку «%s» (%d образцов); уточните `aliases` при необходимости',
            header,
            guess.role,
            guess.n,
        )
    return guess.role


def recognize(
    headers: list[str],
    aliases: Mapping[str, str],
    samples: Mapping[str, list[str]] | None = None,
) -> Recognition:
    """
    Сопоставить нормализованным заголовкам роли (surname/name/position/...).

    `headers` — нормализованные ключи колонок. `aliases` — из конфига (сырой
    заголовок → роль). `samples` — образцы ячеек (`ключ → значения`) для
    контентной эвристики T016; без него (или пустой) распознаём только по
    заголовку (поведение T006, без обращения к pymorphy). Первый заголовок,
    претендующий на роль, закрепляет её; повторные кандидаты на ту же роль
    игнорируются с предупреждением. Колонка `fullname` разбирается на части,
    только если нет отдельных колонок фамилии/имени/отчества.
    """
    alias_map = {normalize_header(k).lower(): v for k, v in aliases.items()}
    samples = samples or {}
    morph = get_analyzer() if samples else None

    raw: dict[str, str] = {}
    for header in headers:
        key = header.lower()
        guess = (
            infer_role(samples.get(header, []), morph) if morph is not None else None
        )
        role = _decide_role(header, alias_map.get(key), _SYNONYMS.get(key), guess)
        if role is None:
            continue
        if role in raw:
            logger.warning(
                'Колонка «%s» претендует на роль «%s», уже занятую колонкой «%s» — '
                'игнорирую',
                header,
                role,
                raw[role],
            )
            continue
        raw[role] = header

    fullname_source = raw.pop(FULLNAME, None)
    roles = dict(raw)
    if fullname_source is not None and not (_FIO_PARTS & roles.keys()):
        roles[SURNAME] = KEY_SURNAME
        roles[NAME] = KEY_NAME
        roles[PATRONYMIC] = KEY_PATRONYMIC
    elif fullname_source is not None:
        # Есть отдельные колонки ФИО — колонку «ФИО» не разбираем, она
        # остаётся доступной как целый тег `{{ ФИО }}`.
        logger.warning(
            'Колонка «%s» и отдельные колонки фамилии/имени/отчества заданы '
            'одновременно — «%s» не разбираю, доступна целиком',
            fullname_source,
            fullname_source,
        )
        fullname_source = None
    return Recognition(roles=roles, fullname_source=fullname_source)
