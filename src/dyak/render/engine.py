"""
Рендер имени файла (Jinja) и документа (docxtpl).

Этап 0 (T001): без падежных фильтров — простая подстановка. В T002
имя файла и документ переводятся на общее Jinja-окружение с русскими
фильтрами склонения (`им/рд/…`, `согл`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jinja2
from docxtpl import DocxTemplate

if TYPE_CHECKING:
    from pathlib import Path


def render_filename(template: str, context: dict[str, object]) -> str:
    """Отрендерить шаблон имени выходного файла."""
    return jinja2.Template(template).render(context)


def render_document(
    template_path: Path,
    context: dict[str, object],
    output_path: Path,
) -> None:
    """Отрендерить docx-шаблон с контекстом и сохранить результат."""
    template = DocxTemplate(template_path)
    template.render(context)
    template.save(output_path)
