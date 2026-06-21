"""Тесты разрешения коллизий имён выходных файлов (этап 0, T001)."""

from __future__ import annotations

import logging

import pytest

from dyak.io.naming import unique_filename


def test_free_name_unchanged() -> None:
    used: set[str] = set()
    assert unique_filename('Приказ_Иванов.docx', used) == 'Приказ_Иванов.docx'
    assert 'Приказ_Иванов.docx' in used


def test_collision_gets_numeric_suffix() -> None:
    used: set[str] = set()
    first = unique_filename('Приказ.docx', used)
    second = unique_filename('Приказ.docx', used)
    third = unique_filename('Приказ.docx', used)
    assert first == 'Приказ.docx'
    assert second == 'Приказ_2.docx'
    assert third == 'Приказ_3.docx'


def test_suffix_preserves_extension() -> None:
    used = {'doc.docx'}
    assert unique_filename('doc.docx', used) == 'doc_2.docx'


def test_collision_warns(caplog: pytest.LogCaptureFixture) -> None:
    used = {'a.docx'}
    with caplog.at_level(logging.WARNING):
        unique_filename('a.docx', used)
    assert any('a.docx' in r.message for r in caplog.records)
