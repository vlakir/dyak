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

from docxtpl import DocxTemplate

from dyak.render.filters import build_jinja_env

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
# Два и более подряд идущих пробела (для чистки после пустых подстановок).
_MULTISPACE = re.compile(r' {2,}')


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
    return env.from_string(fix_jinja_spaces(template)).render(context)


def _iter_paragraphs(container: Document | _Cell) -> Iterator[Paragraph]:
    """Обойти все параграфы контейнера, включая вложенные таблицы."""
    yield from container.paragraphs
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_paragraphs(cell)


def _collapse_paragraph_spaces(paragraph: Paragraph) -> None:
    """Схлопнуть сдвоенные пробелы в параграфе (в т.ч. на стыке run'ов)."""
    in_space = False
    for run in paragraph.runs:
        if not run.text:
            continue
        text = _MULTISPACE.sub(' ', run.text)
        if in_space:
            text = text.lstrip(' ')
        run.text = text
        if text:
            in_space = text.endswith(' ')


def render_document(
    template_path: Path,
    context: dict[str, object],
    output_path: Path,
) -> None:
    """Отрендерить docx-шаблон, подчистить двойные пробелы и сохранить."""
    template = DyakTemplate(template_path)
    template.render(context, jinja_env=build_jinja_env())
    for paragraph in _iter_paragraphs(template.docx):
        _collapse_paragraph_spaces(paragraph)
    template.save(output_path)
