"""Тесты конфигурации dyak (T006: опциональный yaml, aliases/overrides)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dyak.config import Config, load_config

_VALID_YAML = """
aliases:
  "Сотрудник": surname
  "Подразделение": position

overrides:
  fio: {}
  position: {}
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / 'dyak.yaml'
    path.write_text(text, encoding='utf-8')
    return path


def test_missing_file_yields_empty_config(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / 'нет.yaml')
    assert isinstance(cfg, Config)
    assert cfg.aliases == {}
    assert cfg.overrides.fio == {}


def test_none_path_yields_empty_config() -> None:
    cfg = load_config(None)
    assert cfg.aliases == {}


def test_load_valid_config(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _VALID_YAML))
    assert cfg.aliases == {'Сотрудник': 'surname', 'Подразделение': 'position'}


def test_empty_file_yields_defaults(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, ''))
    assert cfg.aliases == {}
    assert cfg.overrides.position == {}


def test_invalid_alias_role_rejected(tmp_path: Path) -> None:
    text = 'aliases:\n  "Колонка": неизвестная_роль\n'
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, text))


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, 'columns: {}\n'))
