"""Тесты конфигурации dyak (этап 0, T001)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dyak.config import Config, load_config

_VALID_YAML = """
columns:
  surname: "Фамилия"
  name: "Имя"
  patronymic: "Отчество"
  position: "Должность"
  gender: "Пол"
  дата_начала: "Дата начала"
  номер_приказа: "Номер приказа"

gender_values:
  male: ["м", "муж", "мужской"]
  female: ["ж", "жен", "женский"]

filename: "Приказ_{{ сотрудник.фамилия }}.docx"

overrides:
  fio: {}
  position: {}
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / 'dyak.yaml'
    path.write_text(text, encoding='utf-8')
    return path


def test_load_valid_config(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _VALID_YAML))
    assert isinstance(cfg, Config)
    assert cfg.columns.surname == 'Фамилия'
    assert cfg.columns.gender == 'Пол'
    assert cfg.filename == 'Приказ_{{ сотрудник.фамилия }}.docx'


def test_extra_columns_are_kept(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _VALID_YAML))
    extra = cfg.columns.extra_fields()
    assert extra == {'дата_начала': 'Дата начала', 'номер_приказа': 'Номер приказа'}


def test_gender_values_parsed(tmp_path: Path) -> None:
    cfg = load_config(_write(tmp_path, _VALID_YAML))
    assert 'муж' in cfg.gender_values.male
    assert 'жен' in cfg.gender_values.female


def test_missing_required_column_rejected(tmp_path: Path) -> None:
    text = _VALID_YAML.replace('  gender: "Пол"\n', '')
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, text))


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    text = _VALID_YAML + '\nнеизвестный_ключ: 42\n'
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, text))


def test_defaults_when_optional_sections_omitted(tmp_path: Path) -> None:
    minimal = """
columns:
  surname: "Фамилия"
  name: "Имя"
  patronymic: "Отчество"
  position: "Должность"
  gender: "Пол"
filename: "{{ сотрудник.фамилия }}.docx"
"""
    cfg = load_config(_write(tmp_path, minimal))
    assert cfg.gender_values.male  # есть дефолтные значения
    assert cfg.overrides.fio == {}
