"""
Конфигурация dyak: pydantic-схема и загрузка YAML.

Соответствует разделу §9 ТЗ (`CONCEPT.md`). На этапе 0 (T001) реально
используются `columns` и `filename`; `gender_values` и `overrides`
валидируются для стабильности формата между этапами, но поведение к ним
подключается в T002–T003.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pathlib import Path

# Дефолтные распознаваемые значения колонки пола (§9).
_DEFAULT_MALE = ['м', 'муж', 'мужской']
_DEFAULT_FEMALE = ['ж', 'жен', 'женский']

# Падежные формы одного слова: русское сокращение падежа → форма.
CaseForms = dict[str, str]


class ColumnMap(BaseModel):
    """
    Маппинг доменных полей на заголовки колонок таблицы.

    Пять полей обязательны; любые дополнительные колонки (даты, номера
    приказов и т.п.) допускаются и доступны в шаблоне по русскому
    имени-ключу.
    """

    model_config = ConfigDict(extra='allow')

    surname: str
    name: str
    patronymic: str
    position: str
    gender: str

    def extra_fields(self) -> dict[str, str]:
        """Дополнительные колонки сверх обязательных пяти."""
        return {key: str(value) for key, value in (self.model_extra or {}).items()}


class GenderValues(BaseModel):
    """Распознавание значений колонки пола."""

    model_config = ConfigDict(extra='forbid')

    male: list[str] = Field(default_factory=lambda: list(_DEFAULT_MALE))
    female: list[str] = Field(default_factory=lambda: list(_DEFAULT_FEMALE))


class Overrides(BaseModel):
    """Ручные формы склонения (§7.3). Задел на T002–T003."""

    model_config = ConfigDict(extra='forbid')

    fio: dict[str, CaseForms] = Field(default_factory=dict)
    position: dict[str, CaseForms] = Field(default_factory=dict)


class Config(BaseModel):
    """Корневая конфигурация (`dyak.yaml`)."""

    model_config = ConfigDict(extra='forbid')

    columns: ColumnMap
    filename: str
    gender_values: GenderValues = Field(default_factory=GenderValues)
    overrides: Overrides = Field(default_factory=Overrides)


def load_config(path: Path) -> Config:
    """Прочитать и провалидировать `dyak.yaml`."""
    raw = yaml.safe_load(path.read_text(encoding='utf-8'))
    return Config.model_validate(raw)
