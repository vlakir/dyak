"""
Конфигурация dyak: pydantic-схема и загрузка YAML.

С T006 (ADR 2026-06-21) подстановка идёт напрямую по заголовкам колонок,
поэтому `dyak.yaml` стал **опциональным**: обязательный маппинг `columns`,
шаблон `filename` и колонка `gender` упразднены. Остаются две опциональные
секции:

- `aliases` — нестандартный заголовок → роль (surname/name/patronymic/
  position) для распознавания склоняемых колонок;
- `overrides` — ручные формы склонения (потребляются в T002–T003).

Если файла нет — используется пустая конфигурация (нулевой порог входа).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from pathlib import Path

# Роль склоняемой/служебной колонки (совпадает с константами в columns.py).
# `fullname` — одна колонка «ФИО», разбираемая на фамилию/имя/отчество;
# `rank` — звание (склоняемое, движок — фаза B T016); `personal_number` —
# личный номер (несклоняемый, подставляется буквально).
Role = Literal[
    'surname', 'name', 'patronymic', 'position', 'fullname', 'rank', 'personal_number'
]

# Падежные формы одного слова: русское сокращение падежа → форма.
CaseForms = dict[str, str]


class Overrides(BaseModel):
    """Ручные формы склонения (§7.3). `rank` — звания (T016 фаза B)."""

    model_config = ConfigDict(extra='forbid')

    fio: dict[str, CaseForms] = Field(default_factory=dict)
    position: dict[str, CaseForms] = Field(default_factory=dict)
    rank: dict[str, CaseForms] = Field(default_factory=dict)


class Config(BaseModel):
    """
    Корневая конфигурация (`dyak.yaml`), целиком опциональная.

    `aliases` — привязка нестандартных заголовков к ролям; `overrides` —
    ручные формы склонения для T002–T003.
    """

    model_config = ConfigDict(extra='forbid')

    aliases: dict[str, Role] = Field(default_factory=dict)
    overrides: Overrides = Field(default_factory=Overrides)
    # Ручное указание пола для неоднозначных имён (T002): ФИО (как в таблице)
    # → `м`/`ж`/`male`/`female`. Перекрывает автоопределение по отчеству/имени.
    genders: dict[str, str] = Field(default_factory=dict)


def load_config(path: Path | None) -> Config:
    """Прочитать `dyak.yaml`; при отсутствии файла вернуть пустой конфиг."""
    if path is None or not path.exists():
        return Config()
    raw = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return Config.model_validate(raw)
