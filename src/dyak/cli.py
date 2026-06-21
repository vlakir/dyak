"""
CLI dyak (typer). T006: команда `generate` — подстановка по заголовкам колонок.

Команды `check` и `init` появляются в T004/T005.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from dyak.config import Config, load_config
from dyak.errors import DyakError
from dyak.inflection import PetrovichInflector, parse_gender
from dyak.io.excel import read_table
from dyak.io.naming import unique_filename
from dyak.render.context import build_context, normalize_fullname_key
from dyak.render.engine import (
    default_filename_template,
    render_document,
    render_filename,
)

if TYPE_CHECKING:
    from dyak.domain import Gender

logger = logging.getLogger(__name__)

app = typer.Typer(
    help='dyak — генератор кадровых документов с русским склонением.',
    add_completion=False,
)

_DEFAULT_CONFIG = Path('dyak.yaml')


@app.callback()
def _main() -> None:
    """Dyak — пакетная генерация кадровых документов с русским склонением."""


def _gender_overrides(cfg: Config) -> dict[str, Gender]:
    """Нормализовать секцию `genders` конфига в `ключ ФИО → Gender`."""
    result: dict[str, Gender] = {}
    for raw_name, raw_value in cfg.genders.items():
        gender = parse_gender(raw_value)
        if gender is not None:
            result[normalize_fullname_key(raw_name)] = gender
        else:
            logger.warning(
                'Неизвестное значение пола «%s» для «%s» в секции `genders` — '
                'игнорирую (ожидается м/ж/муж/жен/male/female)',
                raw_value,
                raw_name,
            )
    return result


def generate_documents(
    table: Path,
    template: Path,
    out: Path,
    config: Path | None,
    sheet: str | None,
    filename: str | None,
) -> list[Path]:
    """Сгенерировать по документу на строку таблицы. Вернуть пути файлов."""
    cfg = load_config(config)
    data = read_table(table, cfg, sheet)
    out.mkdir(parents=True, exist_ok=True)

    name_template = filename or default_filename_template(data.roles)
    if name_template is None:
        logger.warning(
            'Не заданы --filename и не распознаны колонки ФИО — '
            'имена файлов будут порядковыми (Документ_N.docx)',
        )

    inflector = PetrovichInflector()
    gender_overrides = _gender_overrides(cfg)
    used: set[str] = set()
    written: list[Path] = []
    for line, person in enumerate(data.people, start=1):
        context = build_context(
            person,
            fullname_source=data.fullname_source,
            roles=data.roles,
            inflector=inflector,
            gender_overrides=gender_overrides,
        )
        base = (
            f'Документ_{line}.docx'
            if name_template is None
            else render_filename(name_template, context)
        )
        name = unique_filename(base, used)
        target = out / name
        render_document(template, context, target)
        written.append(target)

    logger.info('Сгенерировано документов: %d → %s', len(written), out)
    return written


@app.command()
def generate(
    table: Annotated[
        Path,
        typer.Option(help='Таблица данных (xlsx)', exists=True, dir_okay=False),
    ],
    template: Annotated[
        Path,
        typer.Option(help='Шаблон документа (docx)', exists=True, dir_okay=False),
    ],
    out: Annotated[Path, typer.Option(help='Каталог для результатов')],
    config: Annotated[
        Path | None,
        typer.Option(help='Опциональный dyak.yaml (по умолчанию ./dyak.yaml)'),
    ] = None,
    sheet: Annotated[
        str | None,
        typer.Option(help='Имя листа (по умолчанию активный)'),
    ] = None,
    filename: Annotated[
        str | None,
        typer.Option(
            help='Шаблон имени файла (по умолчанию по колонкам ФИО), '
            'напр. "Приказ_{{ Номер_приказа }}_{{ Фамилия }}.docx"',
        ),
    ] = None,
) -> None:
    """Сгенерировать набор документов из таблицы и шаблона."""
    try:
        written = generate_documents(
            table,
            template,
            out,
            config or _DEFAULT_CONFIG,
            sheet,
            filename,
        )
    except DyakError as exc:
        typer.echo(f'Ошибка: {exc}', err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f'Готово: {len(written)} документ(ов) в {out}')


if __name__ == '__main__':
    app()
