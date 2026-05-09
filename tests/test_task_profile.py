from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from localeforge.errors import TaskProfileError
from localeforge.task_profile import load_task_profile


class TaskProfileTests(unittest.TestCase):
    def write_task(self, text: str) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "task.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_minimal_transform_task_uses_defaults(self) -> None:
        path = self.write_task("---\nid: proofread\n---\n\nPolish the text.\n")
        profile = load_task_profile(path)

        self.assertEqual(profile.id, "proofread")
        self.assertEqual(profile.mode, "transform")
        self.assertEqual(profile.input.column, "source")
        self.assertEqual(profile.output.column, "target")
        self.assertTrue(profile.output.overwrite)
        self.assertEqual(profile.prompt, "Polish the text.")

    def test_full_task_reads_nested_config(self) -> None:
        path = self.write_task(
            "---\n"
            "id: proofread-fr\n"
            "mode: transform\n"
            "input:\n"
            "  sheet: Sheet1\n"
            "  column: C\n"
            "  start_row: 3\n"
            "output:\n"
            "  column: F\n"
            "  columns:\n"
            "    status: G\n"
            "    reason: H\n"
            "model:\n"
            "  execution_mode: api\n"
            "  provider: default-api\n"
            "  name: gpt-4.1-mini\n"
            "  concurrency: 4\n"
            "---\n\nPrompt body\n"
        )
        profile = load_task_profile(path)

        self.assertEqual(profile.input.column, "C")
        self.assertEqual(profile.input.start_row, 3)
        self.assertEqual(profile.output.columns["status"], "G")
        self.assertEqual(profile.output.columns["reason"], "H")
        self.assertEqual(profile.model.provider, "default-api")
        self.assertEqual(profile.model.concurrency, 4)

    def test_scalar_model_is_model_name_shorthand(self) -> None:
        path = self.write_task("---\nid: rewrite\nmode: transform\nmodel: gpt-5.5\n---\n\nRewrite.\n")

        profile = load_task_profile(path)

        self.assertEqual(profile.model.name, "gpt-5.5")
        self.assertIsNone(profile.model.provider)
        self.assertIsNone(profile.model.execution_mode)

    def test_example_task_is_valid(self) -> None:
        root = Path(__file__).resolve().parents[1]
        profile = load_task_profile(root / "tasks" / "example-task.md")

        self.assertEqual(profile.id, "example-rewrite-fr")
        self.assertEqual(profile.input.column, "source")
        self.assertEqual(profile.output.column, "target")
        self.assertIn("Return only the rewritten text.", profile.prompt)

    def test_missing_prompt_body_is_invalid(self) -> None:
        path = self.write_task("---\nid: empty\n---\n")

        with self.assertRaises(TaskProfileError):
            load_task_profile(path)

    def test_invalid_yaml_is_invalid(self) -> None:
        path = self.write_task("---\nid: [broken\n---\n\nPrompt\n")

        with self.assertRaises(TaskProfileError):
            load_task_profile(path)


if __name__ == "__main__":
    unittest.main()
