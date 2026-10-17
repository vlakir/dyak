# T039 — полный ручной перенос dreamteam 2.0.0 (R2)

Статус R3: legacy деактивирован после actual semantic review и fresh
byte/hash/mode-check; итоговые review/CI ещё требуются, cold activation нет.
База R2: `1f916f2e7307d454b7b0d43e6050f2f684e3678e`;
согласованный current-main: `90f2b47a0f41ec17d556d758befa5cd61c0c1ec7`.
Публичное имя — `dyak`; каталог исторически называется `djak`.

## Граница

Переносим методику, native роли, команды и управляющий контекст; не меняем
приложение, стек, зависимости, lock, CI, скрипты гейтов и бизнес-контракт.
`chancellery` — движок, `dyak` — GUI/CLI/PDF/scaffold/упаковка,
`letopis` — другой потребитель библиотеки, не часть этого переноса.
Примеры не меняются сознательно: поведение приложения неизменно.

## Реальный inventory рендера — 28/28

Источник: установленный CLI `dt init PATH --defaults --data key=value`,
эфемерный render с существующими публичными ответами; не переписанный CLI,
не подложная база. Авторские ответы остаются исходными, в журнал не выводятся.

| № | Managed path | Native назначение / ручное решение |
|---|---|---|
| 1 | `.copier-answers.yml` | После review/hash-check provenance 2.0.0 и installed bundle из реального render; прежние публичные/авторские ответы сохранены |
| 2 | `.gitignore` | Сохранить существующее исключение worktrees/venv; бизнес-дельты нет |
| 3 | `.opencode/agents/architect.md` | Анализ требований/архитектуры, read-only, explicit edit/bash/question deny |
| 4 | `.opencode/agents/backend.md` | Контракты, persistence, backend; question deny, спорные требования лиду |
| 5 | `.opencode/agents/designer.md` | UX, состояния, доступность; question deny |
| 6 | `.opencode/agents/devops.md` | CI/окружения/rollback, общий ресурс только через лида; question deny |
| 7 | `.opencode/agents/frontend.md` | Web UI и интеграция; question deny |
| 8 | `.opencode/agents/mobile.md` | Mobile/platform/integration; question deny |
| 9 | `.opencode/agents/reviewer.md` | Независимое review, read-only, explicit edit/bash/question deny |
| 10 | `.opencode/agents/tech-lead.md` | Единственный primary и question allow; точная база/identity, terminal shutdown, новая итерация новым worker |
| 11 | `.opencode/agents/tester.md` | Проверка поведения/регрессий/AC, question deny |
| 12 | `.opencode/ensemble.json` | Сохранить mergeOnCleanup=false и promptForModels=false |
| 13 | `.opencode/team-roles.md` | Девять ролей, ownership, непрерывность незаконченного, полномочия и канон |
| 14 | `AGENTS.md` | Активный канон 2.0: существующий доменный контекст/DoD примеров + глобальные актуальные правила |
| 15 | `BACKLOG.md` | Сохранить весь реальный backlog; T009 остаётся незакрытой |
| 16 | `BOARD.md` | Только своя запись T039 с AC; Done только по факту полной приёмки |
| 17 | `CHANGELOG.md` | Только запись T039, без переписывания исторических версий |
| 18 | `CONCEPT.md` | Immutable исходный body/байты, сверка sha256; НЕ заменять пустым render |
| 19 | `DECISIONS.md` | Только ADR T039 с ручными решениями/ограничениями |
| 20 | `README.md` | Существующий бизнес-контекст и инструкция native методики; не заменять scaffold |
| 21 | `hooks/pre-push` | Сохранить фактический hook без изменения поведения; gates.sh --light локально, полный srv CI |
| 22 | `opencode.json` | Существующий schema/plugin pin/default_agent/instructions; question deny default, lead override |
| 23 | `pyproject.toml` | Сохранить существующий проект/стек/гейты; не переносить scaffold |
| 24 | `scripts/pytest-guard.sh` | Не добавлять: remote purpose покрыт изоляцией srv CI; local purpose — обязательной координацией/сериализацией по AGENTS. Автоматический mutex не установлен, gates.sh его не гарантирует; для local full лид обеспечивает согласованный exclusive mutex. Поведение scripts вне scope |
| 25 | `specs/design-brief-template.md` | Native шаблон UX-решения для будущих задач, не ретроактивная приёмка |
| 26 | `specs/spec-template.md` | Native шаблон spec/clarify/analyze для будущих крупных задач |
| 27 | `src/main.py` | Не добавлять business seed: существующий src/dyak — приложение |
| 28 | `tests/test_main.py` | Не добавлять fake seed-test: существующие tests — проверки dyak |

