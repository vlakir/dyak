---
description: "Передать точное продолжение незавершённой задачи"
agent: tech-lead
---

Подготовь handoff $ARGUMENTS: T-ID и execution task ID, exact base/current SHA,
ветка/worktree/owner, actual agent/member/session IDs, dirty state, scope,
принятые решения, реальные проверки с rc/evidence и оставшиеся AC. Не выводи
секреты. У uncertain effects сначала reconciliation: timeout не доказывает
отмену. Сохрани незакоммиченное до shutdown; shutdown терминален, новый раунд
только новым worker от согласованного checkpoint, без resurrection/role drift.
Для runtime-файлов укажи, что offline validation не cold activation;
не запускай новый сервер вместо существующего и не обещай recovery всех сбоев.
