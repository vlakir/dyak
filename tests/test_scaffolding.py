"""Тесты `dyak init` — scaffold нового проекта (T005)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from docx import Document
from typer.testing import CliRunner

from dyak.cli import app
from dyak.errors import DyakError
from dyak.scaffolding import SCAFFOLD_FILES, ScaffoldExistsError, init_project

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def test_init_creates_full_set(tmp_path: Path) -> None:
    created = init_project(tmp_path, force=False)

    assert [path.name for path in created] == list(SCAFFOLD_FILES)
    for name in SCAFFOLD_FILES:
        asset = tmp_path / name
        assert asset.exists()
        assert asset.stat().st_size > 0


def test_init_creates_missing_target_dir(tmp_path: Path) -> None:
    target = tmp_path / 'nested' / 'project'

    init_project(target, force=False)

    assert (target / 'dyak.yaml').exists()


def test_init_target_is_file_raises_dyak_error(tmp_path: Path) -> None:
    target = tmp_path / 'file.txt'
    target.write_text('x', encoding='utf-8')

    # Путь существует как файл → доменная ошибка, а не сырой OSError/трейсбек.
    with pytest.raises(DyakError, match='не является каталогом'):
        init_project(target, force=False)


def test_init_mkdir_failure_raises_dyak_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_: object, **__: object) -> None:
        raise PermissionError(13, 'Permission denied')

    monkeypatch.setattr('pathlib.Path.mkdir', boom)
    # OSError от mkdir заворачивается в DyakError (чистое сообщение в CLI).
    with pytest.raises(DyakError, match='Не удалось создать каталог'):
        init_project(tmp_path / 'sub', force=False)


def test_init_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    (tmp_path / 'dyak.yaml').write_text('mine', encoding='utf-8')

    with pytest.raises(ScaffoldExistsError, match='dyak.yaml'):
        init_project(tmp_path, force=False)


def test_init_collision_does_not_partially_write(tmp_path: Path) -> None:
    # Существует только один файл — остальные НЕ должны появиться при отказе.
    (tmp_path / 'dyak.yaml').write_text('mine', encoding='utf-8')

    with pytest.raises(ScaffoldExistsError):
        init_project(tmp_path, force=False)

    assert not (tmp_path / 'template.docx').exists()
    assert not (tmp_path / 'table.xlsx').exists()
    assert (tmp_path / 'dyak.yaml').read_text(encoding='utf-8') == 'mine'


def test_init_force_overwrites(tmp_path: Path) -> None:
    (tmp_path / 'dyak.yaml').write_text('mine', encoding='utf-8')

    init_project(tmp_path, force=True)

    assert (tmp_path / 'dyak.yaml').read_text(encoding='utf-8') != 'mine'


def test_cli_init_succeeds(tmp_path: Path) -> None:
    result = runner.invoke(app, ['init', '--dir', str(tmp_path)])

    assert result.exit_code == 0
    assert 'Создан стартовый набор' in result.stdout
    for name in SCAFFOLD_FILES:
        assert (tmp_path / name).exists()


def test_cli_init_collision_exits_nonzero(tmp_path: Path) -> None:
    (tmp_path / 'table.xlsx').write_text('mine', encoding='utf-8')

    result = runner.invoke(app, ['init', '--dir', str(tmp_path)])

    assert result.exit_code == 1
    assert 'table.xlsx' in result.stderr


def test_init_then_generate_roundtrip(tmp_path: Path) -> None:
    # Acceptance T005: сразу после init пример прогоняется и даёт документы.
    init_project(tmp_path, force=False)
    out_dir = tmp_path / 'out'

    result = runner.invoke(
        app,
        [
            'generate',
            '--table',
            str(tmp_path / 'table.xlsx'),
            '--template',
            str(tmp_path / 'template.docx'),
            '--out',
            str(out_dir),
        ],
    )

    assert result.exit_code == 0
    docs = sorted(out_dir.glob('*.docx'))
    assert len(docs) == 3

    text = '\n'.join(p.text for p in Document(docs[0]).paragraphs)
    # Пример склонился (винительный + родительный должности)…
    assert 'Иванова Петра Семёновича' in text
    assert 'директора' in text
    # …а блок-шпаргалка остался буквальным ({% raw %}), не выполнился.
    assert '{{ ФИО | рд }}' in text
