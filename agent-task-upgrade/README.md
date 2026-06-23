# agent-task-upgrade

Скилл преобразует краткое намерение разработчика в проверяемое задание для
ИИ-исполнителя. Он выделяет цель, строит критерии Given/When/Then, запрашивает
отсутствующие ограничения и добавляет базовые инженерные инварианты.

## Состав

- `SKILL.md` — основной алгоритм и контракт поведения;
- `templates/task-prompt.md` — шаблон готового задания;
- `templates/clarification.md` — шаблон блокирующих вопросов;
- `tools/validate_task.py` — валидатор JSON-спецификации и итогового Markdown;
- `schemas/task-spec.schema.json` — формальная JSON Schema;
- `examples/` — успешный, неполный и запрещённый сценарии;
- `tests/` — регрессионные тесты валидатора.

## Проверка

```bash
python -m unittest discover -s tests -v
python tools/validate_task.py spec examples/valid-task.json
python tools/validate_task.py markdown examples/valid-output.md
```

Валидатор не определяет бизнес-смысл автоматически. Он проверяет структуру,
обязательные секции, заполненность ограничений, форму Given/When/Then и отсутствие
заглушек.
