# Plan: T010 — Windows-сборка GUI «Дьяк»

Инфра-фича: сборка Windows-бинарников GUI (T008) через GitHub Actions —
**setup-инсталлятор** (Inno Setup) + **portable-zip**, релиз по тегу
`vX.Y.Z`. Образец — `mil_mapper`
(`.github/workflows/build-windows-installer.yml` + `SK42*.spec` +
`installer.iss`); адаптация под наш стек (uv, PySide6, src-layout,
subprocess-ядро). Один PR, коммиты по фазам, squash при merge.

## Результаты спайка (2026-06-23, локально, Linux onedir-бандл)

Механика `frozen`-бандла одинакова на Linux/Windows — ключевые риски
сняты локально, без Windows-раннера:

1. **Subprocess-ядро в бандле работает, `runner.py` не меняем.** В бандле
   `sys.executable` = сам exe. Единая точка входа `src/dyak/_app_entry.py`
   снимает префикс `-m dyak` и по наличию команды разводит режим
   (нет аргументов → GUI, есть → CLI). Вызов `dyak -m dyak generate …`
   (ровно `runner.base_argv()`) реально сгенерировал 3 документа из
   бандла; JSONL-прогресс в stderr корректен. → `runner.py` остаётся
   как есть (ADR T008 правильно выбрал `sys.executable -m dyak`).
2. **Package-data ядра нужно собирать явно.** Без них падает на
   `petrovich/rules/rules.json`. Решение — `collect_all('petrovich')`,
   `collect_all('pymorphy3')`, `collect_all('pymorphy3_dicts_ru')`
   (datas + binaries + hiddenimports). GUI-assets — `datas`
   (`src/dyak/gui/assets → dyak/gui/assets`), `load_app_icon` грузит
   `icon.png` через `importlib.resources` и в бандле работает.
3. **GUI-режим** (без аргументов) поднимается из бандла (offscreen),
   иконка подхватывается.
4. **PyInstaller 6.21.0 под Python 3.14.5** ставится и собирает чисто.
5. **Размер onedir ~221 МБ** (PySide6 ~28 МБ; основной вес — numpy +
   `pymorphy3-dicts-ru` + stdlib). Опциональная оптимизация `excludes`
   (tkinter, unittest, pydoc) — в фазе полировки, если останется время;
   не блокер acceptance.

## Раскладка артефактов (`packaging/`)

Инфра в своей папке (не засоряем корень, src-layout-стиль):

- `packaging/dyak.spec` — **одна** onedir-сборка (COLLECT → `dist/dyak/`).
  Содержимое для инсталлятора и portable **идентично** (в отличие от
  образца mil_mapper, где у portable была своя структура папок) →
  одна сборка PyInstaller переиспользуется для обоих артефактов: Inno
  упаковывает `dist/dyak/*`, portable-zip = тот же `dist/dyak/` +
  `README.txt`. Экономим вторую сборку (DRY).
- `packaging/installer.iss` — Inno Setup: per-user (`{localappdata}`,
  `PrivilegesRequired=lowest`), RU/EN, иконка `SetupIconFile`, ярлык на
  рабочий стол, `OutputBaseFilename=dyak-{VERSION}-setup`. Без миграций и
  диалогов ключей (у нас их нет — проще, чем образец mil_mapper).
- `src/dyak/_app_entry.py` — единая точка входа бандла (уже создана в
  спайке). Импорты `dyak.cli.app` и `dyak.gui.app.main` — оба в шапке
  (правило импортов соблюдено; Qt тянется и в CLI-режиме бандла, но
  subprocess зовётся раз на батч `generate`, оверхед приемлем).

Spec'и запускаются из корня репо (`pyinstaller packaging/dyak.spec`),
пути внутри — относительно cwd (`src/…`). Inno `installer.iss` берёт
`dist/dyak/*` относительно `{#SourcePath}\..`.

## Сборочный стек (uv-адаптация)

- PyInstaller — отдельная dependency-group `build` в `pyproject.toml`
  (`uv sync --group build`), чтобы попал в `uv.lock` (воспроизводимость),
  но не тянулся в обычный `uv sync` / тесты.
- Workflow: `astral-sh/setup-uv` + `uv sync --group build` + кеш по
  `uv.lock`; `uv run pyinstaller packaging/dyak.spec`.
- Python в сборке — 3.14 (как проект). Если на windows-latest нет
  wheels PyInstaller/PySide6 под 3.14 — зафиксировать build-Python ниже
  (заметка в workflow, как в образце).

## Релизный процесс — теги (новое для проекта, → ADR)

Проект до сих пор не использовал git-теги (milestone-versioning через
CHANGELOG). T010 вводит теги `vX.Y.Z` как **релизный триггер**:

- Workflow: `on: push: tags: ['v*']` + `workflow_dispatch` (ручной
  прогон для проверки без релиза).
- `VERSION` из `github.ref_name`; при `workflow_dispatch` — fallback
  (`0.0.0-dev` или input).
- Release — `softprops/action-gh-release@v2` (только на тег), прикладывает
  `dyak-X.Y.Z-setup.exe` + `dyak-X.Y.Z-portable.zip`.
- Версия тега и `[N.M.0]` в CHANGELOG смыкаются: тег ставится на
  milestone-коммит в `main` после среза версии (ручной шаг кадровика).

## Фазы (коммиты на ветке)

1. **Entry + spec (частично готово в спайке).** `_app_entry.py`,
   `packaging/dyak.spec` (одна onedir), dependency-group `build`.
   Локальная Linux-сборка как дым-проверка spec.
2. **Inno Setup + portable.** `installer.iss` (per-user, RU/EN, иконка),
   шаг упаковки portable (папка exe + `README.txt` → zip из того же
   `dist/dyak/`). Inno локально не проверить (Windows-only) —
   верификация в CI.
3. **Workflow + теги.** `.github/workflows/build-windows.yml`:
   setup-uv → sync → **одна** сборка → installer → portable-zip →
   артефакты → Release по тегу. **Верификация — `workflow_dispatch`
   прогон на
   GitHub** (собираются ли артефакты на windows-latest) до постановки
   реального тега.
4. **Документация.** ADR (PyInstaller+Inno, единый entry, package-data,
   теги, uv-адаптация), `CHANGELOG.md` `[Unreleased]`, `README.md`
   (раздел про Windows-сборку/релиз), `BOARD.md` Doing→Done. Примеры
   ядра T010 не меняет (инфра) — `examples/` не трогаем осознанно.

## Acceptance (из BACKLOG)

Пуш тега `vX.Y.Z` → workflow на windows-latest; PyInstaller собирает GUI;
`dyak-X.Y.Z-setup.exe` (per-user, без админа) + `dyak-X.Y.Z-portable.zip`
приложены к GitHub Release; запущенный exe открывает окно «Дьяк» с иконкой
и **реально генерирует документы** (subprocess-ядро в бандле — снято
спайком); сборка воспроизводима из чистого клона.

## Ограничение проверки

Windows-бинарники локально (Linux) не собрать — финальная верификация
инсталлятора/portable только на windows-раннере (workflow_dispatch).
Subprocess-механика, package-data и entry-разводка проверены локально
(frozen идентичен на платформах). «Реальный запуск exe открывает окно и
генерирует» на чистой Windows — ручная проверка кадровика/Разработчика
после первого релиза (отметить в acceptance как пост-релизный шаг).

## Проверки перед push

`uv run ruff check . && uv run ruff format --check . && uv run mypy src &&
uv run pytest` (coverage ≥ 80% на `src/`). Импорты только в шапке; без
`# noqa` / `# type: ignore`.