## Actual custom / legacy → native

- `CLAUDE.md`: старый активный канон. Его проектный DoD (обновление
  `examples/`) уже есть в `AGENTS.md` и сохраняется; общая методика переходит
  в `AGENTS.md`, процедуры spec/clarify/analyze — native commands.
  В R3 удалён после fresh сверки private originals и actual semantic review;
  reviewer не нашёл уникального legacy-правила без native назначения.
- Actual tracked `.claude/**`: **0 файлов** по `git ls-files -s`; это явный
  результат инвентаризации, а не «historical_preserved=[] значит всё учтено».
  Неизвестные untracked секреты не копировались и не активируются.
- `.opencode/agents/architect.md`: сохранить русскоязычный консультационный
  протокол, анализ требований и ADR-Lite, не заменить generic заглушкой.
- `AGENTS.md`: сохранить проектный DoD примеров; заполнить отсутствующий
  доменный контекст по README/ADR T033/T035, не по старым предположениям ТЗ.
- `.opencode/team-roles.md`: существующая интеграционная методика остаётся;
  добавить обязательные owner/base/agent checks и передачу unfinished work.
- `specs/T008-gui/**`, `specs/T010-windows-build/**` и прочие старые specs:
  исторические факты/AC не переобъявлять выполненными новым шаблоном.
- `hooks/`, `.forgejo/`, `.github/`, `ci/`, `scripts/`: реальный delivery
  контур сохраняется; обновляются только ссылки/инструкции в методике.
- Новые `.opencode/commands/spec.md`, `clarify.md`, `analyze.md`, `status.md`,
  `handoff.md`: реальные control surfaces для принятия/разбора/продолжения
  задачи, все адресованы `tech-lead`, не заменяют полномочия пользователя.

## Evidence до деактивации

Private R2 directory:
`/home/vlakir/.local/share/dreamteam/migration-20261016/djak-T039-devops-r2-durable-20261017`.
Создан заново с mode 0700; сохранены 72 actual tracked originals и 28
rendered файлов (0600), manifest с byte-count/sha256/original-mode.
Отбор включает все managed-potential root и immutable CONCEPT, не следует
symlink, не включает gitlinks/foreign worktrees. Untracked файлы не копирует.
R1 private prepare.py не читался, не исполнялся и не перезаписывался.

Первый настоящий `dt update ROOT --dry-run`: **rc=2**, не успех.
stdout/stderr захвачены только в RAM; сохранён лишь whitelist JSON.
Первый простой uppercase category matcher дал нули и не классифицирует
ошибку как clean: это ограничение парсера, не доказательство no-op.
Перед изменением provenance/деактивацией R3 повторил все72 original-byte
hashes/bytes/checkpoint/modes: mismatch0; actual review передан лидом.
Reviewer private originals не проверял; это авторское evidence.

## Проверка повторного применения и recovery

R3 выполнил полный повтор actual `dt update --dry-run` после ручной миграции,
с независимым rc и whitelist категориями. CLI apply/noop сам по себе не AC:
Все28 назначений и реальные controls проверяются отдельно от CLI: normal
plan дважды rc=0, 1 changed / 24 unchanged / 3 added / 0 removed /
0 conflicts. Changed answers — только YAML formatting (semantic equality
проверена в RAM), без actual architect_model addition. ADD — guard и два
business seeds из строк24/27/28; их не применяем по указанным назначениям.
Reviewer после actual gates/AGENTS/Forgejo review не признал guard ADD
потерянным HIGH: remote isolation и local agreed coordination не следует
выдавать за установленный auto mutex. Meaningful MODIFY/HIGH не скрываются
generic CLI-noop: это manual mapping и review, не автоматический apply.
Raw plan не записывался; hash/stability и ограничения — [r3-checkpoint.md](r3-checkpoint.md).

Offline effective validation установленным OpenCode 1.19.0 не запускает
новый server, не меняет installed plugins/global models и не означает
cold activation. Работающий server 4096 не перезапускаем. Cold activation
исходного checkout — отдельное окно и отдельное разрешение; owner исходной
ветки неизвестен, она не объявлена idle.

Rollback: до merge вернуть только собственный task diff на checkpoint;
после доставки — отдельный revert задачного squash с повторными гейтами.
При необходимости исходные байты доступны в private manifest/originals;
восстановление только перечисленных собственных файлов, не всего checkout
и не чужих worktrees. Отмена не удаляет незаконченные задачи/артефакты.
