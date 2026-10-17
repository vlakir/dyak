---
description: "Подготовить зрелую спецификацию dyak с границами и AC"
agent: tech-lead
---

Разбери задачу $ARGUMENTS по CONCEPT, README, DECISIONS, BOARD/BACKLOG.
Не путай движок chancellery с оболочками dyak и соседним letopis.
Найди существующий T-ID; новый присваивай по max BOARD/BACKLOG/CHANGELOG +1.
Для крупной задачи заполни specs/T-ID-slug/spec.md по specs/spec-template.md:
пользовательские сценарии, требования, измеримые AC, ограничения и out of scope.
Сохрани реальные незавершённые AC и исторические статусы. Не реализуй код
до clarify/analyze. Неизвестные продуктовые решения вынеси native question
с рекомендацией первым вариантом; не подменяй ответы предположениями.
