"""
Рендер имени файла (Jinja) и документа (docxtpl) + автопочинка пробелов.

T006: подстановка идёт по заголовкам колонок. Если пользователь забыл
заменить пробел в заголовке и написал `{{ Дата начала }}`, dyak чинит это
сам (пробел → `_` внутри тега) с предупреждением. Для docx починка работает
на этапе XML-патча docxtpl (после склейки run'ов), поэтому устойчива к
плейсхолдерам, разрезанным Word по run'ам.

Чинятся **только** теги вывода `{{ … }}`, и только если их тело — «голый»
многословный идентификатор (буквы/цифры/`_`/пробелы, без `.`/`|`/прочих
операторов Jinja). Тег с фильтром (`{{ ФИО | рд }}`, появится в T002) или
управляющий блок `{% … %}` не трогаются — там пробелы значимы.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import jinja2
from docxtpl import DocxTemplate

from dyak.errors import UndefinedVariableError
from dyak.render.filters import EMPTY_MARKER, build_jinja_env

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from docx.document import Document
    from docx.table import _Cell
    from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)

# Тег вывода `{{ ... }}` (нежадно, через переводы строк).
_OUTPUT_TAG = re.compile(r'\{\{(.*?)\}\}', re.DOTALL)
# «Голый» многословный идентификатор: только буквы/цифры/`_` и пробелы.
_BARE_MULTIWORD = re.compile(r'[^\W]+(?: +[^\W]+)+', re.UNICODE)
_SPACES = re.compile(r' +')

# Закрывающая пунктуация: перед ней одиночный пробел убирается (T016 фаза C).
_CLOSING_PUNCT = frozenset('.,;:!?»)…')
# Завершающая пунктуация: «висячую» (после пустого значения, в конце параграфа)
# убираем целиком; разделители (`, ;`) сохраняем.
_TERMINATORS = frozenset('.!?…')


def fix_jinja_spaces(text: str) -> str:
    """Починить пробелы в «голых» идентификаторах тегов `{{ … }}` + warning."""

    def repl(match: re.Match[str]) -> str:
        trimmed = match.group(1).strip()
        if _BARE_MULTIWORD.fullmatch(trimmed):
            fixed = _SPACES.sub('_', trimmed)
            logger.warning(
                'Пробел в теге «{{ %s }}» — нормализую в «{{ %s }}»',
                trimmed,
                fixed,
            )
            return '{{ ' + fixed + ' }}'
        return match.group(0)

    return _OUTPUT_TAG.sub(repl, text)


class DyakTemplate(DocxTemplate):
    """`DocxTemplate` с автопочинкой пробелов в тегах на этапе XML-патча."""

    def patch_xml(self, src_xml: str) -> str:
        """Склеить run'ы штатным docxtpl, затем починить пробелы в тегах."""
        return fix_jinja_spaces(super().patch_xml(src_xml))


def default_filename_template(roles: dict[str, str]) -> str | None:
    """
    Дефолтный шаблон имени файла по распознанным колонкам ФИО.

    Возвращает `None`, если ни одна из колонок surname/name/patronymic не
    распознана — тогда вызывающий код использует порядковый запасной вариант.
    """
    parts = [roles[role] for role in ('surname', 'name', 'patronymic') if role in roles]
    if not parts:
        return None
    # `select` отбрасывает пустые части (напр. отсутствующее отчество),
    # поэтому в имени не остаётся хвостовых/сдвоенных подчёркиваний.
    listed = ', '.join(parts)
    return f"{{{{ [{listed}] | select | join('_') }}}}.docx"


def render_filename(template: str, context: dict[str, object]) -> str:
    """Отрендерить шаблон имени выходного файла (с автопочинкой пробелов)."""
    env = build_jinja_env()
    try:
        rendered = env.from_string(fix_jinja_spaces(template)).render(context)
    except jinja2.UndefinedError as exc:
        msg = f'Неизвестная переменная в шаблоне имени файла: {exc}'
        raise UndefinedVariableError(msg) from exc
    # Маркер пустой подстановки не должен попасть в имя файла.
    return rendered.replace(EMPTY_MARKER, '')


def iter_paragraphs(container: Document | _Cell) -> Iterator[Paragraph]:
    """Обойти все параграфы контейнера, включая вложенные таблицы."""
    yield from container.paragraphs
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from iter_paragraphs(cell)


def _mark_empty_substitutions(text: str, keep: list[bool]) -> None:
    """Снять маркеры пустых подстановок; убрать висячую хвостовую пунктуацию."""
    for i, char in enumerate(text):
        if char != EMPTY_MARKER:
            continue
        keep[i] = False  # сам маркер не выводим
        # За пустым значением — пропускаем пробелы; если дальше завершающая
        # пунктуация и до конца параграфа только пробелы, убираем и её
        # («Звание: ▮.» → «Звание:»). Разделители (`, ;`) сохраняем.
        j = i + 1
        while j < len(text) and text[j] == ' ':
            j += 1
        if j < len(text) and text[j] in _TERMINATORS and text[j + 1 :].strip() == '':
            keep[j] = False


def _mark_redundant_spaces(text: str, keep: list[bool]) -> None:
    """Пометить к удалению лишние пробелы среди ещё живых символов."""
    kept = [i for i in range(len(text)) if keep[i]]
    chars = [text[i] for i in kept]
    pos = 0
    while pos < len(chars):
        if chars[pos] != ' ':
            pos += 1
            continue
        end = pos
        while end < len(chars) and chars[end] == ' ':
            end += 1
        edge = pos == 0 or end == len(chars)
        before_punct = end < len(chars) and chars[end] in _CLOSING_PUNCT
        # На краях/перед пунктуацией убираем все пробелы пачки, иначе схлопываем
        # до одного (со второго).
        drop_from = pos if edge or before_punct else pos + 1
        for local in range(drop_from, end):
            keep[kept[local]] = False
        pos = end


def _clean_paragraph(paragraph: Paragraph) -> None:
    """Снять маркеры пустых подстановок и подчистить пробелы (через run'ы)."""
    runs = paragraph.runs
    texts = [run.text for run in runs]
    full = ''.join(texts)
    if EMPTY_MARKER not in full and '  ' not in full and full == full.strip():
        return  # быстрый выход: ни маркеров, ни лишних пробелов
    keep = [True] * len(full)
    _mark_empty_substitutions(full, keep)
    _mark_redundant_spaces(full, keep)
    pos = 0
    for run, text in zip(runs, texts, strict=True):
        end = pos + len(text)
        cleaned = ''.join(
            char for char, alive in zip(text, keep[pos:end], strict=True) if alive
        )
        if cleaned != text:
            run.text = cleaned
        pos = end


def render_to_document(template_path: Path, context: dict[str, object]) -> Document:
    """
    Отрендерить docx-шаблон в память (без записи); вернуть `Document`.

    Общий путь рендера для `generate` (потом `.save`) и `check` (только в
    память). Неизвестная переменная (`StrictUndefined`) → `TemplateError`.
    """
    template = DyakTemplate(template_path)
    try:
        template.render(context, jinja_env=build_jinja_env())
    except jinja2.UndefinedError as exc:
        msg = f'Неизвестная переменная в шаблоне: {exc}'
        raise UndefinedVariableError(msg) from exc
    for paragraph in iter_paragraphs(template.docx):
        _clean_paragraph(paragraph)
    return template.docx


def render_document(
    template_path: Path,
    context: dict[str, object],
    output_path: Path,
) -> None:
    """Отрендерить docx-шаблон, подчистить двойные пробелы и сохранить."""
    document = render_to_document(template_path, context)
    document.save(str(output_path))
