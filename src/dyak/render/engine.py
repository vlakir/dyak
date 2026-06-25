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

import html
import logging
import re
from typing import TYPE_CHECKING

import jinja2
from docxtpl import DocxTemplate

from dyak.columns import normalize_header
from dyak.errors import TemplateError, UndefinedVariableError
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
# Символы DSL/Jinja внутри тега: фильтр `|`, атрибут `.`, вызовы/индексация/
# строки. Тег с любым из них — не «голая ссылка на заголовок», его не трогаем
# (там символы значимы: `{{ ФИО | дт }}`, `{{ ФИО.инициалы }}`, фильтр имени файла).
_DSL_CHARS = frozenset('|.()[]{}\'"')

# Завершающая пунктуация: «висячую» (после пустого значения, в конце параграфа)
# убираем целиком; разделители (`, ;`) сохраняем.
_TERMINATORS = frozenset('.!?…')


def _is_plain_header_tag(content: str) -> bool:
    """Проверить, что тег — «голая» ссылка на заголовок (без фильтра/атрибута)."""
    return bool(content) and not any(ch in _DSL_CHARS for ch in content)


def fix_jinja_spaces(text: str) -> str:
    """
    Нормализовать «голые» теги-ссылки `{{ заголовок }}` под ключи контекста.

    Пробелы и спецсимволы заголовка (`/`, `№`, `-` …) приводятся к `_` той же
    `normalize_header`, что строит ключи контекста, — поэтому `{{ л/н }}` и
    `{{ Дата начала }}` находят свои колонки (иначе Jinja разобрала бы `/` как
    деление, а пробел как два слова). Теги с фильтром (`| дт`), атрибутом
    (`.инициалы`) или вызовом/строкой — НЕ трогаем, там символы значимы.
    """

    def repl(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        if _is_plain_header_tag(content):
            fixed = normalize_header(content)
            if fixed and fixed != content:
                logger.warning(
                    'Тег «{{ %s }}» нормализован в «{{ %s }}» (под заголовок колонки)',
                    content,
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
    except jinja2.TemplateError as exc:
        msg = (
            'Ошибка в разметке шаблона имени файла — проверьте теги «{{ … }}» '
            f'и фильтры падежей («| дт» и т.п.): {exc}'
        )
        raise TemplateError(msg) from exc
    # Общий с телом docx env держит `autoescape=True` (обязателен для XML тела),
    # поэтому `&`/`'`/`<`/`>`/`"` в значении уезжают в `&amp;`/`&#39;`/… Для имени
    # файла HTML-экранирование не нужно — снимаем его обратным `html.unescape`
    # (точный инверс autoescape). Тело docx это не затрагивает: у него свой путь
    # рендера, экранирование там остаётся (T011).
    rendered = html.unescape(rendered)
    # Маркер пустой подстановки не должен попасть в имя файла.
    return rendered.replace(EMPTY_MARKER, '')


def iter_paragraphs(container: Document | _Cell) -> Iterator[Paragraph]:
    """Обойти все параграфы контейнера, включая вложенные таблицы."""
    yield from container.paragraphs
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from iter_paragraphs(cell)


def _mark_empty_cleanup(text: str, keep: list[bool]) -> None:
    """
    Снять маркеры пустых подстановок и подчистить ТОЛЬКО соседние пробелы.

    Область чистки — строго подстановки: убираем сам маркер, схлопываем
    появившийся из-за пустого значения дублированный пробел и снимаем висячую
    хвостовую пунктуацию. Любые ДРУГИЕ пробелы (намеренные, в подписи и т.п.)
    остаются нетронутыми — программа не самодействует вне подстановок.
    """
    n = len(text)
    for i, char in enumerate(text):
        if char != EMPTY_MARKER:
            continue
        keep[i] = False  # сам маркер не выводим
        left_space = i - 1 >= 0 and text[i - 1] == ' '
        j = i + 1
        while j < n and text[j] == ' ':
            j += 1
        right_space = j > i + 1  # за маркером были пробелы
        # Висячая хвостовая пунктуация в конце параграфа («Звание: ▮.» → «Звание:»):
        # убираем её, пробелы до неё и пробел перед маркером.
        if j < n and text[j] in _TERMINATORS and text[j + 1 :].strip() == '':
            keep[j] = False
            for k in range(i + 1, j):
                keep[k] = False
            if left_space:
                keep[i - 1] = False
        elif left_space and right_space:
            keep[i + 1] = False  # «A ▮ C» → «A C» (один дублированный пробел)
        elif right_space:
            keep[i + 1] = False  # «▮ C» в начале → «C»
        elif left_space:
            keep[i - 1] = False  # «A ▮» в конце → «A»


def _clean_paragraph(paragraph: Paragraph) -> None:
    """Снять маркеры пустых подстановок и подчистить соседние пробелы (по run'ам)."""
    runs = paragraph.runs
    texts = [run.text for run in runs]
    full = ''.join(texts)
    if EMPTY_MARKER not in full:
        return  # нет пустых подстановок — текст не трогаем (намеренные пробелы целы)
    keep = [True] * len(full)
    _mark_empty_cleanup(full, keep)
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
    except jinja2.TemplateError as exc:
        msg = (
            'Ошибка в разметке шаблона — проверьте теги «{{ … }}» и фильтры '
            f'падежей («| дт» и т.п.): {exc}'
        )
        raise TemplateError(msg) from exc
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
