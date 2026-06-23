#!/usr/bin/env python3
"""Deterministic validator for agent-task-upgrade artifacts.

The validator deliberately checks structure, placeholders, and basic Gherkin shape.
It does not claim to validate business semantics or whether an inferred goal is true.

Usage:
    python tools/validate_task.py spec path/to/task-spec.json
    python tools/validate_task.py markdown path/to/final-task.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PLACEHOLDER_PATTERNS = (
    re.compile(r"<[^>\n]+>"),
    re.compile(r"\b(?:TODO|TBD|FIXME)\b", re.IGNORECASE),
    re.compile(r"\{\{[^}\n]+\}\}"),
)

EMPTY_CONSTRAINT_MARKERS = {
    "нет дополнительных пользовательских ограничений",
    "нет дополнительных ограничений",
    "нет",
}


@dataclass(frozen=True)
class Finding:
    level: str
    code: str
    message: str

    def render(self) -> str:
        return f"{self.level} {self.code}: {self.message}"


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def has_placeholder(text: str) -> bool:
    return any(pattern.search(text) for pattern in PLACEHOLDER_PATTERNS)


def normalized(text: str) -> str:
    return re.sub(r"[.。؛;:]+$", "", text.strip().lower())


def validate_string_list(
    value: Any, field: str, findings: list[Finding], *, require_item: bool = True
) -> None:
    if not isinstance(value, list):
        findings.append(Finding("ERROR", "TYPE", f"{field} должен быть массивом строк"))
        return
    if require_item and not value:
        findings.append(Finding("ERROR", "EMPTY", f"{field} не должен быть пустым"))
        return
    for index, item in enumerate(value):
        if not is_nonempty_string(item):
            findings.append(
                Finding("ERROR", "EMPTY_ITEM", f"{field}[{index}] должен быть непустой строкой")
            )
        elif has_placeholder(item):
            findings.append(
                Finding("ERROR", "PLACEHOLDER", f"{field}[{index}] содержит незаполненный маркер")
            )


def validate_scenario(value: Any, index: int, findings: list[Finding]) -> None:
    field = f"scenarios[{index}]"
    if not isinstance(value, dict):
        findings.append(Finding("ERROR", "TYPE", f"{field} должен быть объектом"))
        return

    allowed = {"name", "given", "when", "then", "and"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        findings.append(
            Finding("ERROR", "UNKNOWN_FIELD", f"{field} содержит неизвестные поля: {', '.join(unknown)}")
        )

    for key in ("name", "given", "when", "then"):
        item = value.get(key)
        if not is_nonempty_string(item):
            findings.append(Finding("ERROR", "MISSING", f"{field}.{key} обязателен"))
        elif has_placeholder(item):
            findings.append(
                Finding("ERROR", "PLACEHOLDER", f"{field}.{key} содержит незаполненный маркер")
            )

    if "and" in value:
        validate_string_list(value["and"], f"{field}.and", findings, require_item=False)

    then = value.get("then")
    if is_nonempty_string(then):
        weak_then = re.search(
            r"\b(?:реализован[аоы]?|написан[аоы]?|отрефакторен[аоы]?|измен[её]н[аоы]?)\b",
            then,
            re.IGNORECASE,
        )
        if weak_then:
            findings.append(
                Finding(
                    "WARN",
                    "IMPLEMENTATION_THEN",
                    f"{field}.then может описывать реализацию, а не наблюдаемый результат",
                )
            )


def validate_spec(data: Any) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(data, dict):
        return [Finding("ERROR", "ROOT_TYPE", "корень JSON должен быть объектом")]

    allowed = {
        "status",
        "source_intent",
        "context",
        "goal",
        "goal_source",
        "scenarios",
        "constraints",
        "questions",
        "blocked_reason",
    }
    unknown = sorted(set(data) - allowed)
    if unknown:
        findings.append(
            Finding("ERROR", "UNKNOWN_FIELD", f"неизвестные поля: {', '.join(unknown)}")
        )

    status = data.get("status")
    if status not in {"READY", "NEEDS_INPUT", "BLOCKED"}:
        findings.append(
            Finding("ERROR", "STATUS", "status должен быть READY, NEEDS_INPUT или BLOCKED")
        )

    source_intent = data.get("source_intent")
    if not is_nonempty_string(source_intent):
        findings.append(Finding("ERROR", "MISSING", "source_intent обязателен"))

    if status == "READY":
        for key in ("context", "goal"):
            value = data.get(key)
            if not is_nonempty_string(value):
                findings.append(Finding("ERROR", "MISSING", f"{key} обязателен для READY"))
            elif has_placeholder(value):
                findings.append(
                    Finding("ERROR", "PLACEHOLDER", f"{key} содержит незаполненный маркер")
                )

        goal_source = data.get("goal_source")
        if goal_source not in {"explicit", "inferred", "confirmed"}:
            findings.append(
                Finding(
                    "ERROR",
                    "GOAL_SOURCE",
                    "goal_source должен быть explicit, inferred или confirmed",
                )
            )
        elif goal_source == "inferred":
            findings.append(
                Finding(
                    "WARN",
                    "INFERRED_GOAL",
                    "цель выведена из намерения; убедитесь, что вывод однозначен",
                )
            )

        scenarios = data.get("scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            findings.append(
                Finding("ERROR", "SCENARIOS", "для READY нужен хотя бы один сценарий")
            )
        else:
            for index, scenario in enumerate(scenarios):
                validate_scenario(scenario, index, findings)

        constraints = data.get("constraints")
        if not isinstance(constraints, dict):
            findings.append(
                Finding("ERROR", "CONSTRAINTS", "constraints должен быть объектом")
            )
        else:
            allowed_constraints = {"mandatory", "preferred", "forbidden"}
            unknown_constraints = sorted(set(constraints) - allowed_constraints)
            if unknown_constraints:
                findings.append(
                    Finding(
                        "ERROR",
                        "UNKNOWN_CONSTRAINT",
                        "неизвестные категории ограничений: " + ", ".join(unknown_constraints),
                    )
                )
            for key in ("mandatory", "preferred", "forbidden"):
                validate_string_list(constraints.get(key), f"constraints.{key}", findings)

    elif status == "NEEDS_INPUT":
        validate_string_list(data.get("questions"), "questions", findings)
        if is_nonempty_string(data.get("goal")) and data.get("goal_source") == "inferred":
            findings.append(
                Finding(
                    "WARN",
                    "UNCONFIRMED_GOAL",
                    "NEEDS_INPUT содержит выведенную цель; не представляйте её как согласованную",
                )
            )

    elif status == "BLOCKED":
        if not is_nonempty_string(data.get("blocked_reason")):
            findings.append(
                Finding("ERROR", "MISSING", "blocked_reason обязателен для BLOCKED")
            )

    return findings


def heading_positions(text: str) -> dict[str, int]:
    positions: dict[str, int] = {}
    for match in re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", text):
        title = match.group(2).strip().lower()
        positions[title] = match.start()
    return positions


def section_body(text: str, title: str) -> str | None:
    pattern = re.compile(
        rf"(?ms)^#{{1,6}}\s+{re.escape(title)}\s*$\n(.*?)(?=^#{{1,6}}\s+|\Z)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def bullet_items(body: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"(?m)^\s*[-*]\s+(.+?)\s*$", body)]


def validate_markdown(text: str) -> list[Finding]:
    findings: list[Finding] = []
    if not text.strip():
        return [Finding("ERROR", "EMPTY_FILE", "Markdown-файл пуст")]

    if has_placeholder(text):
        findings.append(
            Finding("ERROR", "PLACEHOLDER", "документ содержит незаполненные маркеры")
        )

    required_headings = [
        "статус",
        "контекст",
        "цель",
        "критерии приёмки",
        "пользовательские ограничения",
        "обязательные",
        "предпочтительные",
        "запрещено",
        "инженерные инварианты",
        "безопасность",
        "связность и простота",
        "проверяемость",
        "порядок выполнения",
        "формат ответа исполнителя",
    ]
    positions = heading_positions(text)
    for heading in required_headings:
        if heading not in positions:
            findings.append(
                Finding("ERROR", "MISSING_HEADING", f"отсутствует раздел «{heading}»")
            )

    status_body = section_body(text, "Статус")
    if status_body is None or status_body.strip() != "READY":
        findings.append(
            Finding("ERROR", "STATUS", "итоговый Markdown должен иметь статус READY")
        )

    for title in ("Контекст", "Цель"):
        body = section_body(text, title)
        if body is None or not body.strip():
            findings.append(Finding("ERROR", "EMPTY_SECTION", f"раздел «{title}» пуст"))

    scenarios = list(
        re.finditer(
            r"(?ms)^\s*Scenario:\s*(?P<name>.+?)\s*$\n"
            r"\s*Given\s+(?P<given>.+?)\s*$\n"
            r"\s*When\s+(?P<when>.+?)\s*$\n"
            r"\s*Then\s+(?P<then>.+?)\s*$",
            text,
        )
    )
    if not scenarios:
        findings.append(
            Finding(
                "ERROR",
                "GHERKIN",
                "не найден полный сценарий Scenario/Given/When/Then",
            )
        )
    else:
        for index, match in enumerate(scenarios):
            for key in ("name", "given", "when", "then"):
                if not match.group(key).strip():
                    findings.append(
                        Finding("ERROR", "GHERKIN_EMPTY", f"сценарий {index + 1}: {key} пуст")
                    )

    for title in ("Обязательные", "Предпочтительные", "Запрещено"):
        body = section_body(text, title)
        if body is None:
            continue
        items = bullet_items(body)
        if not items:
            findings.append(
                Finding("ERROR", "CONSTRAINT_EMPTY", f"раздел «{title}» должен содержать список")
            )
            continue
        for item in items:
            if not item.strip():
                findings.append(
                    Finding("ERROR", "CONSTRAINT_EMPTY_ITEM", f"раздел «{title}» содержит пустой пункт")
                )

    if re.search(r"(?im)^\s*(?:Given|When|Then)\s*$", text):
        findings.append(
            Finding("ERROR", "GHERKIN_EMPTY", "обнаружена пустая строка Given/When/Then")
        )

    return findings


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"файл не найден: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"некорректный JSON: {exc}") from exc


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"файл не найден: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"файл должен быть в UTF-8: {exc}") from exc


def print_findings(findings: Iterable[Finding]) -> int:
    findings = list(findings)
    for finding in findings:
        print(finding.render())
    errors = sum(1 for finding in findings if finding.level == "ERROR")
    warnings = sum(1 for finding in findings if finding.level == "WARN")
    if not findings:
        print("PASS: структурная валидация пройдена")
    else:
        print(f"SUMMARY: errors={errors}, warnings={warnings}")
    return 1 if errors else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("spec", "markdown"))
    parser.add_argument("path", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.mode == "spec":
            findings = validate_spec(load_json(args.path))
        else:
            findings = validate_markdown(load_text(args.path))
    except ValueError as exc:
        print(f"ERROR IO: {exc}")
        return 2
    return print_findings(findings)


if __name__ == "__main__":
    raise SystemExit(main())
