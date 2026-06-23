from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "validate_task.py"
SPEC = importlib.util.spec_from_file_location("validate_task", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
validate_task = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_task
SPEC.loader.exec_module(validate_task)


class SpecValidationTest(unittest.TestCase):
    def test_valid_ready_spec_has_no_errors(self) -> None:
        data = json.loads((ROOT / "examples" / "valid-task.json").read_text(encoding="utf-8"))
        findings = validate_task.validate_spec(data)
        self.assertFalse([item for item in findings if item.level == "ERROR"])
        self.assertTrue(any(item.code == "INFERRED_GOAL" for item in findings))

    def test_ready_requires_goal(self) -> None:
        data = {
            "status": "READY",
            "source_intent": "Сделать X",
            "goal_source": "explicit",
            "context": "Контекст",
            "scenarios": [
                {"name": "X", "given": "A", "when": "B", "then": "C"}
            ],
            "constraints": {
                "mandatory": ["Нет"],
                "preferred": ["Нет"],
                "forbidden": ["Нет"]
            }
        }
        findings = validate_task.validate_spec(data)
        self.assertTrue(any(item.code == "MISSING" and "goal" in item.message for item in findings))

    def test_ready_requires_all_constraint_categories(self) -> None:
        data = {
            "status": "READY",
            "source_intent": "Сделать X",
            "context": "Контекст",
            "goal": "Получить Y",
            "goal_source": "explicit",
            "scenarios": [
                {"name": "X", "given": "A", "when": "B", "then": "C"}
            ],
            "constraints": {
                "mandatory": ["Нет"],
                "preferred": ["Нет"]
            }
        }
        findings = validate_task.validate_spec(data)
        self.assertTrue(any("constraints.forbidden" in item.message for item in findings))

    def test_needs_input_requires_questions(self) -> None:
        findings = validate_task.validate_spec(
            {"status": "NEEDS_INPUT", "source_intent": "Сделать X", "questions": []}
        )
        self.assertTrue(any(item.code == "EMPTY" for item in findings))


class MarkdownValidationTest(unittest.TestCase):
    def test_valid_markdown_passes(self) -> None:
        text = (ROOT / "examples" / "valid-output.md").read_text(encoding="utf-8")
        findings = validate_task.validate_markdown(text)
        self.assertFalse([item for item in findings if item.level == "ERROR"])

    def test_template_is_rejected_due_to_placeholders(self) -> None:
        text = (ROOT / "templates" / "task-prompt.md").read_text(encoding="utf-8")
        findings = validate_task.validate_markdown(text)
        self.assertTrue(any(item.code == "PLACEHOLDER" for item in findings))

    def test_missing_gherkin_is_rejected(self) -> None:
        text = (ROOT / "examples" / "valid-output.md").read_text(encoding="utf-8")
        text = text.replace("  Then при маскировании всё тело запроса заменяется маской\n", "")
        findings = validate_task.validate_markdown(text)
        self.assertTrue(any(item.code == "GHERKIN" for item in findings))


if __name__ == "__main__":
    unittest.main()
