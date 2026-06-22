"""
CLI dyak (typer): команды `generate`, `check` (T004) и `init` (T005).

`generate` (T006) — подстановка по заголовкам колонок; `check` — сухой
прогон с отчётом; `init` — выложить стартовый scaffold-набор.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from dyak.check import check_table, format_report
from dyak.config import Config, load_config
from dyak.errors import DyakError
from dyak.inflection import PetrovichInflector, PymorphyInflector, parse_gender
from dyak.io.excel import read_table
from dyak.io.naming import unique_filename
from dyak.progress import GenerateProgress
from dyak.render.context import build_context, normalize_lookup_key
from dyak.render.engine import (
    default_filename_template,
    render_document,
    render_filename,
)
from dyak.scaffolding import init_project

if TYPE_CHECKING:
    from dyak.config import CaseForms
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
            result[normalize_lookup_key(raw_name)] = gender
        else:
            logger.warning(
                'Неизвестное значение пола «%s» для «%s» в секции `genders` — '
                'игнорирую (ожидается м/ж/муж/жен/male/female)',
                raw_value,
                raw_name,
            )
    return result


def _position_overrides(cfg: Config) -> dict[str, CaseForms]:
    """Нормализовать `overrides.position` в `ключ должности → падежные формы`."""
    return {
        normalize_lookup_key(text): forms
        for text, forms in cfg.overrides.position.items()
    }


def generate_documents(
    table: Path,
    template: Path,
    out: Path,
    config: Path | None,
    sheet: str | None,
    filename: str | None,
    *,
    progress_json: bool = False,
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
    position_inflector = PymorphyInflector()
    gender_overrides = _gender_overrides(cfg)
    position_overrides = _position_overrides(cfg)
    used: set[str] = set()
    written: list[Path] = []
    with GenerateProgress(len(data.people), json_events=progress_json) as progress:
        for line, person in enumerate(data.people, start=1):
            context = build_context(
                person,
                fullname_source=data.fullname_source,
                roles=data.roles,
                inflector=inflector,
                gender_overrides=gender_overrides,
                position_inflector=position_inflector,
                position_overrides=position_overrides,
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
            progress.advance(name)

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
    *,
    progress_json: Annotated[
        bool,
        typer.Option(
            '--progress-json',
            help='Машиночитаемый прогресс (JSONL-события) в stderr — для GUI',
        ),
    ] = False,
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
            progress_json=progress_json,
        )
    except DyakError as exc:
        typer.echo(f'Ошибка: {exc}', err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f'Готово: {len(written)} документ(ов) в {out}')


@app.command()
def check(
    table: Annotated[
        Path,
        typer.Option(help='Таблица данных (xlsx)', exists=True, dir_okay=False),
    ],
    template: Annotated[
        Path,
        typer.Option(help='Шаблон документа (docx)', exists=True, dir_okay=False),
    ],
    config: Annotated[
        Path | None,
        typer.Option(help='Опциональный dyak.yaml (по умолчанию ./dyak.yaml)'),
    ] = None,
    sheet: Annotated[
        str | None,
        typer.Option(help='Имя листа (по умолчанию активный)'),
    ] = None,
) -> None:
    """Сухой прогон: проверить склонение/пол/шаблон без записи файлов."""
    try:
        cfg = load_config(config or _DEFAULT_CONFIG)
        data = read_table(table, cfg, sheet)
        report = check_table(
            data,
            template,
            gender_overrides=_gender_overrides(cfg),
            position_overrides=_position_overrides(cfg),
        )
    except DyakError as exc:
        typer.echo(f'Ошибка: {exc}', err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(format_report(report))
    if report.fatal:
        raise typer.Exit(code=1)


@app.command()
def init(
    directory: Annotated[
        Path | None,
        typer.Option(
            '--dir',
            help='Каталог для scaffold-набора (по умолчанию текущий)',
        ),
    ] = None,
    *,
    force: Annotated[
        bool,
        typer.Option('--force', help='Перезаписать существующие файлы'),
    ] = False,
) -> None:
    """Выложить стартовый набор: dyak.yaml + пример шаблона + пример таблицы."""
    target = directory if directory is not None else Path.cwd()
    try:
        created = init_project(target, force=force)
    except DyakError as exc:
        typer.echo(f'Ошибка: {exc}', err=True)
        raise typer.Exit(code=1) from exc
    typer.echo('Создан стартовый набор dyak:')
    for path in created:
        typer.echo(f'  {path}')
    typer.echo(
        '\nДальше: отредактируйте table.xlsx и template.docx под себя '
        '(в шаблоне удалите блок «ШПАРГАЛКА»), затем\n'
        '  dyak generate --table table.xlsx --template template.docx --out out',
    )


if __name__ == '__main__':
    app()
